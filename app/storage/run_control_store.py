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

    return {
        "enabled": False,
        "auto_start": False,
        "desired_state": SENSOR_CAPTURE_STATUS_DISABLED,
        "active": False,
        "status": SENSOR_CAPTURE_STATUS_DISABLED,
        "profile_name": str(sensors.get("profile_name") or "").strip() or None,
        "sensor_count": 0,
        "output_root": None,
        "manifest_path": None,
        "manifest": None,
        "saved_frames": 0,
        "saved_samples": 0,
        "sensor_outputs": [],
        "worker_state_path": None,
        "worker_log_path": None,
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
