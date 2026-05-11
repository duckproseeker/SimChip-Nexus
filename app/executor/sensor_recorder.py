from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SensorRecorderResult:
    profile_name: str | None
    sensor_count: int
    output_root: Path


class SensorRecorderProcess:
    """Run the CARLA sensor attachment lifecycle in a dedicated worker process."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float,
        output_root: Path,
        *,
        startup_timeout_seconds: float = 15.0,
        shutdown_timeout_seconds: float = 10.0,
        python_executable: str | None = None,
        worker_module: str = "app.executor.sensor_recorder_worker",
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._output_root = output_root
        self._startup_timeout_seconds = startup_timeout_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._python_executable = python_executable or sys.executable
        self._worker_module = worker_module

        self._worker_root = output_root / "_worker"
        self._descriptor_path = self._worker_root / "descriptor.json"
        self._state_path = self._worker_root / "state.json"
        self._log_path = self._worker_root / "worker.log"

        self._process: subprocess.Popen[str] | None = None
        self._log_handle: TextIO | None = None
        self._stop_requested = False

    def start(self, descriptor: Any, *, hero_role_name: str = "hero") -> SensorRecorderResult:
        if self._process is not None:
            raise RuntimeError("sensor recorder worker already started")

        self._prepare_worker_files(descriptor)
        self._log_handle = self._log_path.open("w", encoding="utf-8")
        self._process = subprocess.Popen(
            self._build_command(hero_role_name),
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        deadline = time.monotonic() + self._startup_timeout_seconds
        while time.monotonic() < deadline:
            state = self._read_state()
            if state is not None:
                status = str(state.get("status") or "").strip().lower()
                if status == "ready":
                    return SensorRecorderResult(
                        profile_name=self._read_optional_text(state.get("profile_name")),
                        sensor_count=max(0, int(state.get("sensor_count") or 0)),
                        output_root=Path(
                            str(state.get("output_root") or self._output_root)
                        ).expanduser(),
                    )
                if status == "error":
                    error_message = self._worker_error_message(
                        default="sensor recorder worker failed before becoming ready"
                    )
                    self.stop()
                    raise RuntimeError(error_message)

            if self._process.poll() is not None:
                error_message = self._worker_error_message(
                    default=(
                        "sensor recorder worker exited before becoming ready "
                        f"(code={self._process.returncode})"
                    )
                )
                self.stop()
                raise RuntimeError(error_message)

            time.sleep(0.1)

        timeout_message = self._worker_error_message(
            default=(
                "sensor recorder worker did not become ready within "
                f"{self._startup_timeout_seconds:.1f}s"
            )
        )
        self.stop()
        raise RuntimeError(timeout_message)

    def unexpected_exit_error(self) -> str | None:
        if self._process is None:
            return None
        return_code = self._process.poll()
        if return_code is None or self._stop_requested:
            return None
        if return_code == 0:
            return None
        return self._worker_error_message(
            default=f"sensor recorder worker exited unexpectedly (code={return_code})"
        )

    def stop(self) -> None:
        self._stop_requested = True
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=self._shutdown_timeout_seconds)
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:  # noqa: BLE001
                pass
            self._log_handle = None

    def _prepare_worker_files(self, descriptor: Any) -> None:
        self._worker_root.mkdir(parents=True, exist_ok=True)
        descriptor_payload = self._descriptor_to_payload(descriptor)
        self._descriptor_path.write_text(
            json.dumps(descriptor_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if self._state_path.exists():
            self._state_path.unlink()
        if self._log_path.exists():
            self._log_path.unlink()

    def _build_command(self, hero_role_name: str) -> list[str]:
        return [
            self._python_executable,
            "-m",
            self._worker_module,
            "--host",
            self._host,
            "--port",
            str(self._port),
            "--timeout-seconds",
            str(self._timeout_seconds),
            "--output-root",
            str(self._output_root),
            "--descriptor-path",
            str(self._descriptor_path),
            "--state-path",
            str(self._state_path),
            "--hero-role-name",
            hero_role_name,
        ]

    @staticmethod
    def _descriptor_to_payload(descriptor: Any) -> dict[str, Any]:
        if hasattr(descriptor, "to_dict"):
            payload = descriptor.to_dict()
        elif hasattr(descriptor, "model_dump"):
            payload = descriptor.model_dump(mode="json")
        else:
            raise RuntimeError("descriptor must expose to_dict() or model_dump()")
        if not isinstance(payload, dict):
            raise RuntimeError("descriptor payload must be a mapping")
        return payload

    def _read_state(self) -> dict[str, Any] | None:
        if not self._state_path.exists():
            return None
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _read_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _worker_error_message(self, *, default: str) -> str:
        state = self._read_state() or {}
        explicit_error = self._read_optional_text(state.get("error"))
        message = explicit_error or default
        log_tail = self._read_log_tail()
        if log_tail:
            return f"{message}. worker_log_tail={log_tail}"
        return message

    def _read_log_tail(self, max_lines: int = 8) -> str | None:
        if not self._log_path.exists():
            return None
        try:
            lines = self._log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        if not lines:
            return None
        tail = " | ".join(line.strip() for line in lines[-max_lines:] if line.strip())
        return tail or None


class SensorRecorder:
    """Attach descriptor-defined sensors to the hero actor and persist outputs."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float,
        output_root: Path,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._output_root = output_root

        self._carla: Any = None
        self._client: Any = None
        self._world: Any = None
        self._hero_actor: Any = None
        self._spawned_sensors: list[Any] = []
        self._jsonl_handles: dict[str, Any] = {}
        self._lock = threading.Lock()

    def start(self, descriptor: Any, *, hero_role_name: str = "hero") -> SensorRecorderResult:
        sensor_config = getattr(descriptor, "sensors", None)
        sensor_specs = list(getattr(sensor_config, "sensors", []) or [])
        if not getattr(sensor_config, "enabled", False) or not sensor_specs:
            raise RuntimeError("descriptor does not define enabled sensors")

        self._connect()
        self._hero_actor = self._wait_for_hero_actor(hero_role_name)
        blueprint_library = self._world.get_blueprint_library()
        self._output_root.mkdir(parents=True, exist_ok=True)

        manifest = {
            "profile_name": getattr(sensor_config, "profile_name", None),
            "config_yaml_path": getattr(sensor_config, "config_yaml_path", None),
            "hero_role_name": hero_role_name,
            "sensors": [spec.model_dump(mode="json") for spec in sensor_specs],
        }
        (self._output_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        for spec in sensor_specs:
            blueprint = blueprint_library.find(spec.type)
            self._apply_spec_to_blueprint(blueprint, spec)
            transform = self._build_transform(spec)
            sensor_actor = self._world.spawn_actor(
                blueprint,
                transform,
                attach_to=self._hero_actor,
            )
            sensor_output_dir = self._output_root / spec.id
            sensor_output_dir.mkdir(parents=True, exist_ok=True)
            sensor_actor.listen(
                self._build_sensor_callback(
                    sensor_id=spec.id,
                    sensor_type=spec.type,
                    output_dir=sensor_output_dir,
                )
            )
            self._spawned_sensors.append(sensor_actor)

        return SensorRecorderResult(
            profile_name=getattr(sensor_config, "profile_name", None),
            sensor_count=len(self._spawned_sensors),
            output_root=self._output_root,
        )

    def stop(self) -> None:
        for handle in self._jsonl_handles.values():
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass
        self._jsonl_handles.clear()

        sensor_actors = list(reversed(self._spawned_sensors))
        for sensor_actor in sensor_actors:
            try:
                sensor_actor.listen(lambda *_args: None)
            except Exception:  # noqa: BLE001
                pass
            try:
                sensor_actor.stop()
            except Exception:  # noqa: BLE001
                pass
        # CARLA sensor callbacks may still flush briefly after stop(); give the
        # native listener threads a short grace window before destroy().
        if sensor_actors:
            time.sleep(0.2)
        for sensor_actor in sensor_actors:
            try:
                sensor_actor.destroy()
            except Exception:  # noqa: BLE001
                pass
        self._spawned_sensors.clear()
        self._hero_actor = None
        self._world = None
        self._client = None
        self._carla = None

    def _connect(self) -> None:
        try:
            import carla  # type: ignore
        except ImportError as exc:
            raise RuntimeError("carla Python API not found for sensor recording") from exc

        self._carla = carla
        self._client = carla.Client(self._host, self._port)
        self._client.set_timeout(self._timeout_seconds)
        self._world = self._client.get_world()

    def _wait_for_hero_actor(self, role_name: str, wait_timeout_seconds: float = 40.0) -> Any:
        deadline = time.monotonic() + wait_timeout_seconds
        while time.monotonic() < deadline:
            self._world = self._client.get_world()
            candidates = list(self._world.get_actors().filter("vehicle.*"))
            fallback_candidates: list[Any] = []
            for actor in candidates:
                actor_role = str(actor.attributes.get("role_name") or "").strip()
                if actor_role == role_name:
                    return actor
                if actor_role and actor_role.startswith("scenario_"):
                    continue
                fallback_candidates.append(actor)
            if len(fallback_candidates) == 1:
                return fallback_candidates[0]
            if len(fallback_candidates) > 1:
                fallback_candidates.sort(key=lambda actor: int(actor.id))
                return fallback_candidates[0]
            time.sleep(0.2)
        raise RuntimeError(f"hero actor with role_name='{role_name}' not found")

    def _build_transform(self, spec: Any) -> Any:
        return self._carla.Transform(
            self._carla.Location(
                x=float(spec.x),
                y=float(spec.y),
                z=float(spec.z),
            ),
            self._carla.Rotation(
                roll=float(spec.roll),
                pitch=float(spec.pitch),
                yaw=float(spec.yaw),
            ),
        )

    def _apply_spec_to_blueprint(self, blueprint: Any, spec: Any) -> None:
        attributes = {
            "image_size_x": getattr(spec, "width", None),
            "image_size_y": getattr(spec, "height", None),
            "fov": getattr(spec, "fov", None),
            "horizontal_fov": getattr(spec, "horizontal_fov", None),
            "vertical_fov": getattr(spec, "vertical_fov", None),
            "range": getattr(spec, "range", None),
            "channels": getattr(spec, "channels", None),
            "points_per_second": getattr(spec, "points_per_second", None),
            "rotation_frequency": getattr(spec, "rotation_frequency", None),
        }
        reading_frequency = getattr(spec, "reading_frequency", None)
        if reading_frequency not in {None, 0}:
            attributes["sensor_tick"] = 1.0 / float(reading_frequency)

        for key, value in attributes.items():
            if value is None:
                continue
            self._set_blueprint_attribute(blueprint, key, value)

        extra_attributes = getattr(spec, "attributes", {}) or {}
        if isinstance(extra_attributes, dict):
            for key, value in extra_attributes.items():
                self._set_blueprint_attribute(blueprint, str(key), value)

    def _set_blueprint_attribute(self, blueprint: Any, key: str, value: Any) -> None:
        if not blueprint.has_attribute(key):
            return
        blueprint.set_attribute(key, str(value))

    def _build_sensor_callback(
        self, *, sensor_id: str, sensor_type: str, output_dir: Path
    ):
        def _callback(measurement: Any) -> None:
            try:
                self._persist_measurement(
                    sensor_id=sensor_id,
                    sensor_type=sensor_type,
                    output_dir=output_dir,
                    measurement=measurement,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("sensor recorder failed for %s: %s", sensor_id, exc)

        return _callback

    def _persist_measurement(
        self,
        *,
        sensor_id: str,
        sensor_type: str,
        output_dir: Path,
        measurement: Any,
    ) -> None:
        frame = int(getattr(measurement, "frame", 0))
        timestamp = float(getattr(measurement, "timestamp", 0.0))

        if sensor_type.startswith("sensor.camera."):
            image_path = output_dir / f"frame_{frame:06d}.png"
            if hasattr(measurement, "save_to_disk"):
                measurement.save_to_disk(str(image_path))
            else:
                image_path.write_bytes(bytes(getattr(measurement, "raw_data", b"")))
            return

        if sensor_type.startswith("sensor.lidar."):
            lidar_path = output_dir / f"frame_{frame:06d}.bin"
            lidar_path.write_bytes(bytes(getattr(measurement, "raw_data", b"")))
            return

        if sensor_type == "sensor.other.radar":
            detections: list[dict[str, float]] = []
            for detection in measurement:
                detections.append(
                    {
                        "altitude": float(detection.altitude),
                        "azimuth": float(detection.azimuth),
                        "depth": float(detection.depth),
                        "velocity": float(detection.velocity),
                    }
                )
            self._append_jsonl(
                sensor_id,
                output_dir,
                {
                    "frame": frame,
                    "timestamp": timestamp,
                    "detections": detections,
                },
            )
            return

        if sensor_type == "sensor.other.gnss":
            self._append_jsonl(
                sensor_id,
                output_dir,
                {
                    "frame": frame,
                    "timestamp": timestamp,
                    "latitude": float(measurement.latitude),
                    "longitude": float(measurement.longitude),
                    "altitude": float(measurement.altitude),
                },
            )
            return

        if sensor_type == "sensor.other.imu":
            self._append_jsonl(
                sensor_id,
                output_dir,
                {
                    "frame": frame,
                    "timestamp": timestamp,
                    "accelerometer": {
                        "x": float(measurement.accelerometer.x),
                        "y": float(measurement.accelerometer.y),
                        "z": float(measurement.accelerometer.z),
                    },
                    "gyroscope": {
                        "x": float(measurement.gyroscope.x),
                        "y": float(measurement.gyroscope.y),
                        "z": float(measurement.gyroscope.z),
                    },
                    "compass": float(measurement.compass),
                },
            )
            return

        if sensor_type == "sensor.opendrive_map":
            opendrive_path = output_dir / "opendrive.xml"
            payload = getattr(measurement, "opendrive", None)
            if payload is None:
                payload = str(measurement)
            opendrive_path.write_text(str(payload), encoding="utf-8")
            return

        raw_path = output_dir / f"frame_{frame:06d}.bin"
        if hasattr(measurement, "raw_data"):
            raw_path.write_bytes(bytes(getattr(measurement, "raw_data", b"")))
            return

        self._append_jsonl(
            sensor_id,
            output_dir,
            {
                "frame": frame,
                "timestamp": timestamp,
                "repr": repr(measurement),
            },
        )

    def _append_jsonl(self, sensor_id: str, output_dir: Path, payload: dict[str, Any]) -> None:
        with self._lock:
            handle = self._jsonl_handles.get(sensor_id)
            if handle is None:
                jsonl_path = output_dir / "records.jsonl"
                handle = jsonl_path.open("a", encoding="utf-8")
                self._jsonl_handles[sensor_id] = handle
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")
            handle.flush()


def run_sensor_recorder_worker(
    *,
    host: str,
    port: int,
    timeout_seconds: float,
    output_root: Path,
    descriptor_path: Path,
    state_path: Path,
    hero_role_name: str = "hero",
) -> int:
    from app.scenario.validators import validate_descriptor

    stop_requested = threading.Event()
    recorder: SensorRecorder | None = None

    def _request_stop(_signum: int, _frame: Any) -> None:
        stop_requested.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("sensor recorder descriptor must be a mapping")
        descriptor = validate_descriptor(payload)
        recorder = SensorRecorder(
            host=host,
            port=port,
            timeout_seconds=timeout_seconds,
            output_root=output_root,
        )
        result = recorder.start(descriptor, hero_role_name=hero_role_name)
        _write_worker_state(
            state_path,
            {
                "status": "ready",
                "profile_name": result.profile_name,
                "sensor_count": result.sensor_count,
                "output_root": str(result.output_root),
            },
        )
        while not stop_requested.wait(0.5):
            pass
        return 0
    except Exception as exc:  # noqa: BLE001
        _write_worker_state(
            state_path,
            {
                "status": "error",
                "error": str(exc),
            },
        )
        return 1
    finally:
        if recorder is not None:
            try:
                recorder.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("sensor recorder worker cleanup failed: %s", exc)
        if stop_requested.is_set():
            _write_worker_state(
                state_path,
                {
                    "status": "stopped",
                },
            )


def _write_worker_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CARLA sensor recorder worker")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--descriptor-path", type=Path, required=True)
    parser.add_argument("--state-path", type=Path, required=True)
    parser.add_argument("--hero-role-name", default="hero")
    args = parser.parse_args(argv)

    return run_sensor_recorder_worker(
        host=args.host,
        port=args.port,
        timeout_seconds=args.timeout_seconds,
        output_root=args.output_root,
        descriptor_path=args.descriptor_path,
        state_path=args.state_path,
        hero_role_name=args.hero_role_name,
    )


if __name__ == "__main__":
    raise SystemExit(main())
