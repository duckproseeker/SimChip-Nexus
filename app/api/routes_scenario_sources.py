from __future__ import annotations

import copy
import hashlib
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from app.api.carla_worker_runner import CarlaWorkerError, run_carla_worker
from app.api.routes_runs import get_run_manager, raise_http_error, run_to_payload
from app.api.routes_scenario_recordings import (
    get_scenario_recording_store,
)
from app.api.schemas import (
    ScenarioSourceDetailPayload,
    ScenarioSourceDetailResponse,
    ScenarioSourceLaunchRecordingPayload,
    ScenarioSourceLaunchRecordingRequest,
    ScenarioSourceLaunchRecordingResponse,
    ScenarioSourceListPayload,
    ScenarioSourceListResponse,
    ScenarioSourceMaterializationListResponse,
    ScenarioSourceMaterializationPayload,
    ScenarioSourceMaterializationSummaryPayload,
    ScenarioSourcePayload,
    ScenarioSourceRescanPayload,
    ScenarioSourceRescanResponse,
)
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, ValidationError
from app.core.models import (
    RunStatus,
    ScenarioSourceMaterializationRecord,
    ScenarioSourceRecord,
)
from app.scenario.launch_builder import (
    build_generated_scenario_source,
    build_launch_descriptor,
    write_launch_artifacts,
)
from app.scenario.library import get_scenario_catalog_item
from app.scenario.official_runner import official_preset_index
from app.scenario.sensor_profiles import build_sensor_config_from_profile, get_sensor_profile
from app.scenario.source_discovery import (
    BENCH2DRIVE_PROVIDER,
    OFFICIAL_OPENSCENARIO_PROVIDER,
    discover_scenario_sources,
    sha256_file,
    stable_hash,
)
from app.storage.scenario_source_store import ScenarioSourceStore
from app.utils.time_utils import now_utc, to_iso8601

router = APIRouter(tags=["公共场景源"])

MATERIALIZATION_STATUS_NEVER = "never_recorded"
MATERIALIZATION_STATUS_RUNNING = "recording_running"
MATERIALIZATION_STATUS_RECORDED_UNPUBLISHED = "recorded_unpublished"
MATERIALIZATION_STATUS_PUBLISHED = "published_asset_available"
MATERIALIZATION_STATUS_FAILED = "failed_last_materialization"
MATERIALIZATION_STATUS_INCOMPATIBLE = "incompatible"


@lru_cache(maxsize=1)
def get_scenario_source_store() -> ScenarioSourceStore:
    settings = get_settings()
    return ScenarioSourceStore(settings.scenario_recordings_root)


def _unique_text(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value).strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _hash_jsonish(value: Any) -> str:
    import json

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _materialization_agent_hash(
    *, agent_type: str, source: ScenarioSourceRecord, fixed_delta_seconds: float
) -> str:
    payload = {
        "agent_type": agent_type,
        "version": "materialization_route_follower_v1",
        "source_id": source.source_id,
        "route_id": source.route_id,
        "fixed_delta_seconds": fixed_delta_seconds,
    }
    return _hash_jsonish(payload)


def _materialization_id(source_id: str, run_id: str) -> str:
    return f"mat_{stable_hash(f'{source_id}:{run_id}')[:24]}"


def _source_to_payload(
    source: ScenarioSourceRecord,
    materializations: list[ScenarioSourceMaterializationRecord] | None = None,
) -> ScenarioSourcePayload:
    materialization_summary = _materialization_summary(source, materializations or [])
    return ScenarioSourcePayload(
        source_id=source.source_id,
        provider=source.provider,
        provider_version=source.provider_version,
        source_path=source.source_path,
        source_hash=source.source_hash,
        route_id=source.route_id,
        scenario_type=source.scenario_type,
        map_name=source.map_name,
        weather=source.weather,
        recommended_duration_seconds=source.recommended_duration_seconds,
        corner_case_labels=source.corner_case_labels,
        compatibility_status=source.compatibility_status,
        compatibility_message=source.compatibility_message,
        parsed_metadata=source.parsed_metadata,
        materialization=materialization_summary,
        discovered_at_utc=to_iso8601(source.discovered_at),
        updated_at_utc=to_iso8601(source.updated_at),
    )


