from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc

SENSOR_CAPTURE_STATUS_DISABLED = "DISABLED"
SENSOR_CAPTURE_STATUS_STOPPED = "STOPPED"
SENSOR_CAPTURE_STATUS_STARTING = "STARTING"
SENSOR_CAPTURE_STATUS_RUNNING = "RUNNING"
SENSOR_CAPTURE_STATUS_STOPPING = "STOPPING"
SENSOR_CAPTURE_STATUS_ERROR = "ERROR"

RECORDER_STATUS_DISABLED = "DISABLED"
RECORDER_STATUS_STOPPED = "STOPPED"
RECORDER_STATUS_STARTING = "STARTING"
RECORDER_STATUS_RUNNING = "RUNNING"
RECORDER_STATUS_ERROR = "ERROR"


class RunControlStore:
    def __init__(self, controls_root: Path) -> None:
        self._controls_root = ensure_dir(controls_root)

    def _path(self, run_id: str) -> Path:
        return self._controls_root / f"{run_id}.json"

    def get(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._path(run_id)
        payload_to_write = {**payload, "updated_at_utc": now_utc().isoformat()}
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload_to_write, handle, indent=2, ensure_ascii=False)
        return payload_to_write

    def update(self, run_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        merged = _deep_merge(self.get(run_id), patch)
        return self.save(run_id, merged)


def build_default_sensor_capture_control(
    descriptor: dict[str, Any],
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    sensors = descriptor.get("sensors", {})
    if not isinstance(sensors, dict):
        sensors = {}
    sensor_items = sensors.get("sensors", [])
    if not isinstance(sensor_items, list):
        sensor_items = []

    enabled = bool(sensors.get("enabled")) and (
        bool(sensor_items) or bool(str(sensors.get("profile_name") or "").strip())
    )
    auto_start = bool(sensors.get("auto_start", False))
    desired_state = "RUNNING" if enabled and auto_start else "STOPPED"
    worker_root = output_root / "_worker" if output_root is not None else None
    return {
        "enabled": enabled,
        "auto_start": auto_start,
        "desired_state": desired_state,
        "active": False,
        "status": SENSOR_CAPTURE_STATUS_STOPPED if enabled else SENSOR_CAPTURE_STATUS_DISABLED,
        "profile_name": str(sensors.get("profile_name") or "").strip() or None,
        "sensor_count": len(sensor_items),
        "output_root": str(output_root) if output_root is not None else None,
        "manifest_path": str(output_root / "manifest.json") if output_root is not None else None,
        "manifest": None,
        "saved_frames": 0,
        "saved_samples": 0,
        "sensor_outputs": [],
        "worker_state_path": (str(worker_root / "state.json") if worker_root is not None else None),
        "worker_log_path": (str(worker_root / "worker.log") if worker_root is not None else None),
        "worker_log_tail": None,
        "download_url": None,
        "last_error": None,
        "updated_at_utc": None,
    }


def build_default_recorder_control(
    run_id: str,
    descriptor: dict[str, Any],
    *,
    recorder_path: Path | None = None,
) -> dict[str, Any]:
    recorder = descriptor.get("recorder", {})
    if not isinstance(recorder, dict):
        recorder = {}
    enabled = bool(recorder.get("enabled"))
    return {
        "enabled": enabled,
        "active": False,
        "status": RECORDER_STATUS_STOPPED if enabled else RECORDER_STATUS_DISABLED,
        "output_path": str(recorder_path) if recorder_path is not None else None,
        "last_error": None,
        "updated_at_utc": None,
    }


def _resolve_output_root_path(
    raw_output_root: Any,
    *,
    default_output_root: Path,
) -> Path:
    if raw_output_root is None:
        return default_output_root
    normalized = str(raw_output_root).strip()
    if not normalized:
        return default_output_root
    return Path(normalized).expanduser()


def _read_json_mapping(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return copy.deepcopy(payload) if isinstance(payload, dict) else None


def _tail_text(path: Path, max_lines: int = 8) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    tail = " | ".join(line.strip() for line in lines[-max_lines:] if line.strip())
    return tail or None


def _count_non_empty_lines(path: Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _summarize_sensor_output_dir(output_root: Path, sensor_dir: Path) -> dict[str, Any]:
    file_count = 0
    frame_file_count = 0
    record_count = 0
    single_file_count = 0
    latest_artifact_path: str | None = None
    latest_artifact_mtime_ns = -1

    for path in sorted(sensor_dir.rglob("*")):
        if not path.is_file():
            continue
        file_count += 1
        if path.name == "records.jsonl":
            record_count += _count_non_empty_lines(path)
        elif path.name.startswith("frame_"):
            frame_file_count += 1
        else:
            single_file_count += 1

        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            mtime_ns = -1
        if mtime_ns > latest_artifact_mtime_ns:
            latest_artifact_mtime_ns = mtime_ns
            latest_artifact_path = path.relative_to(output_root).as_posix()

    sample_count = frame_file_count + record_count + single_file_count
    return {
        "sensor_id": sensor_dir.name,
        "relative_dir": sensor_dir.relative_to(output_root).as_posix(),
        "sample_count": sample_count,
        "file_count": file_count,
        "frame_file_count": frame_file_count,
        "record_count": record_count,
        "latest_artifact_path": latest_artifact_path,
    }


def _build_sensor_capture_artifact_summary(
    run_id: str,
    *,
    output_root: Path,
) -> dict[str, Any]:
    manifest_path = output_root / "manifest.json"
    worker_root = output_root / "_worker"
    worker_state_path = worker_root / "state.json"
    worker_log_path = worker_root / "worker.log"

    sensor_outputs: list[dict[str, Any]] = []
    saved_samples = 0
    saved_frames = 0

    if output_root.exists() and output_root.is_dir():
        for path in sorted(output_root.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_dir() or path.name == "_worker":
                continue
            summary = _summarize_sensor_output_dir(output_root, path)
            sensor_outputs.append(summary)
            saved_samples += int(summary["sample_count"])
            saved_frames = max(saved_frames, int(summary["sample_count"]))

    return {
        "output_root": str(output_root),
        "manifest_path": str(manifest_path),
        "manifest": _read_json_mapping(manifest_path),
        "saved_frames": saved_frames,
        "saved_samples": saved_samples,
        "sensor_outputs": sensor_outputs,
        "worker_state_path": str(worker_state_path),
        "worker_log_path": str(worker_log_path),
        "worker_log_tail": _tail_text(worker_log_path),
        "download_url": (
            f"/runs/{run_id}/sensor-capture/download"
            if output_root.exists() and output_root.is_dir()
            else None
        ),
    }


def build_resolved_runtime_control(
    run_id: str,
    descriptor: dict[str, Any],
    persisted: dict[str, Any] | None,
    *,
    artifact_run_dir: Path,
) -> dict[str, Any]:
    state = copy.deepcopy(persisted) if isinstance(persisted, dict) else {}
    default_sensor_output_root = artifact_run_dir / "outputs" / "sensors"
    sensor_capture = build_default_sensor_capture_control(
        descriptor,
        output_root=default_sensor_output_root,
    )
    sensor_capture.update(_coerce_mapping(state.get("sensor_capture")))
    resolved_output_root = _resolve_output_root_path(
        sensor_capture.get("output_root"),
        default_output_root=default_sensor_output_root,
    )
    sensor_capture.update(
        _build_sensor_capture_artifact_summary(
            run_id,
            output_root=resolved_output_root,
        )
    )

    recorder = build_default_recorder_control(
        run_id,
        descriptor,
        recorder_path=artifact_run_dir / "recorder" / f"{run_id}.log",
    )
    recorder.update(_coerce_mapping(state.get("recorder")))

    return {
        "weather": state.get("weather"),
        "debug": state.get("debug"),
        "sensor_capture": sensor_capture,
        "recorder": recorder,
        "updated_at_utc": state.get("updated_at_utc"),
    }


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged
