from __future__ import annotations

import asyncio
import base64
import json
import sys
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.api.carla_worker_runner import CarlaWorkerError, run_carla_worker
from app.api.schemas import (
    CreateRunRequest,
    RunCreatePayload,
    RunCreateResponse,
    RunEnvironmentStatePayload,
    RunEnvironmentStateResponse,
    RunEnvironmentUpdateRequest,
    RunEventListResponse,
    RunEventPayload,
    RunListResponse,
    RunPayload,
    RunResponse,
    RunViewerInfoPayload,
    RunViewerInfoResponse,
)
from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.core.models import EventLevel, RunEvent, RunRecord, RunStatus
from app.orchestrator.queue import FileCommandQueue
from app.orchestrator.run_manager import RunManager
from app.storage.artifact_store import ArtifactStore
from app.storage.benchmark_definition_store import BenchmarkDefinitionStore
from app.storage.benchmark_task_store import BenchmarkTaskStore
from app.storage.gateway_store import GatewayStore
from app.storage.project_store import ProjectStore
from app.storage.run_control_store import (
    SENSOR_CAPTURE_STATUS_RUNNING,
    SENSOR_CAPTURE_STATUS_STARTING,
    SENSOR_CAPTURE_STATUS_STOPPED,
    SENSOR_CAPTURE_STATUS_STOPPING,
    RunControlStore,
    build_resolved_runtime_control,
)
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc, to_iso8601
from app.viewer.ego_snapshot import list_viewer_views

router = APIRouter(tags=["运行管理"])
ACTIVE_VIEWER_STATUSES = {
    RunStatus.STARTING,
    RunStatus.RUNNING,
    RunStatus.PAUSED,
    RunStatus.STOPPING,
}
VIEWER_STREAM_INTERVAL_MS = 66
VIEWER_STREAM_WIDTH = 800
VIEWER_STREAM_HEIGHT = 450
VIEWER_PLAYBACK_INTERVAL_MS = 66
VIEWER_BUFFER_MIN_FRAMES = 2
VIEWER_BUFFER_MAX_FRAMES = 6


@lru_cache(maxsize=1)
def get_run_manager() -> RunManager:
    settings = get_settings()
    return RunManager(
        run_store=RunStore(settings.runs_root),
        artifact_store=ArtifactStore(settings.artifacts_root),
        command_queue=FileCommandQueue(settings.commands_root),
        gateway_store=GatewayStore(settings.gateways_root),
    )


@lru_cache(maxsize=1)
def get_artifact_store() -> ArtifactStore:
    settings = get_settings()
    return ArtifactStore(settings.artifacts_root)


@lru_cache(maxsize=1)
def get_project_store() -> ProjectStore:
    settings = get_settings()
    return ProjectStore(settings.projects_root)


@lru_cache(maxsize=1)
def get_benchmark_definition_store() -> BenchmarkDefinitionStore:
    settings = get_settings()
    return BenchmarkDefinitionStore(settings.benchmark_definitions_root)


@lru_cache(maxsize=1)
def get_benchmark_task_store() -> BenchmarkTaskStore:
    settings = get_settings()
    return BenchmarkTaskStore(settings.benchmark_tasks_root)


@lru_cache(maxsize=1)
def get_control_store() -> RunControlStore:
    settings = get_settings()
    return RunControlStore(settings.controls_root)


def _metadata_tag_value(metadata: dict[str, Any], prefix: str) -> str | None:
    tags = metadata.get("tags")
    if not isinstance(tags, list):
        return None

    needle = f"{prefix}:"
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith(needle):
            continue
        value = tag[len(needle) :].strip()
        return value or None
    return None


