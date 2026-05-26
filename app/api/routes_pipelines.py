from __future__ import annotations

import threading
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    CreatePipelineRequest,
    PipelineExecutionListResponse,
    PipelineExecutionPayload,
    PipelineExecutionResponse,
    PipelineListResponse,
    PipelineNodeStatePayload,
    PipelinePayload,
    PipelineResponse,
    PipelineValidationError,
    PipelineValidationResponse,
    PipelineValidationResult,
    UpdatePipelineRequest,
)
from app.core.models import (
    PipelineEdgeDef,
    PipelineExecutionStatus,
    PipelineNodeDef,
    PipelineRecord,
)
from app.storage.pipeline_execution_store import (
    get_pipeline_execution_store,
)
from app.storage.pipeline_store import get_pipeline_store
from app.utils.time_utils import to_iso8601

router = APIRouter(tags=["流程编排"])


def _pipeline_to_payload(record: PipelineRecord) -> PipelinePayload:
    return PipelinePayload(
        pipeline_id=record.pipeline_id,
        name=record.name,
        description=record.description,
        nodes=[
            {"node_id": n.node_id, "type": n.type, "position": n.position, "data": n.data}
            for n in record.nodes
        ],
        edges=[
            {
                "edge_id": e.edge_id,
                "source": e.source,
                "source_handle": e.source_handle,
                "target": e.target,
                "target_handle": e.target_handle,
            }
            for e in record.edges
        ],
        created_at_utc=to_iso8601(record.created_at),
        updated_at_utc=to_iso8601(record.updated_at),
    )


def _execution_to_payload(record) -> PipelineExecutionPayload:
    return PipelineExecutionPayload(
        execution_id=record.execution_id,
        pipeline_id=record.pipeline_id,
        status=record.status.value,
        node_states={
            k: PipelineNodeStatePayload(**v) if isinstance(v, dict) else v
            for k, v in record.node_states.items()
        },
        created_at_utc=to_iso8601(record.created_at),
        updated_at_utc=to_iso8601(record.updated_at),
    )


def _validate_pipeline(record: PipelineRecord) -> PipelineValidationResult:
    errors: list[PipelineValidationError] = []
    nodes_by_id = {n.node_id: n for n in record.nodes}
    edges = record.edges

    # Cycle detection via DFS
    adj: dict[str, list[str]] = {n: [] for n in nodes_by_id}
    for e in edges:
        if e.source in adj:
            adj[e.source].append(e.target)

    visited: set[str] = set()
    in_stack: set[str] = set()

    def has_cycle(node_id: str) -> bool:
        visited.add(node_id)
        in_stack.add(node_id)
        for neighbor in adj.get(node_id, []):
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in in_stack:
                return True
        in_stack.discard(node_id)
        return False

    for node_id in nodes_by_id:
        if node_id not in visited:
            if has_cycle(node_id):
                errors.append(PipelineValidationError(code="CYCLE", message="Pipeline contains a cycle"))
                break

    # ProjectNode must exist and be unique
    project_nodes = [n for n in record.nodes if n.type == "project"]
    if len(project_nodes) == 0:
        errors.append(PipelineValidationError(code="NO_PROJECT", message="Pipeline must have a Project node"))
    elif len(project_nodes) > 1:
        errors.append(PipelineValidationError(code="MULTIPLE_PROJECTS", message="Pipeline must have exactly one Project node"))

    # live_run node port validation
    live_run_nodes = [n for n in record.nodes if n.type == "live_run"]
    for run_node in live_run_nodes:
        incoming_handles = {e.target_handle for e in edges if e.target == run_node.node_id}
        if "project" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_PROJECT", message=f"实时仿真节点 {run_node.node_id} 缺少项目连接"))
        if "scenario" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_SCENARIO", message=f"实时仿真节点 {run_node.node_id} 缺少场景连接"))
        if "map" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_MAP", message=f"实时仿真节点 {run_node.node_id} 缺少地图连接"))
        if "weather" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_WEATHER", message=f"实时仿真节点 {run_node.node_id} 缺少天气连接"))
        if "sensor" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_SENSOR", message=f"实时仿真节点 {run_node.node_id} 至少需要一个传感器"))

    # replay_run node port validation
    replay_run_nodes = [n for n in record.nodes if n.type == "replay_run"]
    for run_node in replay_run_nodes:
        incoming_handles = {e.target_handle for e in edges if e.target == run_node.node_id}
        if "project" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_PROJECT", message=f"录制回放节点 {run_node.node_id} 缺少项目连接"))
        if "recording" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_RECORDING", message=f"录制回放节点 {run_node.node_id} 缺少场景录制连接"))
        if "sensor" not in incoming_handles:
            errors.append(PipelineValidationError(code="MISSING_SENSOR", message=f"录制回放节点 {run_node.node_id} 至少需要一个传感器"))

    return PipelineValidationResult(valid=len(errors) == 0, errors=errors)