def _materialization_to_payload(
    materialization: ScenarioSourceMaterializationRecord,
) -> ScenarioSourceMaterializationPayload:
    return ScenarioSourceMaterializationPayload(
        materialization_id=materialization.materialization_id,
        source_id=materialization.source_id,
        run_id=materialization.run_id,
        recording_id=materialization.recording_id,
        status=materialization.status,
        sensor_profile_id=materialization.sensor_profile_id,
        sensor_profile_hash=materialization.sensor_profile_hash,
        fixed_delta_seconds=materialization.fixed_delta_seconds,
        materialization_agent_type=materialization.materialization_agent_type,
        materialization_agent_hash=materialization.materialization_agent_hash,
        recorder_file_sha256=materialization.recorder_file_sha256,
        started_at_utc=to_iso8601(materialization.started_at),
        completed_at_utc=to_iso8601(materialization.completed_at),
        error_message=materialization.error_message,
        created_at_utc=to_iso8601(materialization.created_at),
        updated_at_utc=to_iso8601(materialization.updated_at),
    )


def _materialization_summary(
    source: ScenarioSourceRecord,
    materializations: list[ScenarioSourceMaterializationRecord],
) -> ScenarioSourceMaterializationSummaryPayload:
    if source.compatibility_status != "ok":
        return ScenarioSourceMaterializationSummaryPayload(
            status=MATERIALIZATION_STATUS_INCOMPATIBLE,
            last_error=source.compatibility_message,
        )
    if not materializations:
        return ScenarioSourceMaterializationSummaryPayload(status=MATERIALIZATION_STATUS_NEVER)
    latest = sorted(materializations, key=lambda item: item.created_at, reverse=True)[0]
    return ScenarioSourceMaterializationSummaryPayload(
        status=latest.status,
        last_run_id=latest.run_id,
        last_recording_id=latest.recording_id,
        last_error=latest.error_message,
        last_materialized_at_utc=to_iso8601(latest.completed_at or latest.started_at),
        sensor_profile_hash=latest.sensor_profile_hash,
        fixed_delta_seconds=latest.fixed_delta_seconds,
    )


def _recording_file_sha256(run_id: str) -> str | None:
    recording = get_scenario_recording_store().get_by_source_run_id(run_id)
    if recording is None:
        return None
    path = Path(recording.recorder_log_path)
    return sha256_file(path) if path.exists() else None


def _refresh_materialization_statuses(
    materializations: list[ScenarioSourceMaterializationRecord],
) -> list[ScenarioSourceMaterializationRecord]:
    manager = get_run_manager()
    store = get_scenario_source_store()
    recording_store = get_scenario_recording_store()
    refreshed: list[ScenarioSourceMaterializationRecord] = []
    active = {RunStatus.CREATED, RunStatus.QUEUED, RunStatus.STARTING, RunStatus.RUNNING, RunStatus.PAUSED}
    terminal_failed = {RunStatus.FAILED, RunStatus.CANCELED}
    for item in materializations:
        updated = item
        try:
            recording = recording_store.get_by_source_run_id(item.run_id)
            if recording is not None:
                updated = store.update_materialization(
                    item.materialization_id,
                    status=MATERIALIZATION_STATUS_PUBLISHED,
                    recording_id=recording.recording_id,
                    recorder_file_sha256=_recording_file_sha256(item.run_id),
                    completed_at=now_utc(),
                )
                refreshed.append(updated)
                continue
            run = manager.get_run(item.run_id)
            if run.status in active:
                next_status = MATERIALIZATION_STATUS_RUNNING
            elif run.status == RunStatus.COMPLETED:
                next_status = MATERIALIZATION_STATUS_RECORDED_UNPUBLISHED
            elif run.status in terminal_failed:
                next_status = MATERIALIZATION_STATUS_FAILED
            else:
                next_status = item.status
            if next_status != item.status or item.error_message != run.error_reason:
                updated = store.update_materialization(
                    item.materialization_id,
                    status=next_status,
                    completed_at=run.ended_at if run.status not in active else None,
                    error_message=run.error_reason,
                )
        except AppError:
            pass
        refreshed.append(updated)
    return refreshed


def _rescan_sources() -> list[ScenarioSourceRecord]:
    store = get_scenario_source_store()
    sources = discover_scenario_sources(get_settings())
    return store.replace_sources(sources)


def _ensure_sources_loaded() -> None:
    store = get_scenario_source_store()
    if store.list():
        return
    _rescan_sources()


def _run_preflight(
    *,
    source: ScenarioSourceRecord,
    sensor_profile_valid: bool,
    fixed_delta_seconds: float,
) -> None:
    settings = get_settings()
    try:
        payload = run_carla_worker(
            "app.api.carla_materialization_preflight_worker",
            {
                "map_name": source.map_name,
                "fixed_delta_seconds": fixed_delta_seconds,
                "recorder_output_dir": str(settings.artifacts_root),
                "sensor_profile_valid": sensor_profile_valid,
            },
            timeout_seconds=max(settings.carla_timeout_seconds, 20.0) + 5.0,
        )
    except CarlaWorkerError as exc:
        raise ConflictError(exc.detail) from exc
    if not bool(payload.get("ok", False)):
        raise ConflictError(str(payload.get("error") or "materialization preflight failed"))