def _run_context_from_metadata(run: RunRecord) -> dict[str, str | None]:
    metadata = run.descriptor.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    project_id = _metadata_tag_value(metadata, "project") or _metadata_tag_value(metadata, "chip")
    benchmark_definition_id = _metadata_tag_value(metadata, "benchmark")
    benchmark_task_id = _metadata_tag_value(metadata, "task")
    dut_model = metadata.get("dut_model")
    if not isinstance(dut_model, str) or not dut_model.strip():
        dut_model = None

    project_name = None
    if project_id:
        try:
            project_name = get_project_store().get(project_id).name
        except AppError:
            project_name = None

    benchmark_name = None
    if benchmark_definition_id:
        try:
            benchmark_name = get_benchmark_definition_store().get(benchmark_definition_id).name
        except AppError:
            benchmark_name = None

    if benchmark_task_id:
        try:
            task = get_benchmark_task_store().get(benchmark_task_id)
            project_name = project_name or task.project_name
            benchmark_name = benchmark_name or task.benchmark_name
            dut_model = dut_model or task.dut_model
        except AppError:
            pass

    return {
        "project_id": project_id,
        "project_name": project_name,
        "benchmark_definition_id": benchmark_definition_id,
        "benchmark_name": benchmark_name,
        "benchmark_task_id": benchmark_task_id,
        "dut_model": dut_model,
    }


def run_to_payload(run: RunRecord) -> RunPayload:
    metrics = get_artifact_store().read_metrics(run.run_id) or {}
    device_metrics = get_artifact_store().read_device_metrics(run.run_id)
    context = _run_context_from_metadata(run)
    created_at_utc = to_iso8601(run.created_at)
    updated_at_utc = to_iso8601(run.updated_at)
    started_at_utc = to_iso8601(run.started_at)
    ended_at_utc = to_iso8601(run.ended_at)

    return RunPayload(
        run_id=run.run_id,
        status=run.status.value,
        scenario_name=run.scenario_name,
        map_name=run.map_name,
        created_at_utc=created_at_utc,
        updated_at_utc=updated_at_utc,
        started_at_utc=started_at_utc,
        ended_at_utc=ended_at_utc,
        created_time=created_at_utc,
        updated_time=updated_at_utc,
        start_time=started_at_utc,
        end_time=ended_at_utc,
        error_reason=run.error_reason,
        stop_requested=run.stop_requested,
        cancel_requested=run.cancel_requested,
        hil_config=run.hil_config,
        evaluation_profile=run.evaluation_profile,
        artifact_dir=run.artifact_dir,
        execution_backend=run.execution_backend,
        scenario_source=run.scenario_source,
        device_metrics=device_metrics,
        project_id=context["project_id"],
        project_name=context["project_name"],
        benchmark_definition_id=context["benchmark_definition_id"],
        benchmark_name=context["benchmark_name"],
        benchmark_task_id=context["benchmark_task_id"],
        dut_model=context["dut_model"],
        metadata=run.descriptor.get("metadata", {}),
        weather=run.descriptor.get("weather", {}),
        traffic=run.descriptor.get("traffic", {}),
        sensors=run.descriptor.get("sensors", {}),
        recorder=run.descriptor.get("recorder", {}),
        debug=run.descriptor.get("debug", {}),
        runtime_capabilities={
            "weather_update": run.execution_backend == "native",
            "viewer_friendly": run.execution_backend == "native",
        },
        sim_time=metrics.get("sim_time"),
        current_tick=metrics.get("current_tick"),
        executed_tick_count=metrics.get("executed_tick_count"),
        sim_elapsed_seconds=metrics.get("sim_elapsed_seconds"),
        achieved_tick_rate_hz=metrics.get("achieved_tick_rate_hz"),
        wall_elapsed_seconds=metrics.get("wall_time"),
        spawned_actors_count=metrics.get("spawned_actors_count"),
    )


def raise_http_error(exc: AppError) -> NoReturn:
    detail = {"code": exc.code, "message": exc.message}
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=detail)
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=409, detail=detail)
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=422, detail=detail)
    raise HTTPException(status_code=500, detail=detail)


def _resolved_runtime_control_state(run: RunRecord) -> dict[str, Any]:
    control_store = get_control_store()
    artifact_store = get_artifact_store()
    return build_resolved_runtime_control(
        run.run_id,
        run.descriptor,
        control_store.get(run.run_id),
        artifact_run_dir=artifact_store.run_dir(run.run_id),
    )


def _write_zip_archive(source_dir: Path, archive_path: Path) -> Path:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, arcname=path.relative_to(source_dir.parent).as_posix())
    return archive_path