def _run_pipeline_async(pipeline_id: str, execution_id: str) -> None:
    """Execute pipeline DAG in a background thread."""
    import time
    from app.core.models import RunStatus

    p_store = get_pipeline_store()
    e_store = get_pipeline_execution_store()

    execution = e_store.get(execution_id)
    execution.status = PipelineExecutionStatus.RUNNING
    e_store.save(execution)

    try:
        pipeline = p_store.get(pipeline_id)
        nodes_by_id = {n.node_id: n for n in pipeline.nodes}
        edges = pipeline.edges

        # Kahn's topological sort
        in_degree: dict[str, int] = {n: 0 for n in nodes_by_id}
        adj: dict[str, list[str]] = {n: [] for n in nodes_by_id}
        for e in edges:
            adj[e.source].append(e.target)
            in_degree[e.target] += 1

        queue = [n for n, d in in_degree.items() if d == 0]
        topo_order: list[str] = []
        while queue:
            node_id = queue.pop(0)
            topo_order.append(node_id)
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        ctx: dict[str, object] = {}

        for node_id in topo_order:
            node = nodes_by_id[node_id]
            execution.node_states[node_id] = {"status": "RUNNING"}
            e_store.save(execution)

            try:
                if node.type == "project":
                    ctx["project_id"] = node.data.get("project_id")

                elif node.type == "scenario":
                    ctx["scenario_name"] = node.data.get("scenario_name")

                elif node.type == "map":
                    ctx["map_name"] = node.data.get("map_name")

                elif node.type == "weather":
                    ctx["weather"] = node.data.get("weather_preset_id") or node.data.get("weather_custom")

                elif node.type == "recording":
                    ctx["recording_id"] = node.data.get("recording_id")

                elif node.type in ("sensor_camera", "sensor_lidar", "sensor_radar", "sensor_gnss", "sensor_imu"):
                    ctx.setdefault("sensors", [])
                    ctx["sensors"].append(node.data)  # type: ignore[union-attr]

                elif node.type == "live_run":
                    from app.api.routes_runs import get_run_manager
                    run_manager = get_run_manager()
                    sensors = node.data.get("assembled_sensors") or ctx.get("sensors") or []
                    descriptor = {
                        "scenario_name": ctx.get("scenario_name"),
                        "map_name": ctx.get("map_name"),
                        "weather": ctx.get("weather"),
                        "sensors": sensors,
                        "metadata": {
                            "tags": [f"project:{ctx.get('project_id')}"],
                        },
                    }
                    run = run_manager.create_run(descriptor=descriptor)
                    run_manager.start_run(run.run_id)
                    ctx["run_id"] = run.run_id

                    while True:
                        run = run_manager.get_run(run.run_id)
                        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
                            break
                        time.sleep(2)

                    execution.node_states[node_id] = {
                        "status": run.status.value,
                        "run_id": run.run_id,
                    }
                    e_store.save(execution)
                    if run.status != RunStatus.COMPLETED:
                        raise RuntimeError(f"Run ended with status {run.status.value}")
                    continue

                elif node.type == "replay_run":
                    from app.api.routes_runs import get_run_manager
                    run_manager = get_run_manager()
                    sensors = node.data.get("assembled_sensors") or ctx.get("sensors") or []
                    descriptor = {
                        "recording_id": ctx.get("recording_id"),
                        "sensors": sensors,
                        "metadata": {
                            "tags": [f"project:{ctx.get('project_id')}"],
                        },
                    }
                    run = run_manager.create_run(descriptor=descriptor)
                    run_manager.start_run(run.run_id)
                    ctx["run_id"] = run.run_id

                    while True:
                        run = run_manager.get_run(run.run_id)
                        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED}:
                            break
                        time.sleep(2)

                    execution.node_states[node_id] = {
                        "status": run.status.value,
                        "run_id": run.run_id,
                    }
                    e_store.save(execution)
                    if run.status != RunStatus.COMPLETED:
                        raise RuntimeError(f"Run ended with status {run.status.value}")
                    continue

                elif node.type == "report":
                    run_id = ctx.get("run_id")
                    execution.node_states[node_id] = {
                        "status": "COMPLETED",
                        "run_id": str(run_id) if run_id else None,
                    }
                    e_store.save(execution)
                    continue

                execution.node_states[node_id] = {"status": "COMPLETED"}
                e_store.save(execution)

            except Exception as exc:
                execution.node_states[node_id] = {"status": "FAILED", "error": str(exc)}
                execution.status = PipelineExecutionStatus.FAILED
                e_store.save(execution)
                return

        execution.status = PipelineExecutionStatus.COMPLETED
        e_store.save(execution)

    except Exception:
        execution.status = PipelineExecutionStatus.FAILED
        e_store.save(execution)


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/pipelines", response_model=PipelineListResponse)
def list_pipelines() -> PipelineListResponse:
    store = get_pipeline_store()
    records = store.list()
    return PipelineListResponse(success=True, data=[_pipeline_to_payload(r) for r in records])


