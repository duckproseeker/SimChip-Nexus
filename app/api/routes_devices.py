from __future__ import annotations

from fastapi import APIRouter

from app.api.routes_benchmarks import benchmark_task_to_payload
from app.api.routes_captures import capture_to_payload
from app.api.routes_gateways import gateway_to_payload
from app.api.routes_projects import get_platform_service, raise_platform_http_error
from app.api.schemas import ApiResponse
from app.core.errors import AppError

router = APIRouter(tags=["设备工作台"])


@router.get("/devices/workspace", response_model=ApiResponse, summary="查询设备工作台数据")
def get_devices_workspace() -> ApiResponse:
    service = get_platform_service()
    try:
        workspace = service.get_devices_workspace()
    except AppError as exc:
        raise_platform_http_error(exc)

    return ApiResponse(
        success=True,
        data={
            "summary": workspace["summary"],
            "gateways": [gateway_to_payload(item) for item in workspace["gateways"]],
            "captures": [capture_to_payload(item) for item in workspace["captures"]],
            "benchmark_tasks": [
                benchmark_task_to_payload(item)
                for item in workspace["benchmark_tasks"]
            ],
        },
    )


@router.get(
    "/devices/{gateway_id}/workspace",
    response_model=ApiResponse,
    summary="查询单个设备工作台数据",
)
def get_device_workspace(gateway_id: str) -> ApiResponse:
    service = get_platform_service()
    try:
        workspace = service.get_device_workspace(gateway_id)
    except AppError as exc:
        raise_platform_http_error(exc)

    return ApiResponse(
        success=True,
        data={
            "gateway": gateway_to_payload(workspace["gateway"]),
            "summary": workspace["summary"],
            "captures": [capture_to_payload(item) for item in workspace["captures"]],
            "benchmark_tasks": [
                benchmark_task_to_payload(item)
                for item in workspace["benchmark_tasks"]
            ],
        },
    )