def _append_run_control_event(
    run_id: str,
    event_type: str,
    message: str,
    *,
    payload: dict[str, Any] | None = None,
    level: EventLevel = EventLevel.INFO,
) -> None:
    artifact_store = get_artifact_store()
    event = RunEvent(
        timestamp=now_utc(),
        run_id=run_id,
        level=level,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    artifact_store.append_event(event)
    artifact_store.append_run_log(
        run_id,
        f"[{event.timestamp.isoformat()}] {event.level.value} {event.event_type} {event.message}",
    )


def _assert_sensor_capture_control_allowed(run: RunRecord) -> None:
    if run.status not in ACTIVE_VIEWER_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_SENSOR_CAPTURE_NOT_ACTIVE",
                "message": "只有运行中的场景才允许开始或停止传感器采集",
            },
        )
    sensors = run.descriptor.get("sensors", {})
    if not isinstance(sensors, dict) or not bool(sensors.get("enabled")):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_SENSOR_CAPTURE_DISABLED",
                "message": "当前 run 没有启用可采集的传感器模板",
            },
        )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "RUN_SENSOR_CAPTURE_UNSUPPORTED",
            "message": "当前平台未开放运行中手动开始或停止平台侧传感器采集",
        },
    )


def _viewer_preferred_actor_id(events: list[dict[str, Any]]) -> int | None:
    for event in reversed(events):
        if event.get("event_type") != "EGO_SPAWNED":
            continue
        payload = event.get("payload", {})
        actor_id = payload.get("actor_id")
        if isinstance(actor_id, int):
            return actor_id
    return None


def _viewer_preferred_spawn_point(
    events: list[dict[str, Any]], run: RunRecord
) -> dict[str, float] | None:
    for event in reversed(events):
        if event.get("event_type") != "EGO_SPAWNED":
            continue
        payload = event.get("payload", {})
        resolved_spawn_point = payload.get("resolved_spawn_point")
        if isinstance(resolved_spawn_point, dict):
            return resolved_spawn_point

    spawn_point = run.descriptor.get("ego_vehicle", {}).get("spawn_point")
    if isinstance(spawn_point, dict):
        return spawn_point
    return None


