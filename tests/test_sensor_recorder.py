from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.executor.sensor_recorder import SensorRecorder, SensorRecorderProcess
from app.scenario.validators import validate_descriptor


class FakeHandle:
    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    def close(self) -> None:
        self._events.append(f"close:{self._name}")


class FakeSensorActor:
    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    def listen(self, callback) -> None:
        assert callable(callback)
        self._events.append(f"listen:{self._name}")

    def stop(self) -> None:
        self._events.append(f"stop:{self._name}")

    def destroy(self) -> None:
        self._events.append(f"destroy:{self._name}")


def test_sensor_recorder_stop_detaches_callbacks_before_destroy(
    tmp_path: Path, monkeypatch
) -> None:
    events: list[str] = []
    recorder = SensorRecorder(
        host="127.0.0.1",
        port=2000,
        timeout_seconds=10.0,
        output_root=tmp_path,
    )
    recorder._jsonl_handles = {
        "front": FakeHandle(events, "front"),
        "rear": FakeHandle(events, "rear"),
    }
    recorder._spawned_sensors = [
        FakeSensorActor(events, "front"),
        FakeSensorActor(events, "rear"),
    ]
    recorder._hero_actor = object()
    recorder._world = object()
    recorder._client = object()
    recorder._carla = object()

    monkeypatch.setattr(
        "app.executor.sensor_recorder.time.sleep",
        lambda seconds: events.append(f"sleep:{seconds}"),
    )

    recorder.stop()

    assert events == [
        "close:front",
        "close:rear",
        "listen:rear",
        "stop:rear",
        "listen:front",
        "stop:front",
        "sleep:0.2",
        "destroy:rear",
        "destroy:front",
    ]
    assert recorder._spawned_sensors == []
    assert recorder._jsonl_handles == {}
    assert recorder._hero_actor is None
    assert recorder._world is None
    assert recorder._client is None
    assert recorder._carla is None


def _build_descriptor() -> object:
    return validate_descriptor(
        {
            "version": 1,
            "scenario_name": "free_drive_sensor_collection",
            "map_name": "Town01",
            "weather": {"preset": "ClearNoon"},
            "sync": {"enabled": True, "fixed_delta_seconds": 0.05},
            "ego_vehicle": {
                "blueprint": "vehicle.lincoln.mkz_2017",
                "spawn_point": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                },
            },
            "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
            "sensors": {
                "enabled": True,
                "profile_name": "test_profile",
                "sensors": [
                    {
                        "id": "front_rgb",
                        "type": "sensor.camera.rgb",
                        "x": 1.5,
                        "y": 0.0,
                        "z": 1.6,
                        "width": 1280,
                        "height": 720,
                        "fov": 90.0,
                    }
                ],
            },
            "termination": {"timeout_seconds": 30, "success_condition": "timeout"},
            "recorder": {"enabled": False},
            "debug": {"viewer_friendly": False},
            "metadata": {"author": "test", "tags": ["sensor"], "description": "test"},
        }
    )


class FakeReadyWorkerProcess:
    def __init__(self, command, *, stdout=None, **kwargs) -> None:
        self.command = command
        self.stdout = stdout
        self.kwargs = kwargs
        self.returncode = None
        state_path = Path(command[command.index("--state-path") + 1])
        output_root = Path(command[command.index("--output-root") + 1])
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "profile_name": "test_profile",
                    "sensor_count": 1,
                    "output_root": str(output_root),
                }
            ),
            encoding="utf-8",
        )

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def wait(self, timeout=None) -> int:
        self.returncode = -15 if self.returncode is None else self.returncode
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class FakeCrashedWorkerProcess:
    def __init__(self, command, *, stdout=None, **kwargs) -> None:
        self.command = command
        self.stdout = stdout
        self.kwargs = kwargs
        self.returncode = 7
        if stdout is not None:
            stdout.write("worker crashed before ready\n")
            stdout.flush()

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        return None

    def wait(self, timeout=None) -> int:
        return self.returncode

    def kill(self) -> None:
        return None


def test_sensor_recorder_process_starts_and_stops_worker(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.executor.sensor_recorder.subprocess.Popen",
        FakeReadyWorkerProcess,
    )

    recorder = SensorRecorderProcess(
        host="127.0.0.1",
        port=2000,
        timeout_seconds=10.0,
        output_root=tmp_path / "outputs" / "sensors",
        python_executable="python-test",
        worker_module="test.worker",
    )

    result = recorder.start(_build_descriptor())

    assert result.profile_name == "test_profile"
    assert result.sensor_count == 1
    assert result.output_root == tmp_path / "outputs" / "sensors"

    descriptor_payload = json.loads(
        (tmp_path / "outputs" / "sensors" / "_worker" / "descriptor.json").read_text(
            encoding="utf-8"
        )
    )
    assert descriptor_payload["sensors"]["profile_name"] == "test_profile"

    recorder.stop()

    assert recorder.unexpected_exit_error() is None


def test_sensor_recorder_process_surfaces_worker_start_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "app.executor.sensor_recorder.subprocess.Popen",
        FakeCrashedWorkerProcess,
    )

    recorder = SensorRecorderProcess(
        host="127.0.0.1",
        port=2000,
        timeout_seconds=10.0,
        output_root=tmp_path / "outputs" / "sensors",
        python_executable="python-test",
        worker_module="test.worker",
    )

    with pytest.raises(RuntimeError, match="worker crashed before ready"):
        recorder.start(_build_descriptor())
