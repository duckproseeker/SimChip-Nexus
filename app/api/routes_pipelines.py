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
    NODE_PORT_SCHEMA,
    PipelineEdgeDef,
    PipelineExecutionStatus,
    PipelineNodeDef,
    PipelineRecord,
    PortType,
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
            k: PipelineNodeStatePayload(**v) if isinstance(v, dict) else PipelineNodeStatePayload(status=str(v))
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


def validate_pipeline_graph(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Validate a pipeline graph using the new typed port system."""
    errors: list[str] = []
    node_map = {n["node_id"]: n for n in nodes}

    # Must have at least one scene_replay
    scene_nodes = [n for n in nodes if n["type"] == "scene_replay"]
    if not scene_nodes:
        errors.append("需要至少一个 scene_replay 节点")

    # Check unknown node types
    for n in nodes:
        if n["type"] not in NODE_PORT_SCHEMA:
            errors.append(f"未知节点类型: {n['type']}")

    # Check edge type compatibility
    for e in edges:
        src = node_map.get(e["source"])
        tgt = node_map.get(e["target"])
        if not src or not tgt:
            errors.append(f"边引用了不存在的节点: {e['edge_id']}")
            continue
        src_schema = NODE_PORT_SCHEMA.get(src["type"])
        tgt_schema = NODE_PORT_SCHEMA.get(tgt["type"])
        if not src_schema or not tgt_schema:
            continue
        src_port_type = e.get("source_handle", "")
        tgt_port_type = e.get("target_handle", "")
        if src_port_type and PortType(src_port_type) not in src_schema["outputs"]:
            errors.append(f"节点 {src['node_id']} 没有 {src_port_type} 输出端口")
        if tgt_port_type and PortType(tgt_port_type) not in tgt_schema["inputs"]:
            errors.append(f"节点 {tgt['node_id']} 没有 {tgt_port_type} 输入端口")
        if src_port_type and tgt_port_type and src_port_type != tgt_port_type:
            errors.append(f"端口类型不匹配: {src_port_type} → {tgt_port_type}")

    # Cycle detection (Kahn's algorithm)
    in_degree: dict[str, int] = {n["node_id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["node_id"]: [] for n in nodes}
    for e in edges:
        if e["source"] in adj and e["target"] in in_degree:
            adj[e["source"]].append(e["target"])
            in_degree[e["target"]] += 1
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        nid = queue.pop(0)
        visited += 1
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if visited < len(nodes):
        errors.append("检测到环路 (cycle)")

    return errors


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
def execute_pipeline(pipeline_id: str, body: dict | None = None) -> PipelineExecutionResponse:
    from pydantic import BaseModel

    p_store = get_pipeline_store()
    try:
        record = p_store.get(pipeline_id)
    except KeyError:
        raise HTTPException(status_code=404, detail={"message": f"Pipeline not found: {pipeline_id}"})

    # Parse execution mode from body
    body = body or {}
    mode = body.get("mode", "legacy")  # "offline_render" | "online_play" | "legacy"
    options = body.get("options", {})

    # Determine if pipeline uses new-style typed nodes
    new_style = any(n.type in NODE_PORT_SCHEMA for n in record.nodes)

    if new_style:
        # New validation using port-type system
        nodes_raw = [n.model_dump() for n in record.nodes]
        edges_raw = [e.model_dump() for e in record.edges]
        errors = validate_pipeline_graph(nodes_raw, edges_raw)
        if errors:
            raise HTTPException(status_code=422, detail={"validation_errors": errors})
    else:
        # Legacy validation for old-style nodes
        validation = _validate_pipeline(record)
        if not validation.valid:
            raise HTTPException(status_code=422, detail={"message": validation.errors[0].message})

    e_store = get_pipeline_execution_store()
    execution = e_store.create(pipeline_id=pipeline_id)

    if mode == "offline_render":
        thread = threading.Thread(
            target=_run_offline_render,
            args=(pipeline_id, execution.execution_id, options),
            daemon=True,
        )
    elif mode == "online_play":
        thread = threading.Thread(
            target=_run_online_play,
            args=(pipeline_id, execution.execution_id, options),
            daemon=True,
        )
    else:
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


# ---------------------------------------------------------------------------
# Execution mode handlers
# ---------------------------------------------------------------------------

def _run_offline_render(pipeline_id: str, execution_id: str, options: dict) -> None:
    """Extract sensor configs from pipeline and trigger offline rendering."""
    from app.core.models import SensorConfig
    from app.storage.dataset_store import get_dataset_store
    from app.storage.scenario_asset_store import get_scenario_asset_store
    import uuid

    p_store = get_pipeline_store()
    e_store = get_pipeline_execution_store()

    execution = e_store.get(execution_id)
    execution.status = PipelineExecutionStatus.RUNNING
    e_store.save(execution)

    try:
        pipeline = p_store.get(pipeline_id)

        scenario_log = ""
        scenario_id = ""
        for n in pipeline.nodes:
            if n.type == "scene_replay":
                scenario_id = n.data.get("scenario_id", "")
                scenario_log = n.data.get("recorder_log_path", "")
                break

        if not scenario_log and scenario_id:
            sc_store = get_scenario_asset_store()
            try:
                sc = sc_store.get(scenario_id)
                scenario_log = sc.recorder_log_path
            except KeyError:
                pass

        if not scenario_log:
            raise ValueError("No scenario log path found in pipeline")

        # Get scenario duration to limit render frames
        scenario_duration = 0.0
        if scenario_id:
            sc_store = get_scenario_asset_store()
            try:
                sc = sc_store.get(scenario_id)
                scenario_duration = sc.duration_seconds or 0.0
            except KeyError:
                pass

        sensor_type_map = {
            "camera": "sensor.camera.rgb",
            "lidar": "sensor.lidar.ray_cast",
            "radar": "sensor.other.radar",
            "gnss": "sensor.other.gnss",
            "imu": "sensor.other.imu",
        }
        sensor_configs: list[SensorConfig] = []
        for n in pipeline.nodes:
            if n.type in sensor_type_map:
                cfg = SensorConfig(
                    sensor_id=n.data.get("sensor_id", n.node_id),
                    sensor_type=sensor_type_map[n.type],
                    transform={
                        "x": n.data.get("x", 1.5),
                        "y": n.data.get("y", 0.0),
                        "z": n.data.get("z", 1.7),
                        "pitch": n.data.get("pitch", 0.0),
                        "yaw": n.data.get("yaw", 0.0),
                        "roll": n.data.get("roll", 0.0),
                    },
                    attributes={
                        k: v for k, v in n.data.items()
                        if k not in ("sensor_id", "x", "y", "z", "pitch", "yaw", "roll")
                    },
                )
                sensor_configs.append(cfg)

        if not sensor_configs:
            raise ValueError("No sensor nodes found in pipeline")

        # Extract weather override from env_override node
        weather_preset = ""
        for n in pipeline.nodes:
            if n.type == "env_override":
                weather_preset = n.data.get("weather_preset", "")
                break

        ds_store = get_dataset_store()
        dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
        output_dir = f"/ros2_ws/datasets/{dataset_id}"
        delta = options.get("delta_seconds", 0.05)

        from app.core.models import DatasetRecord, DatasetStatus
        record = DatasetRecord(
            dataset_id=dataset_id,
            scenario_id=scenario_id,
            pipeline_id=pipeline_id,
            name=f"{pipeline.name} render",
            status=DatasetStatus.PENDING,
            sensor_configs=sensor_configs,
            delta_seconds=delta,
            duration_seconds=scenario_duration,
            output_dir=output_dir,
        )
        ds_store.create(record)

        execution.node_states["_dataset_id"] = dataset_id
        execution.status = PipelineExecutionStatus.RUNNING
        e_store.save(execution)

        from app.executor.offline_renderer import start_render_sync, is_rendering
        if is_rendering():
            raise ValueError("渲染进程忙，请等待当前渲染完成后再试")

        start_render_sync(
            dataset_id=dataset_id,
            scenario_log_path=scenario_log,
            sensor_configs=sensor_configs,
            output_dir=output_dir,
            delta_seconds=delta,
            duration=options.get("duration", 0.0) or scenario_duration,
            start_time=options.get("start_time", 0.0),
            weather_preset=weather_preset,
        )

        execution.status = PipelineExecutionStatus.COMPLETED
        e_store.save(execution)

    except Exception as e:
        execution.status = PipelineExecutionStatus.FAILED
        execution.node_states["_error"] = str(e)
        e_store.save(execution)


def _run_online_play(pipeline_id: str, execution_id: str, options: dict) -> None:
    """Play a pre-rendered dataset fullscreen or via RTP."""
    from app.executor.online_player import start_playback
    from app.storage.dataset_store import get_dataset_store

    e_store = get_pipeline_execution_store()
    execution = e_store.get(execution_id)
    execution.status = PipelineExecutionStatus.RUNNING
    e_store.save(execution)

    try:
        dataset_id = options.get("dataset_id", "")
        if not dataset_id:
            raise ValueError("dataset_id required for online_play mode")

        ds_store = get_dataset_store()
        dataset = ds_store.get(dataset_id)

        sensor_id = options.get("sensor_id", "")
        if not sensor_id and dataset.sensor_configs:
            sensor_id = dataset.sensor_configs[0].sensor_id

        target_fps = options.get("target_fps", 30.0)
        mode = options.get("output_mode", "display")

        session = start_playback(
            dataset_id=dataset_id,
            output_dir=dataset.output_dir,
            sensor_id=sensor_id,
            target_fps=target_fps,
            mode=mode,
        )

        while session.running:
            import time
            time.sleep(0.5)

        execution.status = PipelineExecutionStatus.COMPLETED
        e_store.save(execution)

    except Exception as e:
        execution.status = PipelineExecutionStatus.FAILED
        execution.node_states["_error"] = str(e)
        e_store.save(execution)