def _viewer_worker_payload(
    manager: RunManager,
    run_id: str,
    run: RunRecord,
    *,
    width: int,
    height: int,
    view_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    events = manager.get_events(run_id)
    return {
        "host": settings.carla_host,
        "port": settings.carla_port,
        "timeout_seconds": settings.carla_timeout_seconds,
        "width": width,
        "height": height,
        "preferred_actor_id": _viewer_preferred_actor_id(events),
        "preferred_spawn_point": _viewer_preferred_spawn_point(events, run),
        "view_id": view_id,
    }


def _capture_viewer_frame_base64(
    manager: RunManager,
    run_id: str,
    run: RunRecord,
    *,
    width: int,
    height: int,
    view_id: str,
) -> str:
    settings = get_settings()
    worker_payload = run_carla_worker(
        "app.api.carla_viewer_worker",
        _viewer_worker_payload(
            manager,
            run_id,
            run,
            width=width,
            height=height,
            view_id=view_id,
        ),
        timeout_seconds=max(settings.carla_timeout_seconds, 5.0) + 5.0,
    )
    image_base64 = worker_payload.get("image_base64")
    if not isinstance(image_base64, str) or not image_base64:
        raise CarlaWorkerError(
            status_code=503,
            detail="viewer worker returned an empty frame payload.",
        )
    return image_base64


def _viewer_stream_worker_payload(
    manager: RunManager,
    run_id: str,
    run: RunRecord,
    *,
    width: int,
    height: int,
    view_id: str,
) -> dict[str, Any]:
    payload = _viewer_worker_payload(
        manager,
        run_id,
        run,
        width=width,
        height=height,
        view_id=view_id,
    )
    payload["target_interval_ms"] = VIEWER_PLAYBACK_INTERVAL_MS
    payload["capture_timeout_seconds"] = max(1.0, VIEWER_PLAYBACK_INTERVAL_MS / 1000.0 * 2.5)
    return payload


async def _read_worker_json_line(
    stream: asyncio.StreamReader,
    buffer: bytearray,
    *,
    max_bytes: int = 8 * 1024 * 1024,
) -> bytes | None:
    while True:
        newline_index = buffer.find(b"\n")
        if newline_index >= 0:
            line = bytes(buffer[:newline_index])
            del buffer[: newline_index + 1]
            return line

        chunk = await stream.read(65536)
        if not chunk:
            if buffer:
                line = bytes(buffer)
                buffer.clear()
                return line
            return None

        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise ValueError("viewer stream payload exceeded the safety limit")


def _starting_run_has_spawned_ego(manager: RunManager, run_id: str) -> bool:
    events = manager.get_events(run_id)
    return any(event.get("event_type") == "EGO_SPAWNED" for event in events)


def _viewer_availability(
    manager: RunManager,
    run_id: str,
    run: RunRecord,
) -> tuple[bool, str | None]:
    if run.status not in ACTIVE_VIEWER_STATUSES:
        return False, "viewer 仅在 STARTING / RUNNING / PAUSED / STOPPING 状态可用"

    if run.status == RunStatus.STARTING and not _starting_run_has_spawned_ego(manager, run_id):
        return False, "viewer 正在等待 ego 车辆生成"

    return True, None


@router.post(
    "/runs",
    response_model=RunCreateResponse,
    summary="创建运行",
    description="根据 descriptor 创建一个 run，创建后状态为 CREATED。",
)
def create_run(request: CreateRunRequest) -> RunCreateResponse:
    manager = get_run_manager()
    try:
        run = manager.create_run(
            request.descriptor,
            request.descriptor_path,
            request.hil_config.model_dump(mode="json") if request.hil_config is not None else None,
            (
                request.evaluation_profile.model_dump(mode="json")
                if request.evaluation_profile is not None
                else None
            ),
        )
    except AppError as exc:
        raise_http_error(exc)

    return RunCreateResponse(
        success=True,
        data=RunCreatePayload(
            run_id=run.run_id,
            status=run.status.value,
            hil_config=run.hil_config,
            evaluation_profile=run.evaluation_profile,
        ),
    )


@router.post(
    "/runs/{run_id}/start",
    response_model=RunResponse,
    summary="启动运行",
    description="将 run 放入执行队列，状态从 CREATED 变为 QUEUED。",
)
def start_run(run_id: str) -> RunResponse:
    manager = get_run_manager()
    try:
        run = manager.start_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    return RunResponse(success=True, data=run_to_payload(run))


@router.post(
    "/runs/{run_id}/stop",
    response_model=RunResponse,
    summary="停止运行",
    description="请求停止运行。若尚未启动会直接取消；若运行中则进入 STOPPING。",
)
def stop_run(run_id: str) -> RunResponse:
    manager = get_run_manager()
    try:
        run = manager.stop_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    return RunResponse(success=True, data=run_to_payload(run))


@router.post(
    "/runs/{run_id}/cancel",
    response_model=RunResponse,
    summary="取消运行",
    description="请求取消运行。语义与 stop 类似，但标记为取消请求。",
)
def cancel_run(run_id: str) -> RunResponse:
    manager = get_run_manager()
    try:
        run = manager.cancel_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    return RunResponse(success=True, data=run_to_payload(run))


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="查询单个运行",
    description="返回 run 当前状态、起止时间、错误原因和 artifact 路径。",
)
def get_run(run_id: str) -> RunResponse:
    manager = get_run_manager()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    return RunResponse(success=True, data=run_to_payload(run))


@router.get(
    "/runs",
    response_model=RunListResponse,
    summary="查询运行列表",
    description="返回运行列表，可按状态过滤。",
)
def list_runs(
    status: str | None = Query(default=None, description="可选状态过滤值")
) -> RunListResponse:
    manager = get_run_manager()
    try:
        runs = manager.list_runs(status)
    except AppError as exc:
        raise_http_error(exc)

    return RunListResponse(success=True, data=[run_to_payload(run) for run in runs])


@router.get(
    "/runs/{run_id}/events",
    response_model=RunEventListResponse,
    summary="查询运行事件",
    description="返回该 run 的 events.jsonl 事件流。",
)
def get_run_events(run_id: str) -> RunEventListResponse:
    manager = get_run_manager()
    try:
        events = manager.get_events(run_id)
    except AppError as exc:
        raise_http_error(exc)

    return RunEventListResponse(
        success=True,
        data=[
            RunEventPayload(
                timestamp=str(event.get("timestamp", "")),
                run_id=str(event.get("run_id", run_id)),
                level=str(event.get("level", "INFO")),
                event_type=str(event.get("event_type", "")),
                message=str(event.get("message", "")),
                payload=(
                    event.get("payload", {}) if isinstance(event.get("payload", {}), dict) else {}
                ),
            )
            for event in events
        ],
    )


