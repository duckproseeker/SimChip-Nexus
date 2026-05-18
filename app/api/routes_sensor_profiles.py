from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter

from app.api.routes_runs import raise_http_error
from app.api.schemas import (
    SensorProfileCopyRequest,
    SensorProfileListPayload,
    SensorProfileListResponse,
    SensorProfilePayload,
    SensorProfileResponse,
    SensorProfileSaveRequest,
)
from app.core.config import get_settings
from app.core.errors import AppError, ValidationError
from app.core.models import SensorProfileRecord
from app.storage.sensor_profile_store import SensorProfileStore, normalize_sensor_profile_payload
from app.utils.time_utils import to_iso8601

router = APIRouter(tags=["传感器库"])


@lru_cache(maxsize=1)
def get_sensor_profile_store() -> SensorProfileStore:
    settings = get_settings()
    return SensorProfileStore(
        settings.scenario_recordings_root,
        legacy_yaml_root=settings.sensor_profiles_root,
    )


def sensor_profile_to_payload(profile: SensorProfileRecord) -> SensorProfilePayload:
    return SensorProfilePayload(
        sensor_profile_id=profile.sensor_profile_id,
        name=profile.name,
        profile_hash=profile.profile_hash,
        fixed_delta_seconds=profile.fixed_delta_seconds,
        expected_fps=profile.expected_fps,
        output_mode=profile.output_mode,
        hil_output_mode=profile.hil_output_mode,
        profile_name=profile.sensor_profile_id,
        display_name=profile.name,
        description=profile.description,
        vehicle_model=profile.vehicle_model,
        sensors=profile.sensors,
        raw_yaml=profile.raw_yaml,
        source_path=profile.source_path or "",
        metadata=profile.metadata,
        created_at_utc=to_iso8601(profile.created_at),
        updated_at_utc=to_iso8601(profile.updated_at),
    )


def sensor_profile_to_descriptor_config(
    profile: SensorProfileRecord, *, auto_start: bool = True
) -> dict[str, Any]:
    return {
        "enabled": True,
        "auto_start": auto_start,
        "profile_name": profile.sensor_profile_id,
        "config_yaml_path": profile.source_path,
        "sensors": [dict(sensor) for sensor in profile.sensors],
    }


def request_to_record(
    request: SensorProfileSaveRequest,
    *,
    sensor_profile_id: str | None = None,
) -> SensorProfileRecord:
    resolved_id = sensor_profile_id or request.sensor_profile_id or request.profile_name
    if resolved_id is None:
        raise ValidationError("sensor_profile_id must not be empty")
    if request.sensor_profile_id and request.sensor_profile_id != resolved_id:
        raise ValidationError("path sensor_profile_id must match request sensor_profile_id")
    if request.profile_name and request.profile_name != resolved_id:
        raise ValidationError("path sensor_profile_id must match request profile_name")
    return normalize_sensor_profile_payload(
        sensor_profile_id=resolved_id,
        name=request.name or request.display_name or resolved_id,
        description=request.description,
        vehicle_model=request.vehicle_model,
        metadata=request.metadata,
        sensors=[sensor.model_dump(mode="json", exclude_none=True) for sensor in request.sensors],
        fixed_delta_seconds=request.fixed_delta_seconds,
        expected_fps=request.expected_fps,
        output_mode=request.output_mode,
        hil_output_mode=request.hil_output_mode,
    )


@router.get(
    "/sensor-profiles",
    response_model=SensorProfileListResponse,
    summary="列出 SQLite 传感器库配置",
)
def list_sensor_profiles() -> SensorProfileListResponse:
    store = get_sensor_profile_store()
    try:
        profiles = store.list()
    except AppError as exc:
        raise_http_error(exc)
    return SensorProfileListResponse(
        success=True,
        data=SensorProfileListPayload(
            items=[sensor_profile_to_payload(profile) for profile in profiles]
        ),
    )


@router.post(
    "/sensor-profiles",
    response_model=SensorProfileResponse,
    summary="创建传感器配置",
)
def create_sensor_profile(request: SensorProfileSaveRequest) -> SensorProfileResponse:
    store = get_sensor_profile_store()
    try:
        profile = store.create(request_to_record(request))
    except AppError as exc:
        raise_http_error(exc)
    return SensorProfileResponse(success=True, data=sensor_profile_to_payload(profile))


@router.get(
    "/sensor-profiles/{sensor_profile_id}",
    response_model=SensorProfileResponse,
    summary="读取传感器配置详情",
)
def get_sensor_profile(sensor_profile_id: str) -> SensorProfileResponse:
    store = get_sensor_profile_store()
    try:
        profile = store.get(sensor_profile_id)
    except AppError as exc:
        raise_http_error(exc)
    return SensorProfileResponse(success=True, data=sensor_profile_to_payload(profile))


@router.put(
    "/sensor-profiles/{sensor_profile_id}",
    response_model=SensorProfileResponse,
    summary="更新传感器配置",
)
def update_sensor_profile(
    sensor_profile_id: str,
    request: SensorProfileSaveRequest,
) -> SensorProfileResponse:
    store = get_sensor_profile_store()
    try:
        profile = store.upsert(request_to_record(request, sensor_profile_id=sensor_profile_id))
    except AppError as exc:
        raise_http_error(exc)
    return SensorProfileResponse(success=True, data=sensor_profile_to_payload(profile))


@router.post(
    "/sensor-profiles/{sensor_profile_id}/copy",
    response_model=SensorProfileResponse,
    summary="复制传感器配置",
)
def copy_sensor_profile(
    sensor_profile_id: str,
    request: SensorProfileCopyRequest,
) -> SensorProfileResponse:
    store = get_sensor_profile_store()
    try:
        profile = store.duplicate(
            sensor_profile_id,
            sensor_profile_id=request.sensor_profile_id,
            name=request.name,
        )
    except AppError as exc:
        raise_http_error(exc)
    return SensorProfileResponse(success=True, data=sensor_profile_to_payload(profile))
