from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from app.api.routes_runs import (
    get_artifact_store,
    get_control_store,
    get_run_manager,
    raise_http_error,
    run_to_payload,
)
from app.api.routes_sensor_profiles import (
    get_sensor_profile_store,
    sensor_profile_to_descriptor_config,
    sensor_profile_to_payload,
)
from app.api.schemas import (
    RecordingReplayRunPayload,
    ScenarioRecordingDetailPayload,
    ScenarioRecordingDetailResponse,
    ScenarioRecordingLaunchPayload,
    ScenarioRecordingLaunchRequest,
    ScenarioRecordingLaunchResponse,
    ScenarioRecordingListPayload,
    ScenarioRecordingListResponse,
    ScenarioRecordingPayload,
    ScenarioRecordingPublishRequest,
    ScenarioRecordingResponse,
)
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, ValidationError
from app.core.models import RecordingReplayRunRecord, ScenarioRecordingRecord
from app.scenario.library import get_scenario_catalog_item
from app.storage.run_control_store import build_resolved_runtime_control
from app.storage.scenario_recording_store import ScenarioRecordingStore, build_recording_id
from app.storage.scenario_source_store import ScenarioSourceStore
from app.utils.time_utils import now_utc, to_iso8601

router = APIRouter(tags=["场景资产库"])

REPLAY_LAUNCH_MODE = "carla_recorder_replay"
REPLAY_SENSOR_MODE = "carla_live"
FALLBACK_REPLAY_SCENARIO_NAME = "free_drive_sensor_collection"


@lru_cache(maxsize=1)
def get_scenario_recording_store() -> ScenarioRecordingStore:
    settings = get_settings()
    return ScenarioRecordingStore(settings.scenario_recordings_root)


@lru_cache(maxsize=1)
def get_scenario_source_store() -> ScenarioSourceStore:
    settings = get_settings()
    return ScenarioSourceStore(settings.scenario_recordings_root)