@router.get(
    "/runs/{run_id}/environment",
    response_model=RunEnvironmentStateResponse,
    summary="查询运行环境控制状态",
    description="返回该 run 当前 descriptor 中的环境参数以及最近一次运行时环境控制值。",
)
def get_run_environment(run_id: str) -> RunEnvironmentStateResponse:
    manager = get_run_manager()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)
    control_state = _resolved_runtime_control_state(run)

    return RunEnvironmentStateResponse(
        success=True,
        data=RunEnvironmentStatePayload(
            run_id=run_id,
            descriptor_weather=run.descriptor.get("weather", {}),
            descriptor_debug=run.descriptor.get("debug", {}),
            weather=control_state.get("weather"),
            runtime_control={
                "weather": control_state.get("weather"),
                "debug": control_state.get("debug"),
                "sensor_capture": control_state.get("sensor_capture"),
                "recorder": control_state.get("recorder"),
                "updated_at_utc": control_state.get("updated_at_utc"),
            },
        ),
    )


@router.get(
    "/runs/{run_id}/viewer",
    response_model=RunViewerInfoResponse,
    summary="查询运行时 viewer 状态",
    description="返回前端运行时显示界面所需的视角列表和当前可用性。",
)
def get_run_viewer(run_id: str) -> RunViewerInfoResponse:
    manager = get_run_manager()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    available, reason = _viewer_availability(manager, run_id, run)

    return RunViewerInfoResponse(
        success=True,
        data=RunViewerInfoPayload(
            run_id=run_id,
            available=available,
            reason=reason,
            views=list_viewer_views(),
            snapshot_url=f"/runs/{run_id}/viewer/frame",
            stream_ws_path=f"/ws/runs/{run_id}/viewer",
            refresh_interval_ms=1200,
            stream_interval_ms=VIEWER_STREAM_INTERVAL_MS,
            playback_interval_ms=VIEWER_PLAYBACK_INTERVAL_MS,
            stream_buffer_min_frames=VIEWER_BUFFER_MIN_FRAMES,
            stream_buffer_max_frames=VIEWER_BUFFER_MAX_FRAMES,
        ),
    )


