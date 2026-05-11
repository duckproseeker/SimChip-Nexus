from __future__ import annotations

from functools import lru_cache
from typing import NoReturn

from fastapi import APIRouter, HTTPException

from app.api.routes_gateways import gateway_to_payload
from app.api.routes_runs import run_to_payload
from app.api.schemas import ApiResponse, ProjectPayload
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.core.models import BenchmarkDefinitionRecord, BenchmarkTaskRecord, ProjectRecord
from app.orchestrator.queue import FileCommandQueue
from app.orchestrator.run_manager import RunManager
from app.platform.service import PlatformService
from app.storage.artifact_store import ArtifactStore
from app.storage.benchmark_definition_store import BenchmarkDefinitionStore
from app.storage.benchmark_task_store import BenchmarkTaskStore
from app.storage.capture_store import CaptureStore
from app.storage.gateway_store import GatewayStore
from app.storage.project_store import ProjectStore
from app.storage.report_store import ReportStore
from app.storage.run_store import RunStore
from app.utils.time_utils import to_iso8601

router = APIRouter(tags=["项目管理"])


def raise_platform_http_error(exc: AppError) -> NoReturn:
    detail = {"code": exc.code, "message": exc.message}
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=detail)
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=409, detail=detail)
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=422, detail=detail)
    raise HTTPException(status_code=500, detail=detail)


@lru_cache(maxsize=1)
def get_platform_service() -> PlatformService:
    settings = get_settings()
    return PlatformService(
        project_store=ProjectStore(settings.projects_root),
        benchmark_definition_store=BenchmarkDefinitionStore(
            settings.benchmark_definitions_root
        ),
        benchmark_task_store=BenchmarkTaskStore(settings.benchmark_tasks_root),
        report_store=ReportStore(settings.reports_root),
        capture_store=CaptureStore(settings.captures_root),
        run_store=RunStore(settings.runs_root),
        run_manager=RunManager(
            run_store=RunStore(settings.runs_root),
            artifact_store=ArtifactStore(settings.artifacts_root),
            command_queue=FileCommandQueue(settings.commands_root),
            gateway_store=GatewayStore(settings.gateways_root),
        ),
        artifact_store=ArtifactStore(settings.artifacts_root),
        gateway_store=GatewayStore(settings.gateways_root),
        sensor_profiles_root=settings.sensor_profiles_root,
        report_artifacts_root=settings.report_artifacts_root,
    )


def project_to_payload(project: ProjectRecord) -> ProjectPayload:
    return ProjectPayload(
        project_id=project.project_id,
        name=project.name,
        vendor=project.vendor,
        processor=project.processor,
        description=project.description,
        benchmark_focus=project.benchmark_focus,
        target_metrics=project.target_metrics,
        input_modes=project.input_modes,
        status=project.status.value,
        created_at_utc=to_iso8601(project.created_at),
        updated_at_utc=to_iso8601(project.updated_at),
    )


def benchmark_definition_to_payload(
    definition: BenchmarkDefinitionRecord,
) -> dict[str, object]:
    return {
        "benchmark_definition_id": definition.benchmark_definition_id,
        "name": definition.name,
        "description": definition.description,
        "focus_metrics": definition.focus_metrics,
        "cadence": definition.cadence,
        "report_shape": definition.report_shape,
        "project_ids": definition.project_ids,
        "default_project_id": definition.default_project_id,
        "default_evaluation_profile_name": definition.default_evaluation_profile_name,
        "planning_mode": definition.planning_mode.value,
        "candidate_scenario_ids": definition.candidate_scenario_ids,
        "supports_duration_seconds": definition.supports_duration_seconds,
        "default_duration_seconds": definition.default_duration_seconds,
        "queue_note": definition.queue_note,
        "created_at_utc": to_iso8601(definition.created_at),
        "updated_at_utc": to_iso8601(definition.updated_at),
    }


def benchmark_task_to_payload(task: BenchmarkTaskRecord) -> dict[str, object]:
    return {
        "benchmark_task_id": task.benchmark_task_id,
        "project_id": task.project_id,
        "project_name": task.project_name,
        "dut_model": task.dut_model,
        "benchmark_definition_id": task.benchmark_definition_id,
        "benchmark_name": task.benchmark_name,
        "status": task.status.value,
        "planned_run_count": task.planned_run_count,
        "counts_by_status": task.counts_by_status,
        "run_ids": task.run_ids,
        "scenario_matrix": [item.model_dump(mode="json") for item in task.scenario_matrix],
        "planning_mode": task.planning_mode.value,
        "selected_scenario_ids": task.selected_scenario_ids,
        "requested_duration_seconds": task.requested_duration_seconds,
        "hil_config": task.hil_config,
        "evaluation_profile_name": task.evaluation_profile_name,
        "auto_start": task.auto_start,
        "summary": task.summary,
        "created_at_utc": to_iso8601(task.created_at),
        "updated_at_utc": to_iso8601(task.updated_at),
        "started_at_utc": to_iso8601(task.started_at),
        "ended_at_utc": to_iso8601(task.ended_at),
    }


@router.get("/projects", response_model=ApiResponse, summary="查询项目列表")
def list_projects() -> ApiResponse:
    service = get_platform_service()
    return ApiResponse(
        success=True,
        data={"projects": [project_to_payload(item) for item in service.list_projects()]},
    )


@router.get("/projects/{project_id}", response_model=ApiResponse, summary="查询单个项目")
def get_project(project_id: str) -> ApiResponse:
    service = get_platform_service()
    try:
        project = service.get_project(project_id)
    except AppError as exc:
        raise_platform_http_error(exc)
    return ApiResponse(success=True, data=project_to_payload(project))


@router.get(
    "/projects/{project_id}/workspace",
    response_model=ApiResponse,
    summary="查询项目工作台数据",
)
def get_project_workspace(project_id: str) -> ApiResponse:
    service = get_platform_service()
    try:
        workspace = service.get_project_workspace(project_id)
    except AppError as exc:
        raise_platform_http_error(exc)

    return ApiResponse(
        success=True,
        data={
            "project": project_to_payload(workspace["project"]),
            "summary": workspace["summary"],
            "benchmark_definitions": [
                benchmark_definition_to_payload(item)
                for item in workspace["benchmark_definitions"]
            ],
            "benchmark_tasks": [
                benchmark_task_to_payload(item) for item in workspace["benchmark_tasks"]
            ],
            "recent_runs": [run_to_payload(item) for item in workspace["recent_runs"]],
            "gateways": [gateway_to_payload(item) for item in workspace["gateways"]],
            "scenario_presets": workspace["scenario_presets"],
        },
    )