def _unique_text(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        candidate = str(value).strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized


def _recording_to_payload(recording: ScenarioRecordingRecord) -> ScenarioRecordingPayload:
    return ScenarioRecordingPayload(
        recording_id=recording.recording_id,
        name=recording.name,
        source_run_id=recording.source_run_id,
        source_run_status=recording.source_run_status,
        source_id=recording.source_id,
        source_provider=recording.source_provider,
        materialization_id=recording.materialization_id,
        source_type=recording.source_type,
        source_ref=recording.source_ref,
        scenario_name=recording.scenario_name,
        map_name=recording.map_name,
        carla_version=recording.carla_version,
        map_version=recording.map_version,
        recorder_log_path=recording.recorder_log_path,
        recorder_file_size_bytes=recording.recorder_file_size_bytes,
        recorder_file_sha256=recording.recorder_file_sha256,
        duration_seconds=recording.duration_seconds,
        recommended_start_seconds=recording.recommended_start_seconds,
        recommended_duration_seconds=recording.recommended_duration_seconds,
        tags=recording.tags,
        corner_case_labels=recording.corner_case_labels,
        weather=recording.weather,
        traffic_density=recording.traffic_density,
        sensor_profile_name=recording.sensor_profile_name,
        determinism_level=recording.determinism_level,
        notes=recording.notes,
        created_at_utc=to_iso8601(recording.created_at),
        updated_at_utc=to_iso8601(recording.updated_at),
    )


def _replay_run_to_payload(replay_run: RecordingReplayRunRecord) -> RecordingReplayRunPayload:
    return RecordingReplayRunPayload(
        recording_id=replay_run.recording_id,
        run_id=replay_run.run_id,
        start_seconds=replay_run.start_seconds,
        duration_seconds=replay_run.duration_seconds,
        sensor_mode=replay_run.sensor_mode,
        sensor_profile_id=replay_run.sensor_profile_id,
        sensor_profile_hash=replay_run.sensor_profile_hash,
        sensor_profile_snapshot=replay_run.sensor_profile_snapshot,
        preview_sensor_id=replay_run.preview_sensor_id,
        preview_sensor_snapshot=replay_run.preview_sensor_snapshot,
        fixed_delta_seconds=replay_run.fixed_delta_seconds,
        sensor_warmup_seconds=replay_run.sensor_warmup_seconds,
        timebase=replay_run.timebase,
        hil_clock_mode=replay_run.hil_clock_mode,
        output_config_summary=replay_run.output_config_summary,
        report_config_summary=replay_run.report_config_summary,
        created_at_utc=to_iso8601(replay_run.created_at),
    )


def _runtime_recorder_path(run_id: str, run_descriptor: dict[str, Any]) -> Path | None:
    artifact_store = get_artifact_store()
    runtime_control = build_resolved_runtime_control(
        run_id,
        run_descriptor,
        get_control_store().get(run_id),
        artifact_run_dir=artifact_store.run_dir(run_id),
    )
    recorder_control = runtime_control.get("recorder")
    if not isinstance(recorder_control, dict):
        return None
    raw_path = str(recorder_control.get("output_path") or "").strip()
    return Path(raw_path) if raw_path else None


def _source_tags(run_descriptor: dict[str, Any]) -> list[str]:
    metadata = run_descriptor.get("metadata", {})
    if not isinstance(metadata, dict):
        return []
    tags = metadata.get("tags")
    if not isinstance(tags, list):
        return []
    return _unique_text([str(tag) for tag in tags])


def _sensor_profile_name(run_descriptor: dict[str, Any]) -> str | None:
    sensors = run_descriptor.get("sensors", {})
    if not isinstance(sensors, dict):
        return None
    value = sensors.get("profile_name")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _traffic_density(run_descriptor: dict[str, Any]) -> dict[str, Any]:
    traffic = run_descriptor.get("traffic", {})
    if not isinstance(traffic, dict):
        return {}
    return {
        "enabled": bool(traffic.get("enabled", False)),
        "num_vehicles": int(traffic.get("num_vehicles") or 0),
        "num_walkers": int(traffic.get("num_walkers") or 0),
        "seed": traffic.get("seed"),
        "injection_mode": traffic.get("injection_mode"),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _catalog_scenario_name_for_replay(recording: ScenarioRecordingRecord) -> str:
    candidate = str(recording.scenario_name or "").strip()
    if candidate and get_scenario_catalog_item(candidate) is not None:
        return candidate
    return FALLBACK_REPLAY_SCENARIO_NAME


def _build_local_recording_descriptor(recording: ScenarioRecordingRecord) -> dict[str, Any]:
    weather = dict(recording.weather or {})
    weather.setdefault("preset", "ClearNoon")
    return {
        "version": 1,
        "scenario_name": _catalog_scenario_name_for_replay(recording),
        "map_name": recording.map_name,
        "weather": weather,
        "sync": {"enabled": True, "fixed_delta_seconds": 0.05},
        "ego_vehicle": {
            "blueprint": "vehicle.tesla.model3",
            "spawn_point": {
                "x": 0.0,
                "y": 0.0,
                "z": 0.5,
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 0.0,
            },
        },
        "traffic": {
            "enabled": False,
            "num_vehicles": 0,
            "num_walkers": 0,
            "injection_mode": "carla_recorder_replay",
        },
        "sensors": {"enabled": False, "auto_start": False, "sensors": []},
        "termination": {"timeout_seconds": 30, "success_condition": "timeout"},
        "recorder": {"enabled": False},
        "debug": {"viewer_friendly": True},
        "metadata": {
            "author": "scenario_recording_importer",
            "tags": recording.tags,
            "description": f"Recorder replay asset imported from {recording.recording_id}",
            "recording_id": recording.recording_id,
            "asset_scenario_name": recording.scenario_name,
            "source_type": recording.source_type,
            "source_ref": recording.source_ref,
        },
    }


def _default_replay_hil_config(hil_output_mode: str | None) -> dict[str, Any]:
    mode = str(hil_output_mode or "").strip() or "camera_open_loop"
    return {"mode": mode}


def _resolve_preview_sensor(
    sensor_profile_id: str,
    sensors: list[dict[str, Any]],
    requested_sensor_id: str | None,
) -> dict[str, Any]:
    rgb_sensors = [
        dict(sensor)
        for sensor in sensors
        if str(sensor.get("type") or "").strip() == "sensor.camera.rgb"
    ]
    if not rgb_sensors:
        raise ValidationError(
            f"Sensor profile {sensor_profile_id} does not contain a sensor.camera.rgb preview sensor"
        )

    if requested_sensor_id is None:
        return rgb_sensors[0]

    for sensor in sensors:
        if str(sensor.get("id") or "").strip() != requested_sensor_id:
            continue
        if str(sensor.get("type") or "").strip() != "sensor.camera.rgb":
            raise ValidationError(
                f"preview_sensor_id must reference a sensor.camera.rgb entry: {requested_sensor_id}"
            )
        return dict(sensor)

    raise ValidationError(
        f"preview_sensor_id not found in sensor profile {sensor_profile_id}: {requested_sensor_id}"
    )


def _build_replay_descriptor(
    source_descriptor: dict[str, Any],
    recording: ScenarioRecordingRecord,
    request: ScenarioRecordingLaunchRequest,
    *,
    sensor_profile_config: dict[str, Any],
    fixed_delta_seconds: float,
) -> dict[str, Any]:
    descriptor = dict(source_descriptor)
    descriptor["map_name"] = recording.map_name
    descriptor["sync"] = {
        **dict(descriptor.get("sync") or {}),
        "enabled": True,
        "fixed_delta_seconds": fixed_delta_seconds,
    }
    descriptor["sensors"] = sensor_profile_config
    descriptor["traffic"] = {
        **dict(descriptor.get("traffic") or {}),
        "enabled": False,
        "num_vehicles": 0,
        "num_walkers": 0,
        "injection_mode": "carla_recorder_replay",
    }
    descriptor["recorder"] = {"enabled": False}
    descriptor["termination"] = {
        **dict(descriptor.get("termination") or {}),
        "timeout_seconds": max(
            1, int(math.ceil(request.duration_seconds + request.sensor_warmup_seconds))
        ),
        "success_condition": "timeout",
    }

    source_metadata = dict(descriptor.get("metadata") or {})
    request_metadata = (
        request.metadata.model_dump(mode="json", exclude_none=True)
        if request.metadata is not None
        else {}
    )
    merged_tags = _unique_text(
        [
            *[str(tag) for tag in source_metadata.get("tags", []) if isinstance(tag, str)],
            "scenario_recording_replay",
            f"recording:{recording.recording_id}",
            f"source_run:{recording.source_run_id}",
            *[str(tag) for tag in request_metadata.get("tags", []) if isinstance(tag, str)],
        ]
    )
    descriptor["metadata"] = {
        **source_metadata,
        **request_metadata,
        "tags": merged_tags,
        "description": request_metadata.get("description")
        or source_metadata.get("description")
        or f"Recorder replay from {recording.recording_id}",
    }
    return descriptor


def _build_replay_source(
    recording: ScenarioRecordingRecord,
    request: ScenarioRecordingLaunchRequest,
    *,
    sensor_profile_snapshot: dict[str, Any],
    preview_sensor_snapshot: dict[str, Any],
    fixed_delta_seconds: float,
) -> dict[str, Any]:
    return {
        "provider": "carla_recorder",
        "launch_mode": REPLAY_LAUNCH_MODE,
        "recording_id": recording.recording_id,
        "source_run_id": recording.source_run_id,
        "recorder_log_path": recording.recorder_log_path,
        "start_seconds": request.start_seconds,
        "duration_seconds": request.duration_seconds,
        "replay_start_seconds": request.start_seconds,
        "replay_duration_seconds": request.duration_seconds,
        "replay_sensor_mode": request.sensor_mode,
        "fixed_delta_seconds": fixed_delta_seconds,
        "replay_fixed_delta_seconds": fixed_delta_seconds,
        "replay_sensors": False,
        "sensor_profile_id": sensor_profile_snapshot["sensor_profile_id"],
        "sensor_profile_hash": sensor_profile_snapshot["profile_hash"],
        "sensor_profile_snapshot": sensor_profile_snapshot,
        "sensor_profile_name": sensor_profile_snapshot["sensor_profile_id"],
        "preview_sensor_id": preview_sensor_snapshot["id"],
        "preview_sensor_snapshot": preview_sensor_snapshot,
        "sensor_warmup_seconds": request.sensor_warmup_seconds,
        "timebase": request.timebase,
        "hil_clock_mode": request.hil_clock_mode,
        "output_config_summary": request.output_config_summary,
        "report_config_summary": request.report_config_summary,
    }


@router.get(
    "/scenario-recordings",
    response_model=ScenarioRecordingListResponse,
    summary="列出场景资产库 recorder 资产",
)
def list_scenario_recordings(
    map_name: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    corner_case_label: str | None = Query(default=None),
    determinism_level: str | None = Query(default=None),
) -> ScenarioRecordingListResponse:
    store = get_scenario_recording_store()
    recordings = store.list(
        map_name=map_name,
        tag=tag,
        corner_case_label=corner_case_label,
        determinism_level=determinism_level,
    )
    return ScenarioRecordingListResponse(
        success=True,
        data=ScenarioRecordingListPayload(
            recordings=[_recording_to_payload(recording) for recording in recordings]
        ),
    )


@router.post(
    "/scenario-recordings/from-run",
    response_model=ScenarioRecordingResponse,
    summary="从已有 recorder run 发布场景资产",
)
def publish_scenario_recording_from_run(
    request: ScenarioRecordingPublishRequest,
) -> ScenarioRecordingResponse:
    manager = get_run_manager()
    store = get_scenario_recording_store()
    try:
        existing = store.get_by_source_run_id(request.run_id)
        if existing is not None:
            return ScenarioRecordingResponse(
                success=True,
                data=_recording_to_payload(existing),
            )

        run = manager.get_run(request.run_id)
        recorder_path = _runtime_recorder_path(run.run_id, run.descriptor)
        if recorder_path is None or not recorder_path.is_file():
            raise ValidationError(f"Run {run.run_id} 没有可发布的 CARLA recorder 文件")

        stat = recorder_path.stat()
        weather = run.descriptor.get("weather", {})
        source = run.scenario_source or {}
        recorder_sha256 = _sha256_file(recorder_path)
        source_type = request.source_type or str(source.get("provider") or "").strip() or "run"
        source_ref = (
            request.source_ref
            or str(source.get("source_id") or "").strip()
            or str(source.get("source_path") or "").strip()
            or run.run_id
        )
        descriptor_sync = run.descriptor.get("sync", {})
        descriptor_termination = run.descriptor.get("termination", {})
        duration_seconds = request.duration_seconds
        if duration_seconds is None and isinstance(descriptor_termination, dict):
            raw_timeout = descriptor_termination.get("timeout_seconds")
            try:
                duration_seconds = float(raw_timeout) if raw_timeout is not None else None
            except (TypeError, ValueError):
                duration_seconds = None
        map_version = request.map_version
        if map_version is None and isinstance(descriptor_sync, dict):
            map_version = str(descriptor_sync.get("map_version") or "").strip() or None
        recording = ScenarioRecordingRecord(
            recording_id=build_recording_id(run.run_id),
            name=request.name or run.scenario_name,
            source_run_id=run.run_id,
            source_run_status=run.status.value,
            source_id=str(source.get("source_id") or "").strip() or None,
            source_provider=str(source.get("provider") or "").strip() or None,
            materialization_id=str(source.get("materialization_id") or "").strip() or None,
            source_type=source_type,
            source_ref=source_ref,
            scenario_name=run.scenario_name,
            map_name=run.map_name,
            carla_version=request.carla_version,
            map_version=map_version,
            recorder_log_path=str(recorder_path),
            recorder_file_size_bytes=int(stat.st_size),
            recorder_file_sha256=recorder_sha256,
            duration_seconds=duration_seconds,
            recommended_start_seconds=request.recommended_start_seconds,
            recommended_duration_seconds=request.recommended_duration_seconds,
            tags=_unique_text([*_source_tags(run.descriptor), *request.tags]),
            corner_case_labels=request.corner_case_labels,
            weather=weather if isinstance(weather, dict) else {},
            traffic_density=_traffic_density(run.descriptor),
            sensor_profile_name=_sensor_profile_name(run.descriptor),
            determinism_level=request.determinism_level,
            notes=request.notes,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        recording = store.create(recording)
        if recording.materialization_id:
            try:
                get_scenario_source_store().update_materialization(
                    recording.materialization_id,
                    status="published_asset_available",
                    recording_id=recording.recording_id,
                    recorder_file_sha256=recorder_sha256,
                    completed_at=now_utc(),
                )
            except AppError:
                pass
    except AppError as exc:
        raise_http_error(exc)

    return ScenarioRecordingResponse(success=True, data=_recording_to_payload(recording))


@router.get(
    "/scenario-recordings/{recording_id}",
    response_model=ScenarioRecordingDetailResponse,
    summary="读取场景资产详情",
)
def get_scenario_recording(recording_id: str) -> ScenarioRecordingDetailResponse:
    store = get_scenario_recording_store()
    try:
        recording = store.get(recording_id)
        replay_runs = store.list_replay_runs(recording_id)
    except AppError as exc:
        raise_http_error(exc)
    return ScenarioRecordingDetailResponse(
        success=True,
        data=ScenarioRecordingDetailPayload(
            recording=_recording_to_payload(recording),
            replay_runs=[_replay_run_to_payload(replay_run) for replay_run in replay_runs],
        ),
    )


@router.post(
    "/scenario-recordings/{recording_id}/launch",
    response_model=ScenarioRecordingLaunchResponse,
    summary="从场景资产创建 recorder replay run",
)
def launch_scenario_recording(
    recording_id: str,
    request: ScenarioRecordingLaunchRequest,
) -> ScenarioRecordingLaunchResponse:
    manager = get_run_manager()
    store = get_scenario_recording_store()
    try:
        recording = store.get(recording_id)
        recorder_path = Path(recording.recorder_log_path)
        if not recorder_path.is_file():
            raise ValidationError(
                f"Recorder log 不存在，无法创建 replay run: {recording.recorder_log_path}"
            )

        sensor_profile = get_sensor_profile_store().get(request.sensor_profile_id)
        sensor_profile_payload = sensor_profile_to_payload(sensor_profile).model_dump(mode="json")
        preview_sensor_snapshot = _resolve_preview_sensor(
            sensor_profile.sensor_profile_id,
            sensor_profile.sensors,
            request.preview_sensor_id,
        )
        fixed_delta_seconds = (
            float(request.fixed_delta_seconds)
            if request.fixed_delta_seconds is not None
            else float(sensor_profile.fixed_delta_seconds)
        )
        source_hil_config: dict[str, Any] | None
        source_evaluation_profile: dict[str, Any] | None
        try:
            source_run = manager.get_run(recording.source_run_id)
            source_descriptor = source_run.descriptor
            source_hil_config = source_run.hil_config or _default_replay_hil_config(
                sensor_profile.hil_output_mode
            )
            source_evaluation_profile = source_run.evaluation_profile
        except NotFoundError:
            source_descriptor = _build_local_recording_descriptor(recording)
            source_hil_config = _default_replay_hil_config(sensor_profile.hil_output_mode)
            source_evaluation_profile = None
        descriptor = _build_replay_descriptor(
            source_descriptor,
            recording,
            request,
            sensor_profile_config=sensor_profile_to_descriptor_config(
                sensor_profile,
                auto_start=False,
            ),
            fixed_delta_seconds=fixed_delta_seconds,
        )
        scenario_source = _build_replay_source(
            recording,
            request,
            sensor_profile_snapshot=sensor_profile_payload,
            preview_sensor_snapshot=preview_sensor_snapshot,
            fixed_delta_seconds=fixed_delta_seconds,
        )
        run = manager.create_run(
            descriptor_payload=descriptor,
            hil_config=source_hil_config,
            evaluation_profile=source_evaluation_profile,
            execution_backend="native",
            scenario_source=scenario_source,
            config_snapshot_extra={
                "recording_replay": {
                    "recording_id": recording.recording_id,
                    "source_run_id": recording.source_run_id,
                    "sensor_mode": request.sensor_mode,
                    "sensor_profile_id": sensor_profile.sensor_profile_id,
                    "sensor_profile_hash": sensor_profile.profile_hash,
                    "sensor_profile_snapshot": sensor_profile_payload,
                    "preview_sensor_id": preview_sensor_snapshot["id"],
                    "preview_sensor_snapshot": preview_sensor_snapshot,
                    "sensor_warmup_seconds": request.sensor_warmup_seconds,
                    "timebase": request.timebase,
                    "hil_clock_mode": request.hil_clock_mode,
                    "fixed_delta_seconds": fixed_delta_seconds,
                    "start_seconds": request.start_seconds,
                    "duration_seconds": request.duration_seconds,
                    "output_config_summary": request.output_config_summary,
                    "report_config_summary": request.report_config_summary,
                }
            },
        )
        store.create_replay_run(
            RecordingReplayRunRecord(
                recording_id=recording.recording_id,
                run_id=run.run_id,
                start_seconds=request.start_seconds,
                duration_seconds=request.duration_seconds,
                sensor_mode=request.sensor_mode,
                sensor_profile_id=sensor_profile.sensor_profile_id,
                sensor_profile_hash=sensor_profile.profile_hash,
                sensor_profile_snapshot=sensor_profile_payload,
                preview_sensor_id=str(preview_sensor_snapshot["id"]),
                preview_sensor_snapshot=preview_sensor_snapshot,
                fixed_delta_seconds=fixed_delta_seconds,
                sensor_warmup_seconds=request.sensor_warmup_seconds,
                timebase=request.timebase,
                hil_clock_mode=request.hil_clock_mode,
                output_config_summary=request.output_config_summary,
                report_config_summary=request.report_config_summary,
                created_at=now_utc(),
            )
        )
        if request.auto_start:
            run = manager.start_run(run.run_id)
    except AppError as exc:
        raise_http_error(exc)

    return ScenarioRecordingLaunchResponse(
        success=True,
        data=ScenarioRecordingLaunchPayload(
            recording=_recording_to_payload(recording),
            run=run_to_payload(run),
        ),
    )