@router.get(
    "/runs/{run_id}/viewer/frame",
    include_in_schema=False,
    summary="获取运行时 viewer 单帧画面",
)
def get_run_viewer_frame(
    run_id: str,
    view: str = Query(default="first_person"),
) -> Response:
    manager = get_run_manager()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    available, reason = _viewer_availability(manager, run_id, run)
    if not available:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_VIEWER_NOT_AVAILABLE",
                "message": reason or "viewer 当前不可用",
            },
        )

    try:
        image_base64 = _capture_viewer_frame_base64(
            manager,
            run_id,
            run,
            width=1280,
            height=720,
            view_id=view,
        )
        png_bytes = base64.b64decode(image_base64)
    except (CarlaWorkerError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "RUN_VIEWER_UNAVAILABLE", "message": str(exc)},
        ) from exc

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.websocket("/ws/runs/{run_id}/viewer")
async def stream_run_viewer(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    manager = get_run_manager()
    view = websocket.query_params.get("view", "first_person")
    worker_process: asyncio.subprocess.Process | None = None
    stdout_buffer = bytearray()

    try:
        try:
            run = manager.get_run(run_id)
        except AppError as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": exc.code,
                    "message": exc.message,
                }
            )
            return

        available, reason = _viewer_availability(manager, run_id, run)
        if not available:
            await websocket.send_json(
                {
                    "type": "unavailable",
                    "run_id": run_id,
                    "run_status": run.status.value,
                    "reason": reason or "viewer 当前不可用",
                }
            )
            return

        worker_process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.api.carla_viewer_stream_worker",
            json.dumps(
                _viewer_stream_worker_payload(
                    manager,
                    run_id,
                    run,
                    width=VIEWER_STREAM_WIDTH,
                    height=VIEWER_STREAM_HEIGHT,
                    view_id=view,
                ),
                ensure_ascii=False,
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        assert worker_process.stdout is not None
        assert worker_process.stderr is not None

        while True:
            latest_run = manager.get_run(run_id)
            latest_available, latest_reason = _viewer_availability(manager, run_id, latest_run)
            if not latest_available:
                await websocket.send_json(
                    {
                        "type": "unavailable",
                        "run_id": run_id,
                        "run_status": latest_run.status.value,
                        "reason": latest_reason or "viewer 当前不可用",
                    }
                )
                return

            raw_line = await _read_worker_json_line(worker_process.stdout, stdout_buffer)
            if not raw_line:
                stderr_output = await worker_process.stderr.read()
                stderr_text = stderr_output.decode("utf-8", errors="ignore").strip()
                await websocket.send_json(
                    {
                        "type": "unavailable",
                        "run_id": run_id,
                        "run_status": latest_run.status.value,
                        "reason": stderr_text or "viewer stream worker exited unexpectedly",
                    }
                )
                return

            try:
                worker_payload = json.loads(raw_line.decode("utf-8"))
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "unavailable",
                        "run_id": run_id,
                        "run_status": latest_run.status.value,
                        "reason": "viewer stream worker returned malformed payload",
                    }
                )
                return

            if not worker_payload.get("ok"):
                await websocket.send_json(
                    {
                        "type": "unavailable",
                        "run_id": run_id,
                        "run_status": latest_run.status.value,
                        "reason": str(
                            worker_payload.get("error") or "viewer stream unavailable"
                        ),
                    }
                )
                return

            image_base64 = worker_payload.get("image_base64")
            mime = str(worker_payload.get("mime") or "image/png")
            if not isinstance(image_base64, str) or not image_base64:
                await websocket.send_json(
                    {
                        "type": "unavailable",
                        "run_id": run_id,
                        "run_status": latest_run.status.value,
                        "reason": "viewer stream worker returned an empty frame payload",
                    }
                )
                return

            await websocket.send_json(
                {
                    "type": "frame",
                    "run_id": run_id,
                    "run_status": latest_run.status.value,
                    "mime": mime,
                    "image_base64": image_base64,
                }
            )
    except WebSocketDisconnect:
        return
    finally:
        if worker_process is not None and worker_process.returncode is None:
            worker_process.terminate()
            try:
                await asyncio.wait_for(worker_process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                worker_process.kill()


@router.post(
    "/runs/{run_id}/environment",
    response_model=RunEnvironmentStateResponse,
    summary="更新运行环境参数",
    description="更新 run 的环境参数。运行中会由 executor 轮询并应用天气更新。",
)
def update_run_environment(
    run_id: str, request: RunEnvironmentUpdateRequest
) -> RunEnvironmentStateResponse:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    control_store = get_control_store()
    try:
        run = run_store.get(run_id)
    except AppError as exc:
        raise_http_error(exc)

    if run.execution_backend != "native":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_ENVIRONMENT_UPDATE_UNSUPPORTED",
                "message": "当前 run 不支持平台侧运行时天气热更新",
            },
        )

    updated_run = run_store.update_descriptor_sections(
        run_id,
        weather=request.weather.model_dump(mode="json", exclude_none=True),
        debug=request.debug or run.descriptor.get("debug", {}),
    )
    control_state = control_store.update(
        run_id,
        {
            "weather": request.weather.model_dump(mode="json", exclude_none=True),
            "debug": request.debug or updated_run.descriptor.get("debug", {}),
        },
    )

    return RunEnvironmentStateResponse(
        success=True,
        data=RunEnvironmentStatePayload(
            run_id=run_id,
            descriptor_weather=updated_run.descriptor.get("weather", {}),
            descriptor_debug=updated_run.descriptor.get("debug", {}),
            weather=updated_run.descriptor.get("weather", {}),
            runtime_control=build_resolved_runtime_control(
                run_id,
                updated_run.descriptor,
                control_state,
                artifact_run_dir=get_artifact_store().run_dir(run_id),
            ),
        ),
    )


