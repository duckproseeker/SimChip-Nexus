from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    ApiResponse,
    GatewayHeartbeatRequest,
    GatewayRegisterRequest,
)
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, ValidationError
from app.core.models import GatewayRecord
from app.hil.evaluation_profiles import list_evaluation_profiles
from app.hil.gateway_runtime_status import resolve_gateway_status
from app.hil.gateway_registry import GatewayRegistry
from app.storage.artifact_store import ArtifactStore
from app.storage.gateway_store import GatewayStore
from app.utils.time_utils import to_iso8601

router = APIRouter(tags=["网关管理"])


@lru_cache(maxsize=1)
def get_gateway_registry() -> GatewayRegistry:
    settings = get_settings()
    return GatewayRegistry(
        GatewayStore(settings.gateways_root),
        artifact_store=ArtifactStore(settings.artifacts_root),
    )


def gateway_to_payload(
    gateway: GatewayRecord,
    *,
    checked_at: datetime | None = None,
    pi_gateway_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    reference_time = checked_at or datetime.now(timezone.utc)
    effective_status, heartbeat_age_seconds, status_detail = resolve_gateway_status(
        gateway,
        settings,
        checked_at=reference_time,
        pi_gateway_status=pi_gateway_status,
    )
    last_heartbeat_at_utc = to_iso8601(gateway.last_heartbeat_at)

    return {
        "gateway_id": gateway.gateway_id,
        "name": gateway.name,
        "status": effective_status,
        "status_detail": status_detail,
        "capabilities": gateway.capabilities,
        "metrics": gateway.metrics,
        "agent_version": gateway.agent_version,
        "address": gateway.address,
        "current_run_id": gateway.current_run_id,
        "last_heartbeat_at_utc": last_heartbeat_at_utc,
        "last_seen_at_utc": to_iso8601(gateway.last_seen_at),
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "created_at_utc": to_iso8601(gateway.created_at),
        "updated_at_utc": to_iso8601(gateway.updated_at),
    }


def raise_gateway_http_error(exc: AppError) -> None:
    detail = {"code": exc.code, "message": exc.message}
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=detail)
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=422, detail=detail)
    raise HTTPException(status_code=500, detail=detail)


@router.post("/gateways/register", response_model=ApiResponse, summary="注册网关")
def register_gateway(request: GatewayRegisterRequest) -> ApiResponse:
    registry = get_gateway_registry()
    try:
        gateway = registry.register_gateway(
            gateway_id=request.gateway_id,
            name=request.name,
            capabilities=request.capabilities,
            agent_version=request.agent_version,
            address=request.address,
        )
    except AppError as exc:
        raise_gateway_http_error(exc)

    return ApiResponse(success=True, data=gateway_to_payload(gateway))


@router.post(
    "/gateways/{gateway_id}/heartbeat",
    response_model=ApiResponse,
    summary="网关心跳",
)
def heartbeat_gateway(gateway_id: str, request: GatewayHeartbeatRequest) -> ApiResponse:
    registry = get_gateway_registry()
    try:
        gateway = registry.record_heartbeat(
            gateway_id=gateway_id,
            status=request.status,
            metrics=request.metrics,
            current_run_id=request.current_run_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_GATEWAY_STATUS", "message": str(exc)},
        ) from exc
    except AppError as exc:
        raise_gateway_http_error(exc)

    return ApiResponse(success=True, data=gateway_to_payload(gateway))


@router.get("/gateways", response_model=ApiResponse, summary="查询网关列表")
def list_gateways() -> ApiResponse:
    registry = get_gateway_registry()
    return ApiResponse(
        success=True,
        data={
            "gateways": [gateway_to_payload(item) for item in registry.list_gateways()],
        },
    )


@router.get("/gateways/{gateway_id}", response_model=ApiResponse, summary="查询单个网关")
def get_gateway(gateway_id: str) -> ApiResponse:
    registry = get_gateway_registry()
    try:
        gateway = registry.get_gateway(gateway_id)
    except AppError as exc:
        raise_gateway_http_error(exc)
    return ApiResponse(success=True, data=gateway_to_payload(gateway))


@router.get(
    "/evaluation-profiles",
    response_model=ApiResponse,
    summary="查询评测模板",
)
def get_evaluation_profiles() -> ApiResponse:
    return ApiResponse(success=True, data={"profiles": list_evaluation_profiles()})
