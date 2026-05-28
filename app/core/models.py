from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class EventLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class GatewayStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    READY = "READY"
    BUSY = "BUSY"
    ERROR = "ERROR"
    OFFLINE = "OFFLINE"


class CaptureStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PILOT = "PILOT"
    ARCHIVED = "ARCHIVED"


class BenchmarkPlanningMode(str, Enum):
    SINGLE_SCENARIO = "single_scenario"
    TIMED_SINGLE_SCENARIO = "timed_single_scenario"
    ALL_RUNNABLE = "all_runnable"
    CUSTOM_MULTI_SCENARIO = "custom_multi_scenario"


class BenchmarkTaskStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL_FAILED = "PARTIAL_FAILED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class ReportStatus(str, Enum):
    READY = "READY"
    FAILED = "FAILED"


class RunEvent(BaseModel):
    timestamp: datetime
    run_id: str
    level: EventLevel = EventLevel.INFO
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RunMetrics(BaseModel):
    run_id: str
    scenario_name: str
    map_name: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    final_status: RunStatus | None = None
    failure_reason: str | None = None
    current_tick: int | None = None
    sim_time: float | None = None
    executed_tick_count: int | None = None
    sim_elapsed_seconds: float | None = None
    achieved_tick_rate_hz: float | None = None
    wall_time: float | None = None
    spawned_actors_count: int = 0


class RunRecord(BaseModel):
    run_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_reason: str | None = None
    stop_requested: bool = False
    cancel_requested: bool = False
    scenario_name: str
    map_name: str
    descriptor: dict[str, Any]
    hil_config: dict[str, Any] | None = None
    evaluation_profile: dict[str, Any] | None = None
    artifact_dir: str
    execution_backend: str = "native"
    scenario_source: dict[str, Any] | None = None


class ScenarioRecordingRecord(BaseModel):
    recording_id: str
    name: str | None = None
    source_run_id: str
    source_run_status: str | None = None
    source_id: str | None = None
    source_provider: str | None = None
    materialization_id: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    scenario_name: str
    map_name: str
    carla_version: str | None = None
    map_version: str | None = None
    recorder_log_path: str
    recorder_file_size_bytes: int = 0
    recorder_file_sha256: str | None = None
    duration_seconds: float | None = None
    recommended_start_seconds: float | None = None
    recommended_duration_seconds: float | None = None
    tags: list[str] = Field(default_factory=list)
    corner_case_labels: list[str] = Field(default_factory=list)
    weather: dict[str, Any] = Field(default_factory=dict)
    traffic_density: dict[str, Any] = Field(default_factory=dict)
    sensor_profile_name: str | None = None
    determinism_level: str = "world_state_replay_with_carla_live_sensors"
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class RecordingReplayRunRecord(BaseModel):
    recording_id: str
    run_id: str
    start_seconds: float
    duration_seconds: float
    sensor_mode: str = "carla_live"
    sensor_profile_id: str
    sensor_profile_hash: str
    sensor_profile_snapshot: dict[str, Any] = Field(default_factory=dict)
    preview_sensor_id: str
    preview_sensor_snapshot: dict[str, Any] = Field(default_factory=dict)
    fixed_delta_seconds: float
    sensor_warmup_seconds: float = 0.0
    timebase: str = "synchronous_fixed_delta"
    hil_clock_mode: str = "fixed_delta"
    output_config_summary: dict[str, Any] = Field(default_factory=dict)
    report_config_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SensorProfileRecord(BaseModel):
    sensor_profile_id: str
    name: str
    sensors: list[dict[str, Any]]
    profile_hash: str
    fixed_delta_seconds: float = 0.05
    expected_fps: float = 20.0
    output_mode: str = "carla_live"
    hil_output_mode: str = "camera_open_loop"
    description: str = ""
    vehicle_model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_path: str | None = None
    raw_yaml: str = ""
    created_at: datetime
    updated_at: datetime


class ScenarioSourceRecord(BaseModel):
    source_id: str
    provider: str
    provider_version: dict[str, Any] = Field(default_factory=dict)
    source_path: str
    source_hash: str
    route_id: str | None = None
    scenario_type: str | None = None
    map_name: str
    weather: dict[str, Any] = Field(default_factory=dict)
    recommended_duration_seconds: float | None = None
    corner_case_labels: list[str] = Field(default_factory=list)
    compatibility_status: str = "ok"
    compatibility_message: str | None = None
    parsed_metadata: dict[str, Any] = Field(default_factory=dict)
    discovered_at: datetime
    updated_at: datetime