@router.post(
    "/runs/{run_id}/sensor-capture/start",
    response_model=RunEnvironmentStateResponse,
    summary="开始运行中的传感器采集",
    description="仅改变传感器采集状态，不影响场景运行本身。适合在需要保留真实传感器数据时手动开始采集。",
)
def start_run_sensor_capture(run_id: str) -> RunEnvironmentStateResponse:
    manager = get_run_manager()
    control_store = get_control_store()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    _assert_sensor_capture_control_allowed(run)
    current_state = _resolved_runtime_control_state(run)
    current_sensor_capture = (
        current_state.get("sensor_capture", {})
        if isinstance(current_state.get("sensor_capture"), dict)
        else {}
    )
    already_active = bool(current_sensor_capture.get("active"))
    control_state = control_store.update(
        run_id,
        {
            "sensor_capture": {
                "desired_state": "RUNNING",
                "status": (
                    SENSOR_CAPTURE_STATUS_RUNNING
                    if already_active
                    else SENSOR_CAPTURE_STATUS_STARTING
                ),
                "active": already_active,
                "last_error": None,
            }
        },
    )
    _append_run_control_event(
        run_id,
        "SENSOR_CAPTURE_START_REQUESTED",
        "已请求开始传感器采集",
    )
    resolved = build_resolved_runtime_control(
        run_id,
        run.descriptor,
        control_state,
        artifact_run_dir=get_artifact_store().run_dir(run_id),
    )
    return RunEnvironmentStateResponse(
        success=True,
        data=RunEnvironmentStatePayload(
            run_id=run_id,
            descriptor_weather=run.descriptor.get("weather", {}),
            descriptor_debug=run.descriptor.get("debug", {}),
            weather=resolved.get("weather"),
            runtime_control=resolved,
        ),
    )


@router.post(
    "/runs/{run_id}/sensor-capture/stop",
    response_model=RunEnvironmentStateResponse,
    summary="停止运行中的传感器采集",
    description="停止真实传感器数据落盘，但不会停止当前场景。",
)
def stop_run_sensor_capture(run_id: str) -> RunEnvironmentStateResponse:
    manager = get_run_manager()
    control_store = get_control_store()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    _assert_sensor_capture_control_allowed(run)
    current_state = _resolved_runtime_control_state(run)
    current_sensor_capture = (
        current_state.get("sensor_capture", {})
        if isinstance(current_state.get("sensor_capture"), dict)
        else {}
    )
    currently_active = bool(current_sensor_capture.get("active"))
    control_state = control_store.update(
        run_id,
        {
            "sensor_capture": {
                "desired_state": "STOPPED",
                "status": (
                    SENSOR_CAPTURE_STATUS_STOPPING
                    if currently_active
                    else SENSOR_CAPTURE_STATUS_STOPPED
                ),
                "active": currently_active,
            }
        },
    )
    _append_run_control_event(
        run_id,
        "SENSOR_CAPTURE_STOP_REQUESTED",
        "已请求停止传感器采集",
    )
    resolved = build_resolved_runtime_control(
        run_id,
        run.descriptor,
        control_state,
        artifact_run_dir=get_artifact_store().run_dir(run_id),
    )
    return RunEnvironmentStateResponse(
        success=True,
        data=RunEnvironmentStatePayload(
            run_id=run_id,
            descriptor_weather=run.descriptor.get("weather", {}),
            descriptor_debug=run.descriptor.get("debug", {}),
            weather=resolved.get("weather"),
            runtime_control=resolved,
        ),
    )


@router.get(
    "/runs/{run_id}/sensor-capture/download",
    include_in_schema=False,
    summary="下载传感器采集产物",
)
def download_run_sensor_capture(run_id: str) -> FileResponse:
    manager = get_run_manager()
    try:
        run = manager.get_run(run_id)
    except AppError as exc:
        raise_http_error(exc)

    resolved = _resolved_runtime_control_state(run)
    sensor_capture = (
        resolved.get("sensor_capture", {})
        if isinstance(resolved.get("sensor_capture"), dict)
        else {}
    )
    output_root = Path(
        str(
            sensor_capture.get("output_root")
            or (get_artifact_store().run_dir(run_id) / "outputs" / "sensors")
        )
    ).expanduser()
    if not output_root.exists() or not output_root.is_dir():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RUN_SENSOR_CAPTURE_OUTPUT_MISSING",
                "message": "当前 run 还没有可下载的传感器采集目录",
            },
        )

    archive_path = get_artifact_store().run_dir(run_id) / f"{run_id}_sensor_capture.zip"
    _write_zip_archive(output_root, archive_path)
    return FileResponse(
        path=archive_path,
        filename=f"{run_id}_sensor_capture.zip",
        media_type="application/zip",
    )