@router.post("/pipelines", response_model=PipelineResponse)
def create_pipeline(request: CreatePipelineRequest) -> PipelineResponse:
    store = get_pipeline_store()
    record = store.create(name=request.name, description=request.description)
    return PipelineResponse(success=True, data=_pipeline_to_payload(record))


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
def get_pipeline(pipeline_id: str) -> PipelineResponse:
    store = get_pipeline_store()
    try:
        record = store.get(pipeline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Pipeline not found: {pipeline_id}"})
    return PipelineResponse(success=True, data=_pipeline_to_payload(record))


@router.put("/pipelines/{pipeline_id}", response_model=PipelineResponse)
def update_pipeline(pipeline_id: str, request: UpdatePipelineRequest) -> PipelineResponse:
    store = get_pipeline_store()
    try:
        record = store.get(pipeline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Pipeline not found: {pipeline_id}"})
    if request.name is not None:
        record.name = request.name
    if request.description is not None:
        record.description = request.description
    if request.nodes is not None:
        record.nodes = [
            PipelineNodeDef(node_id=n.node_id, type=n.type, position=n.position, data=n.data)
            for n in request.nodes
        ]
    if request.edges is not None:
        record.edges = [
            PipelineEdgeDef(
                edge_id=e.edge_id,
                source=e.source,
                source_handle=e.source_handle,
                target=e.target,
                target_handle=e.target_handle,
            )
            for e in request.edges
        ]
    record = store.save(record)
    return PipelineResponse(success=True, data=_pipeline_to_payload(record))


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: str) -> dict:
    store = get_pipeline_store()
    try:
        store.delete(pipeline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Pipeline not found: {pipeline_id}"})
    return {"success": True}


# ---------------------------------------------------------------------------
# Validation and execution
# ---------------------------------------------------------------------------

@router.post("/pipelines/{pipeline_id}/validate", response_model=PipelineValidationResponse)
def validate_pipeline(pipeline_id: str) -> PipelineValidationResponse:
    store = get_pipeline_store()
    try:
        record = store.get(pipeline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Pipeline not found: {pipeline_id}"})
    result = _validate_pipeline(record)
    return PipelineValidationResponse(success=True, data=result)


@router.post("/pipelines/{pipeline_id}/execute", response_model=PipelineExecutionResponse)
def execute_pipeline(pipeline_id: str) -> PipelineExecutionResponse:
    p_store = get_pipeline_store()
    try:
        record = p_store.get(pipeline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Pipeline not found: {pipeline_id}"})

    validation = _validate_pipeline(record)
    if not validation.valid:
        raise HTTPException(status_code=422, detail={"message": validation.errors[0].message})

    e_store = get_pipeline_execution_store()
    execution = e_store.create(pipeline_id=pipeline_id)

    thread = threading.Thread(
        target=_run_pipeline_async,
        args=(pipeline_id, execution.execution_id),
        daemon=True,
    )
    thread.start()

    return PipelineExecutionResponse(success=True, data=_execution_to_payload(execution))


@router.get("/pipelines/{pipeline_id}/executions", response_model=PipelineExecutionListResponse)
def list_pipeline_executions(pipeline_id: str) -> PipelineExecutionListResponse:
    e_store = get_pipeline_execution_store()
    records = e_store.list_for_pipeline(pipeline_id)
    return PipelineExecutionListResponse(success=True, data=[_execution_to_payload(r) for r in records])


@router.get("/pipeline-executions/{execution_id}", response_model=PipelineExecutionResponse)
def get_pipeline_execution(execution_id: str) -> PipelineExecutionResponse:
    e_store = get_pipeline_execution_store()
    try:
        record = e_store.get(execution_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Execution not found: {execution_id}"})
    return PipelineExecutionResponse(success=True, data=_execution_to_payload(record))


@router.post("/pipeline-executions/{execution_id}/stop")
def stop_pipeline_execution(execution_id: str) -> dict:
    e_store = get_pipeline_execution_store()
    try:
        record = e_store.get(execution_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Execution not found: {execution_id}"})
    record.status = PipelineExecutionStatus.STOPPED
    e_store.save(record)
    return {"success": True}