class ScenarioSourceMaterializationRecord(BaseModel):
    materialization_id: str
    source_id: str
    run_id: str
    recording_id: str | None = None
    status: str
    sensor_profile_id: str | None = None
    sensor_profile_hash: str | None = None
    fixed_delta_seconds: float
    materialization_agent_type: str
    materialization_agent_hash: str
    recorder_file_sha256: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class GatewayRecord(BaseModel):
    gateway_id: str
    name: str
    status: GatewayStatus = GatewayStatus.UNKNOWN
    capabilities: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    agent_version: str | None = None
    address: str | None = None
    current_run_id: str | None = None
    last_heartbeat_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CaptureFrameRecord(BaseModel):
    frame_index: int
    captured_at_utc: datetime | None = None
    relative_path: str
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None


class CaptureRecord(BaseModel):
    capture_id: str
    gateway_id: str
    source: str
    save_format: str
    sample_fps: float
    max_frames: int | None = None
    save_dir: str
    manifest_path: str
    note: str | None = None
    status: CaptureStatus
    saved_frames: int = 0
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_reason: str | None = None


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    vendor: str
    processor: str
    description: str
    benchmark_focus: list[str] = Field(default_factory=list)
    target_metrics: list[str] = Field(default_factory=list)
    input_modes: list[str] = Field(default_factory=list)
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class BenchmarkDefinitionRecord(BaseModel):
    benchmark_definition_id: str
    name: str
    description: str
    focus_metrics: list[str] = Field(default_factory=list)
    cadence: str
    report_shape: str
    project_ids: list[str] = Field(default_factory=list)
    default_project_id: str | None = None
    default_evaluation_profile_name: str | None = None
    planning_mode: BenchmarkPlanningMode = BenchmarkPlanningMode.CUSTOM_MULTI_SCENARIO
    candidate_scenario_ids: list[str] = Field(default_factory=list)
    supports_duration_seconds: bool = False
    default_duration_seconds: int | None = None
    queue_note: str | None = None
    created_at: datetime
    updated_at: datetime


