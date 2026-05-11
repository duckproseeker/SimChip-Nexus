from __future__ import annotations

from functools import lru_cache
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query

from app.api.schemas import ApiResponse, CaptureSyncRequest, CreateCaptureRequest
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.core.models import CaptureRecord
from app.orchestrator.capture_manager import CaptureManager
from app.storage.capture_artifact_store import CaptureArtifactStore
from app.storage.capture_store import CaptureStore
from app.storage.gateway_store import GatewayStore
from app.utils.time_utils import to_iso8601

router = APIRouter(tags=["采集管理"])


@lru_cache(maxsize=1)
def get_capture_manager() -> CaptureManager:
    settings = get_settings()
    return CaptureManager(
        capture_store=CaptureStore(settings.captures_root),
        capture_artifact_store=CaptureArtifactStore(settings.capture_artifacts_root),
        gateway_store=GatewayStore(settings.gateways_root),
    )


def capture_to_payload(capture: CaptureRecord) -> dict[str, Any]:
    return {
        "capture_id": capture.capture_id,
        "gateway_id": capture.gateway_id,
        "source": capture.source,
        "save_format": capture.save_format,
        "sample_fps": capture.sample_fps,
        "max_frames": capture.max_frames,
        "save_dir": capture.save_dir,
        "manifest_path": capture.manifest_path,
        "note": capture.note,
        "status": capture.status.value,
        "saved_frames": capture.saved_frames,
        "created_at_utc": to_iso8601(capture.created_at),
        "updated_at_utc": to_iso8601(capture.updated_at),
        "started_at_utc": to_iso8601(capture.started_at),
        "ended_at_utc": to_iso8601(capture.ended_at),
        "error_reason": capture.error_reason,
    }


def raise_http_error(exc: AppError) -> NoReturn:
    detail = {"code": exc.code, "message": exc.message}
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=detail)
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=409, detail=detail)
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=422, detail=detail)
    raise HTTPException(status_code=500, detail=detail)


@router.post("/captures", response_model=ApiResponse, summary="创建采集任务")
def create_capture(request: CreateCaptureRequest) -> ApiResponse:
    manager = get_capture_manager()
    try:
        capture = manager.create_capture(
            gateway_id=request.gateway_id,
            source=request.source,
            save_format=request.save_format,
            sample_fps=request.sample_fps,
            max_frames=request.max_frames,
            save_dir=request.save_dir,
            note=request.note,
        )
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=capture_to_payload(capture))


@router.post("/captures/{capture_id}/start", response_model=ApiResponse, summary="启动采集")
def start_capture(capture_id: str) -> ApiResponse:
    manager = get_capture_manager()
    try:
        capture = manager.start_capture(capture_id)
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=capture_to_payload(capture))


@router.post("/captures/{capture_id}/stop", response_model=ApiResponse, summary="停止采集")
def stop_capture(capture_id: str) -> ApiResponse:
    manager = get_capture_manager()
    try:
        capture = manager.stop_capture(capture_id)
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=capture_to_payload(capture))


@router.get("/captures", response_model=ApiResponse, summary="查询采集列表")
def list_captures(
    status: str | None = Query(default=None, description="可选采集状态过滤值"),
    gateway_id: str | None = Query(default=None, description="可选网关过滤值"),
) -> ApiResponse:
    manager = get_capture_manager()
    try:
        captures = manager.list_captures(status, gateway_id)
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(
        success=True,
        data={"captures": [capture_to_payload(item) for item in captures]},
    )


@router.get("/captures/{capture_id}", response_model=ApiResponse, summary="查询单个采集")
def get_capture(capture_id: str) -> ApiResponse:
    manager = get_capture_manager()
    try:
        capture = manager.get_capture(capture_id)
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=capture_to_payload(capture))


@router.get(
    "/captures/{capture_id}/frames",
    response_model=ApiResponse,
    summary="查询采集帧列表",
)
def get_capture_frames(
    capture_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> ApiResponse:
    manager = get_capture_manager()
    try:
        frames = manager.get_frames(capture_id, offset=offset, limit=limit)
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=frames)


@router.get(
    "/captures/{capture_id}/manifest",
    response_model=ApiResponse,
    summary="查询采集 manifest",
)
def get_capture_manifest(capture_id: str) -> ApiResponse:
    manager = get_capture_manager()
    try:
        manifest = manager.get_manifest(capture_id)
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=manifest)


@router.post(
    "/captures/{capture_id}/sync",
    response_model=ApiResponse,
    summary="同步采集进度",
)
def sync_capture(capture_id: str, request: CaptureSyncRequest) -> ApiResponse:
    manager = get_capture_manager()
    try:
        capture = manager.sync_capture(
            capture_id=capture_id,
            status=request.status,
            saved_frames=request.saved_frames,
            error_reason=request.error_reason,
            frames=(
                [item.model_dump(mode="json") for item in request.frames]
                if request.frames is not None
                else None
            ),
        )
    except AppError as exc:
        raise_http_error(exc)
    return ApiResponse(success=True, data=capture_to_payload(capture))