def _sensor_config_and_hash(profile_name: str) -> tuple[dict[str, Any], str]:
    settings = get_settings()
    profile = get_sensor_profile(settings.sensor_profiles_root, profile_name)
    if profile is None:
        raise ValidationError(f"未知传感器模板: {profile_name}")
    config = build_sensor_config_from_profile(settings.sensor_profiles_root, profile_name)
    if config is None:
        raise ValidationError(f"传感器模板不可用: {profile_name}")
    return config, _hash_jsonish(profile)


def _build_materialization_descriptor(
    source: ScenarioSourceRecord,
    request: ScenarioSourceLaunchRecordingRequest,
    sensor_config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = request.metadata.model_dump(mode="json", exclude_none=True) if request.metadata else {}
    tags = _unique_text(
        [
            "scenario_source",
            "materialization",
            source.provider,
            *(metadata.get("tags") if isinstance(metadata.get("tags"), list) else []),
        ]
    )
    if source.provider == OFFICIAL_OPENSCENARIO_PROVIDER:
        preset_id = str(source.route_id or source.scenario_type or "").strip()
        preset = official_preset_index().get(preset_id)
        catalog_item = get_scenario_catalog_item(preset_id)
        if preset is None or catalog_item is None:
            raise ValidationError(f"官方 OpenSCENARIO source 缺少 catalog preset: {preset_id}")
        descriptor = build_launch_descriptor(
            catalog_item,
            map_name=source.map_name,
            weather=source.weather,
            traffic={"num_vehicles": 0, "num_walkers": 0},
            sensors=sensor_config,
            timeout_seconds=int(math.ceil(source.recommended_duration_seconds or 30.0)),
            metadata={
                **metadata,
                "author": metadata.get("author") or "scenario-source-materialization",
                "tags": tags,
                "description": metadata.get("description") or f"Materialize {preset_id}",
            },
        )
        descriptor["sync"] = {"enabled": True, "fixed_delta_seconds": request.fixed_delta_seconds}
        descriptor["recorder"] = {"enabled": True}
        return descriptor, copy.deepcopy(catalog_item)

    catalog_item = get_scenario_catalog_item("public_route_materialization")
    if catalog_item is None:
        raise ValidationError("缺少 public_route_materialization 内部场景模板")
    waypoints = source.parsed_metadata.get("waypoints")
    if not isinstance(waypoints, list) or not waypoints:
        raise ValidationError("route source 未解析到 waypoint，无法 materialize")
    first_waypoint = waypoints[0]
    descriptor = copy.deepcopy(catalog_item["descriptor_template"])
    descriptor["scenario_name"] = "public_route_materialization"
    descriptor["map_name"] = source.map_name
    descriptor["weather"] = copy.deepcopy(source.weather)
    descriptor["sync"] = {"enabled": True, "fixed_delta_seconds": request.fixed_delta_seconds}
    descriptor["ego_vehicle"]["spawn_point"] = copy.deepcopy(first_waypoint)
    descriptor["traffic"] = {
        "enabled": False,
        "num_vehicles": 0,
        "num_walkers": 0,
        "injection_mode": "leaderboard_route_materialization",
    }
    descriptor["sensors"] = sensor_config
    descriptor["termination"] = {
        "timeout_seconds": int(math.ceil(source.recommended_duration_seconds or 60.0)),
        "success_condition": "timeout",
    }
    descriptor["recorder"] = {"enabled": True}
    descriptor["metadata"] = {
        "author": metadata.get("author") or "scenario-source-materialization",
        "tags": tags,
        "description": metadata.get("description") or f"Materialize route {source.route_id}",
    }
    return descriptor, catalog_item


def _build_scenario_source_payload(
    source: ScenarioSourceRecord,
    *,
    materialization_id: str,
    request: ScenarioSourceLaunchRecordingRequest,
    sensor_profile_hash: str,
    materialization_agent_hash: str,
    artifacts_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    launch_mode = (
        "openscenario"
        if source.provider == OFFICIAL_OPENSCENARIO_PROVIDER
        else "leaderboard_route"
    )
    route_xml_path = str(source.parsed_metadata.get("route_xml_path") or "")
    route_xml_hash = str(source.parsed_metadata.get("route_xml_hash") or "")
    payload = dict(artifacts_source or {})
    payload.update(
        {
        "launch_mode": launch_mode,
        "source_id": source.source_id,
        "provider": source.provider,
        "source_config_path": source.source_path,
        "source_config_hash": source.source_hash,
        "route_id": source.route_id,
        "route_xml_path": route_xml_path or None,
        "route_xml_hash": route_xml_hash or None,
        "map": source.map_name,
        "weather_profile": source.weather,
        "corner_case_labels": source.corner_case_labels,
        "materialization": True,
        "materialization_id": materialization_id,
        "sensor_profile_id": request.sensor_profile_name,
        "sensor_profile_hash": sensor_profile_hash,
        "fixed_delta_seconds": request.fixed_delta_seconds,
        "materialization_agent": {
            "type": request.materialization_agent_type,
            "version": "materialization_route_follower_v1",
            "config_hash": materialization_agent_hash,
        },
        "template_params": {"targetSpeedMps": 7.0},
        "route_waypoints": source.parsed_metadata.get("waypoints", []),
        }
    )
    return payload


@router.get(
    "/scenario-sources",
    response_model=ScenarioSourceListResponse,
    summary="列出公共 corner case 场景源",
)
def list_scenario_sources(
    provider: str | None = Query(default=None),
    map_name: str | None = Query(default=None),
    scenario_type: str | None = Query(default=None),
    corner_case_label: str | None = Query(default=None),
    compatibility_status: str | None = Query(default=None),
) -> ScenarioSourceListResponse:
    try:
        _ensure_sources_loaded()
        store = get_scenario_source_store()
        sources = store.list(
            provider=provider,
            map_name=map_name,
            scenario_type=scenario_type,
            corner_case_label=corner_case_label,
            compatibility_status=compatibility_status,
        )
        materializations = _refresh_materialization_statuses(store.list_materializations())
        by_source: dict[str, list[ScenarioSourceMaterializationRecord]] = {}
        for item in materializations:
            by_source.setdefault(item.source_id, []).append(item)
    except AppError as exc:
        raise_http_error(exc)
    return ScenarioSourceListResponse(
        success=True,
        data=ScenarioSourceListPayload(
            sources=[
                _source_to_payload(source, by_source.get(source.source_id, []))
                for source in sources
            ]
        ),
    )


@router.post(
    "/scenario-sources/rescan",
    response_model=ScenarioSourceRescanResponse,
    summary="重新扫描公共场景源目录",
)
def rescan_scenario_sources() -> ScenarioSourceRescanResponse:
    try:
        sources = _rescan_sources()
        store = get_scenario_source_store()
        materializations = _refresh_materialization_statuses(store.list_materializations())
        by_source: dict[str, list[ScenarioSourceMaterializationRecord]] = {}
        for item in materializations:
            by_source.setdefault(item.source_id, []).append(item)
    except AppError as exc:
        raise_http_error(exc)
    payload_sources = [
        _source_to_payload(source, by_source.get(source.source_id, []))
        for source in sources
    ]
    return ScenarioSourceRescanResponse(
        success=True,
        data=ScenarioSourceRescanPayload(
            sources=payload_sources,
            source_count=len(payload_sources),
        ),
    )


@router.get(
    "/scenario-sources/{source_id}",
    response_model=ScenarioSourceDetailResponse,
    summary="读取公共场景源详情",
)
def get_scenario_source(source_id: str) -> ScenarioSourceDetailResponse:
    try:
        _ensure_sources_loaded()
        store = get_scenario_source_store()
        source = store.get(source_id)
        materializations = _refresh_materialization_statuses(
            store.list_materializations(source_id)
        )
    except AppError as exc:
        raise_http_error(exc)
    return ScenarioSourceDetailResponse(
        success=True,
        data=ScenarioSourceDetailPayload(
            source=_source_to_payload(source, materializations),
            materializations=[
                _materialization_to_payload(item) for item in materializations
            ],
        ),
    )


@router.get(
    "/scenario-sources/{source_id}/materializations",
    response_model=ScenarioSourceMaterializationListResponse,
    summary="列出场景源 materialization 历史",
)
def list_source_materializations(source_id: str) -> ScenarioSourceMaterializationListResponse:
    try:
        _ensure_sources_loaded()
        store = get_scenario_source_store()
        store.get(source_id)
        materializations = _refresh_materialization_statuses(
            store.list_materializations(source_id)
        )
    except AppError as exc:
        raise_http_error(exc)
    return ScenarioSourceMaterializationListResponse(
        success=True,
        data=[_materialization_to_payload(item) for item in materializations],
    )


@router.post(
    "/scenario-sources/{source_id}/launch-recording",
    response_model=ScenarioSourceLaunchRecordingResponse,
    summary="从公共场景源创建 recorder materialization run",
)
def launch_source_recording(
    source_id: str,
    request: ScenarioSourceLaunchRecordingRequest,
) -> ScenarioSourceLaunchRecordingResponse:
    manager = get_run_manager()
    store = get_scenario_source_store()
    try:
        _ensure_sources_loaded()
        source = store.get(source_id)
        if source.compatibility_status != "ok":
            raise ConflictError(
                source.compatibility_message
                or f"场景源不兼容: {source.compatibility_status}"
            )
        sensor_config, sensor_profile_hash = _sensor_config_and_hash(
            request.sensor_profile_name
        )
        _run_preflight(
            source=source,
            sensor_profile_valid=True,
            fixed_delta_seconds=request.fixed_delta_seconds,
        )

        descriptor, catalog_item = _build_materialization_descriptor(
            source, request, sensor_config
        )
        run_id = manager.build_run_id()
        artifacts_source: dict[str, Any] | None = None
        if source.provider == OFFICIAL_OPENSCENARIO_PROVIDER:
            artifacts = write_launch_artifacts(
                settings=get_settings(),
                run_id=run_id,
                catalog_item=catalog_item,
                descriptor=descriptor,
                launch_request=request.model_dump(mode="json", exclude_none=True),
                template_params={},
            )
            artifacts_source = build_generated_scenario_source(
                catalog_item, artifacts, {}
            )

        materialization_id = _materialization_id(source.source_id, run_id)
        materialization_agent_hash = _materialization_agent_hash(
            agent_type=request.materialization_agent_type,
            source=source,
            fixed_delta_seconds=request.fixed_delta_seconds,
        )
        scenario_source = _build_scenario_source_payload(
            source,
            materialization_id=materialization_id,
            request=request,
            sensor_profile_hash=sensor_profile_hash,
            materialization_agent_hash=materialization_agent_hash,
            artifacts_source=artifacts_source,
        )
        metadata = descriptor.setdefault("metadata", {})
        metadata["materialization_config_hash"] = _hash_jsonish(scenario_source)
        metadata["carla_version"] = source.provider_version.get("expected_carla_version")
        metadata["scenario_runner_version"] = source.provider_version.get("git_commit")
        metadata["leaderboard_version_or_commit"] = source.provider_version.get(
            "expected_leaderboard_version"
        )
        metadata["bench2drive_version_or_commit"] = (
            source.provider_version.get("git_commit")
            if source.provider == BENCH2DRIVE_PROVIDER
            else None
        )
        metadata["sensor_profile_id"] = request.sensor_profile_name
        metadata["sensor_profile_hash"] = sensor_profile_hash
        metadata["fixed_delta_seconds"] = request.fixed_delta_seconds
        metadata["recorder_enabled"] = True
        metadata["materialization_agent"] = scenario_source["materialization_agent"]

        run = manager.create_run(
            descriptor_payload=descriptor,
            run_id=run_id,
            hil_config=None,
            evaluation_profile=None,
            execution_backend="native",
            scenario_source=scenario_source,
            config_snapshot_extra={
                "scenario_source_materialization": {
                    "source_id": source.source_id,
                    "materialization_id": materialization_id,
                    "materialization_config_hash": metadata["materialization_config_hash"],
                }
            },
        )
        materialization = store.create_materialization(
            ScenarioSourceMaterializationRecord(
                materialization_id=materialization_id,
                source_id=source.source_id,
                run_id=run.run_id,
                recording_id=None,
                status=(
                    MATERIALIZATION_STATUS_RUNNING
                    if request.auto_start
                    else MATERIALIZATION_STATUS_NEVER
                ),
                sensor_profile_id=request.sensor_profile_name,
                sensor_profile_hash=sensor_profile_hash,
                fixed_delta_seconds=request.fixed_delta_seconds,
                materialization_agent_type=request.materialization_agent_type,
                materialization_agent_hash=materialization_agent_hash,
                created_at=now_utc(),
                updated_at=now_utc(),
                started_at=now_utc() if request.auto_start else None,
            )
        )
        if request.auto_start:
            run = manager.start_run(run.run_id)
    except AppError as exc:
        raise_http_error(exc)

    source_payload = _source_to_payload(source, [materialization])
    return ScenarioSourceLaunchRecordingResponse(
        success=True,
        data=ScenarioSourceLaunchRecordingPayload(
            source=source_payload,
            materialization=_materialization_to_payload(materialization),
            run=run_to_payload(run),
        ),
    )