class BenchmarkTaskMatrixEntry(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_display_name: str
    execution_backend: str = "native"
    requested_map_name: str
    resolved_map_name: str
    display_map_name: str
    environment_preset_id: str
    environment_name: str
    sensor_profile_name: str
    requested_timeout_seconds: int | None = None
    resolved_timeout_seconds: int = 30


class BenchmarkTaskRecord(BaseModel):
    benchmark_task_id: str
    project_id: str
    project_name: str
    dut_model: str | None = None
    benchmark_definition_id: str
    benchmark_name: str
    status: BenchmarkTaskStatus = BenchmarkTaskStatus.CREATED
    planned_run_count: int = 0
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    run_ids: list[str] = Field(default_factory=list)
    scenario_matrix: list[BenchmarkTaskMatrixEntry] = Field(default_factory=list)
    planning_mode: BenchmarkPlanningMode = BenchmarkPlanningMode.CUSTOM_MULTI_SCENARIO
    selected_scenario_ids: list[str] = Field(default_factory=list)
    requested_duration_seconds: int | None = None
    hil_config: dict[str, Any] | None = None
    evaluation_profile_name: str | None = None
    auto_start: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ReportRecord(BaseModel):
    report_id: str
    benchmark_task_id: str
    project_id: str
    benchmark_definition_id: str
    dut_model: str | None = None
    title: str
    status: ReportStatus = ReportStatus.READY
    artifact_dir: str
    json_path: str
    markdown_path: str
    summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PortType(str, Enum):
    SCENE = "scene"
    SENSOR_DATA = "sensor_data"
    STREAM = "stream"


class NodeCategory(str, Enum):
    SCENE_SOURCE = "scene_source"
    ENV_OVERRIDE = "env_override"
    SENSOR = "sensor"
    OUTPUT = "output"
    TERMINAL = "terminal"


NODE_PORT_SCHEMA: dict[str, dict] = {
    "scene_replay": {"inputs": [], "outputs": [PortType.SCENE], "category": NodeCategory.SCENE_SOURCE},
    "env_override": {"inputs": [PortType.SCENE], "outputs": [PortType.SCENE], "category": NodeCategory.ENV_OVERRIDE},
    "camera": {"inputs": [PortType.SCENE], "outputs": [PortType.SENSOR_DATA], "category": NodeCategory.SENSOR},
    "lidar": {"inputs": [PortType.SCENE], "outputs": [PortType.SENSOR_DATA], "category": NodeCategory.SENSOR},
    "radar": {"inputs": [PortType.SCENE], "outputs": [PortType.SENSOR_DATA], "category": NodeCategory.SENSOR},
    "gnss": {"inputs": [PortType.SCENE], "outputs": [PortType.SENSOR_DATA], "category": NodeCategory.SENSOR},
    "imu": {"inputs": [PortType.SCENE], "outputs": [PortType.SENSOR_DATA], "category": NodeCategory.SENSOR},
    "rtp_output": {"inputs": [PortType.SENSOR_DATA], "outputs": [PortType.STREAM], "category": NodeCategory.OUTPUT},
    "pointcloud_output": {"inputs": [PortType.SENSOR_DATA], "outputs": [PortType.STREAM], "category": NodeCategory.OUTPUT},
    "raw_output": {"inputs": [PortType.SENSOR_DATA], "outputs": [PortType.STREAM], "category": NodeCategory.OUTPUT},
    "dut": {"inputs": [PortType.STREAM], "outputs": [], "category": NodeCategory.TERMINAL},
}


class PipelineExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class PipelineNodeDef(BaseModel):
    node_id: str = Field(description="Unique node identifier within the pipeline")
    type: str = Field(
        description=(
            "Node type. Valid: project | scenario | map | weather | recording | "
            "sensor_camera | sensor_lidar | sensor_radar | sensor_gnss | sensor_imu | "
            "live_run | replay_run | report. "
            "Legacy (migration warning only): scenario_config | sensor_profile | run"
        )
    )
    position: dict[str, float] = Field(description="Canvas position {x, y}")
    data: dict[str, Any] = Field(default_factory=dict, description="Node-specific configuration")


class PipelineEdgeDef(BaseModel):
    edge_id: str = Field(description="Unique edge identifier")
    source: str = Field(description="Source node_id")
    source_handle: str = Field(description="Output port name on source node")
    target: str = Field(description="Target node_id")
    target_handle: str = Field(description="Input port name on target node")


class PipelineRecord(BaseModel):
    pipeline_id: str = Field(description="UUID")
    name: str = Field(description="Human-readable pipeline name")
    description: str = Field(default="", description="Optional description")
    nodes: list[PipelineNodeDef] = Field(default_factory=list)
    edges: list[PipelineEdgeDef] = Field(default_factory=list)
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class PipelineExecutionRecord(BaseModel):
    execution_id: str = Field(description="UUID")
    pipeline_id: str = Field(description="Parent pipeline ID")
    status: PipelineExecutionStatus = Field(default=PipelineExecutionStatus.PENDING)
    node_states: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of node_id to {status, run_id?, error?}"
    )
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class ScenarioAsset(BaseModel):
    id: str
    name: str
    recorder_log_path: str
    map_name: str = ""
    duration_seconds: float = 0.0
    tags: list[str] = []
    description: str = ""
    file_size_bytes: int = 0
    created_at: str = ""
    metadata: dict[str, Any] = {}


class DatasetStatus(str, Enum):
    PENDING = "PENDING"
    RENDERING = "RENDERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SensorConfig(BaseModel):
    sensor_id: str
    sensor_type: str  # sensor.camera.rgb, sensor.lidar.ray_cast, sensor.other.radar, etc.
    transform: dict[str, float] = Field(default_factory=dict)  # x, y, z, roll, pitch, yaw
    attributes: dict[str, Any] = Field(default_factory=dict)  # width, height, fov, channels, range, etc.


class DatasetRecord(BaseModel):
    dataset_id: str
    scenario_id: str  # references ScenarioAsset.id
    pipeline_id: str = ""  # optional reference to pipeline that created it
    name: str
    status: DatasetStatus = DatasetStatus.PENDING
    sensor_configs: list[SensorConfig] = Field(default_factory=list)
    total_frames: int = 0
    rendered_frames: int = 0
    delta_seconds: float = 0.05
    duration_seconds: float = 0.0
    output_dir: str = ""
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""
