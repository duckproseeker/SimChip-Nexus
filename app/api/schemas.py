from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str = Field(description="错误代码")
    message: str = Field(description="错误说明")


class ApiResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True, description="请求是否成功")
    data: T | None = Field(default=None, description="业务数据")
    error: ErrorBody | None = Field(default=None, description="错误信息")


class CreateRunRequest(BaseModel):
    descriptor: dict[str, Any] | None = Field(
        default=None,
        description="场景 descriptor 对象。与 descriptor_path 二选一。",
    )
    descriptor_path: str | None = Field(
        default=None,
        description="容器内可读的 descriptor 文件路径。与 descriptor 二选一。",
    )
    hil_config: HilConfigPayload | None = Field(
        default=None,
        description="阶段二 HIL 运行配置。未提供时保持当前纯 CARLA 控制模式。",
    )
    evaluation_profile: EvaluationProfilePayload | None = Field(
        default=None,
        description="阶段二评测配置。未提供时不绑定评测模板。",
    )

    @model_validator(mode="after")
    def validate_source(self) -> CreateRunRequest:
        if self.descriptor is None and self.descriptor_path is None:
            raise ValueError("descriptor 或 descriptor_path 至少提供一个")
        return self


class RunSummary(BaseModel):
    run_id: str
    status: str
    scenario_name: str
    map_name: str
    start_time: str | None = None
    end_time: str | None = None
    error_reason: str | None = None


class HilConfigPayload(BaseModel):
    mode: str = Field(default="camera_open_loop")
    gateway_id: str | None = Field(
        default=None,
        description="绑定的网关 ID。对于仅拉起 Host/Pi sidecar 的本地演示链路可为空。",
    )
    video_source: str = Field(default="hdmi_x1301")
    dut_input_mode: str = Field(default="uvc_camera")
    result_ingest_mode: str = Field(default="http_push")

    @field_validator("mode", "video_source", "dut_input_mode", "result_ingest_mode")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must not be empty")
        return value.strip()

    @field_validator("gateway_id")
    @classmethod
    def validate_optional_gateway_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EvaluationProfilePayload(BaseModel):
    profile_name: str = Field(default="yolo_open_loop_v1")
    metrics: list[str] = Field(
        default_factory=lambda: [
            "precision",
            "recall",
            "map50",
            "avg_latency_ms",
            "p95_latency_ms",
            "fps",
            "frame_drop_rate",
        ]
    )
    iou_threshold: float = Field(default=0.5, ge=0.1, le=1.0)
    classes: list[str] = Field(default_factory=list)

    @field_validator("profile_name")
    @classmethod
    def validate_profile_name(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("profile_name must not be empty")
        return value.strip()


class WeatherPayload(BaseModel):
    preset: str = Field(default="ClearNoon")
    cloudiness: float | None = Field(default=None, ge=0.0, le=100.0)
    precipitation: float | None = Field(default=None, ge=0.0, le=100.0)
    precipitation_deposits: float | None = Field(default=None, ge=0.0, le=100.0)
    wind_intensity: float | None = Field(default=None, ge=0.0, le=100.0)
    wetness: float | None = Field(default=None, ge=0.0, le=100.0)
    fog_density: float | None = Field(default=None, ge=0.0, le=100.0)
    sun_altitude_angle: float | None = Field(default=None, ge=-90.0, le=90.0)
    sun_azimuth_angle: float | None = Field(default=None, ge=0.0, le=360.0)

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("weather preset must not be empty")
        return value.strip()


class TrafficPayload(BaseModel):
    num_vehicles: int = Field(default=0, ge=0, le=128)
    num_walkers: int = Field(default=0, ge=0, le=128)
    seed: int | None = Field(default=None, ge=0, le=2147483647)


class ScenarioTemplateParameterPayload(BaseModel):
    field: str
    label: str
    description: str | None = None
    type: str
    parameter_type: str | None = None
    required: bool = False
    default: bool | int | float | str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = None
    options: list[str] = Field(default_factory=list)


class ScenarioLaunchCapabilitiesPayload(BaseModel):
    map_editable: bool = False
    weather_editable: bool = False
    traffic_vehicle_count_editable: bool = False
    traffic_walker_count_editable: bool = False
    sensor_profile_editable: bool = False
    timeout_editable: bool = False
    max_vehicle_count: int = 0
    max_walker_count: int = 0
    notes: list[str] = Field(default_factory=list)


class ScenarioLaunchRequest(BaseModel):
    scenario_id: str
    map_name: str | None = None
    weather: WeatherPayload | None = None
    traffic: TrafficPayload = Field(default_factory=TrafficPayload)
    sensor_profile_name: str | None = None
    template_params: dict[str, bool | int | float | str] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, ge=1, le=86400)
    auto_start: bool = True
    metadata: ScenarioMetadataPayload | None = None

    @field_validator("scenario_id")
    @classmethod
    def validate_scenario_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("scenario_id must not be empty")
        return value.strip()

    @field_validator("map_name")
    @classmethod
    def validate_map_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("sensor_profile_name")
    @classmethod
    def validate_sensor_profile_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("template_params")
    @classmethod
    def validate_template_params(
        cls, value: dict[str, bool | int | float | str]
    ) -> dict[str, bool | int | float | str]:
        normalized: dict[str, bool | int | float | str] = {}
        for key, item in value.items():
            field = str(key).strip()
            if not field:
                raise ValueError("template_params field name must not be empty")
            normalized[field] = item
        return normalized


class RunEnvironmentUpdateRequest(BaseModel):
    weather: WeatherPayload
    debug: dict[str, Any] | None = None


class GatewayRegisterRequest(BaseModel):
    gateway_id: str
    name: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    agent_version: str | None = None
    address: str | None = None

    @field_validator("gateway_id", "name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must not be empty")
        return value.strip()


class GatewayHeartbeatRequest(BaseModel):
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    current_run_id: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("status must not be empty")
        return value.strip().upper()


class CreateCaptureRequest(BaseModel):
    gateway_id: str
    source: str = Field(default="hdmi_x1301")
    save_format: str = Field(default="jpg")
    sample_fps: float = Field(default=2.0, gt=0.0, le=30.0)
    max_frames: int = Field(default=300, ge=1, le=100000)
    save_dir: str
    note: str | None = None

    @field_validator("gateway_id", "source", "save_format", "save_dir")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must not be empty")
        return value.strip()

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in {"hdmi_x1301", "frame_stream"}:
            raise ValueError("source must be one of: hdmi_x1301, frame_stream")
        return normalized

    @field_validator("save_format")
    @classmethod
    def validate_save_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"jpg", "png", "raw"}:
            raise ValueError("save_format must be one of: jpg, png, raw")
        return normalized


class CaptureFramePayload(BaseModel):
    frame_index: int = Field(ge=0)
    captured_at_utc: str | None = None
    relative_path: str
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    size_bytes: int | None = Field(default=None, ge=0)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("relative_path must not be empty")
        return value.strip()


class CaptureSyncRequest(BaseModel):
    status: str | None = None
    saved_frames: int | None = Field(default=None, ge=0)
    error_reason: str | None = None
    frames: list[CaptureFramePayload] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("status must not be empty")
        return value.strip().upper()


class BenchmarkTaskScenarioMatrixItemPayload(BaseModel):
    scenario_id: str
    map_name: str | None = None
    environment_preset_id: str | None = None
    sensor_profile_name: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=86400)

    @field_validator("scenario_id")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must not be empty")
        return value.strip()

    @field_validator("map_name", "environment_preset_id", "sensor_profile_name")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CreateBenchmarkTaskRequest(BaseModel):
    project_id: str | None = None
    benchmark_definition_id: str
    dut_model: str | None = None
    scenario_matrix: list[BenchmarkTaskScenarioMatrixItemPayload] = Field(default_factory=list)
    selected_scenario_ids: list[str] = Field(default_factory=list)
    run_duration_seconds: int | None = Field(default=None, ge=1, le=86400)
    hil_config: HilConfigPayload | None = None
    evaluation_profile_name: str | None = None
    auto_start: bool = False

    @field_validator("benchmark_definition_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("field must not be empty")
        return value.strip()

    @field_validator("project_id")
    @classmethod
    def validate_optional_project_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("dut_model")
    @classmethod
    def validate_dut_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("selected_scenario_ids")
    @classmethod
    def validate_selected_scenario_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            candidate = item.strip()
            if not candidate or candidate in seen:
                continue
            normalized.append(candidate)
            seen.add(candidate)
        return normalized


class ReportExportRequest(BaseModel):
    benchmark_task_id: str

    @field_validator("benchmark_task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("benchmark_task_id must not be empty")
        return value.strip()


class RerunBenchmarkTaskRequest(BaseModel):
    auto_start: bool = True


class RunDebugPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    viewer_friendly: bool | None = None


class ScenarioMetadataPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    author: str = ""
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    dut_model: str | None = None


class SensorSpecPayload(BaseModel):
    id: str
    type: str
    x: float | None = None
    y: float | None = None
    z: float | None = None
    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    width: int | None = None
    height: int | None = None
    fov: float | None = None
    horizontal_fov: float | None = None
    vertical_fov: float | None = None
    range: float | None = None
    channels: int | None = None
    points_per_second: int | None = None
    rotation_frequency: float | None = None
    reading_frequency: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class SensorsConfigPayload(BaseModel):
    enabled: bool
    auto_start: bool = False
    profile_name: str | None
    config_yaml_path: str | None
    sensors: list[SensorSpecPayload]


class RecorderConfigPayload(BaseModel):
    enabled: bool


class SensorProfilePayload(BaseModel):
    profile_name: str
    display_name: str
    description: str
    vehicle_model: str | None = None
    sensors: list[SensorSpecPayload]
    raw_yaml: str
    source_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SensorProfileSaveRequest(BaseModel):
    profile_name: str
    display_name: str
    description: str = ""
    vehicle_model: str | None = None
    sensors: list[SensorSpecPayload]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_name", "display_name")
    @classmethod
    def validate_sensor_profile_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must not be empty")
        return normalized

    @field_validator("vehicle_model")
    @classmethod
    def validate_vehicle_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("metadata must be a mapping")
        return value


class SensorProfileListPayload(BaseModel):
    items: list[SensorProfilePayload]


class RunRuntimeCapabilitiesPayload(BaseModel):
    weather_update: bool
    viewer_friendly: bool


class RunCreatePayload(BaseModel):
    run_id: str
    status: str
    hil_config: HilConfigPayload | None
    evaluation_profile: EvaluationProfilePayload | None


class RunPayload(BaseModel):
    run_id: str
    status: str
    scenario_name: str
    map_name: str
    created_at_utc: str | None
    updated_at_utc: str | None
    started_at_utc: str | None
    ended_at_utc: str | None
    created_time: str | None
    updated_time: str | None
    start_time: str | None
    end_time: str | None
    error_reason: str | None
    stop_requested: bool
    cancel_requested: bool
    hil_config: HilConfigPayload | None
    evaluation_profile: EvaluationProfilePayload | None
    artifact_dir: str
    execution_backend: str
    scenario_source: dict[str, Any] | None
    device_metrics: dict[str, Any] | None = None
    project_id: str | None
    project_name: str | None
    benchmark_definition_id: str | None
    benchmark_name: str | None
    benchmark_task_id: str | None
    dut_model: str | None
    metadata: ScenarioMetadataPayload
    weather: WeatherPayload
    traffic: TrafficPayload
    sensors: SensorsConfigPayload
    recorder: RecorderConfigPayload
    debug: RunDebugPayload
    runtime_capabilities: RunRuntimeCapabilitiesPayload
    sim_time: float | None
    current_tick: int | None
    executed_tick_count: int | None
    sim_elapsed_seconds: float | None
    achieved_tick_rate_hz: float | None
    wall_elapsed_seconds: float | None
    spawned_actors_count: int | None


class RunEventPayload(BaseModel):
    timestamp: str
    run_id: str
    level: str
    event_type: str
    message: str
    payload: dict[str, Any]


class SensorCaptureOutputPayload(BaseModel):
    sensor_id: str
    relative_dir: str
    sample_count: int = 0
    file_count: int = 0
    frame_file_count: int = 0
    record_count: int = 0
    latest_artifact_path: str | None = None


class SensorCaptureRuntimeControlPayload(BaseModel):
    enabled: bool
    auto_start: bool
    desired_state: str
    active: bool
    status: str
    profile_name: str | None
    sensor_count: int
    output_root: str | None
    manifest_path: str | None = None
    manifest: dict[str, Any] | None = None
    saved_frames: int = 0
    saved_samples: int = 0
    sensor_outputs: list[SensorCaptureOutputPayload] = Field(default_factory=list)
    worker_state_path: str | None = None
    worker_log_path: str | None = None
    worker_log_tail: str | None = None
    download_url: str | None = None
    last_error: str | None
    updated_at_utc: str | None


class RecorderRuntimeControlPayload(BaseModel):
    enabled: bool
    active: bool
    status: str
    output_path: str | None
    last_error: str | None
    updated_at_utc: str | None


class RunRuntimeControlPayload(BaseModel):
    weather: WeatherPayload | None
    debug: RunDebugPayload | None
    sensor_capture: SensorCaptureRuntimeControlPayload | None = None
    recorder: RecorderRuntimeControlPayload | None = None
    updated_at_utc: str | None


class RunEnvironmentStatePayload(BaseModel):
    run_id: str
    descriptor_weather: WeatherPayload
    descriptor_debug: RunDebugPayload
    weather: WeatherPayload | None = None
    runtime_control: RunRuntimeControlPayload


class RunViewerViewPayload(BaseModel):
    view_id: str
    label: str


class RunViewerInfoPayload(BaseModel):
    run_id: str
    available: bool
    reason: str | None
    views: list[RunViewerViewPayload]
    snapshot_url: str
    stream_ws_path: str
    refresh_interval_ms: int
    stream_interval_ms: int
    playback_interval_ms: int
    stream_buffer_min_frames: int
    stream_buffer_max_frames: int


class ProjectPayload(BaseModel):
    project_id: str
    name: str
    vendor: str
    processor: str
    description: str
    benchmark_focus: list[str]
    target_metrics: list[str]
    input_modes: list[str]
    status: str
    created_at_utc: str | None
    updated_at_utc: str | None


class BenchmarkDefinitionPayload(BaseModel):
    benchmark_definition_id: str
    name: str
    description: str
    focus_metrics: list[str]
    cadence: str
    report_shape: str
    project_ids: list[str]
    default_project_id: str | None
    default_evaluation_profile_name: str | None
    planning_mode: str
    candidate_scenario_ids: list[str]
    supports_duration_seconds: bool
    default_duration_seconds: int | None
    queue_note: str | None
    created_at_utc: str | None
    updated_at_utc: str | None


class BenchmarkTaskScenarioMatrixEntryPayload(BaseModel):
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
    resolved_timeout_seconds: int


class BenchmarkTaskSummaryCountsPayload(BaseModel):
    total_runs: int | None = None
    created_runs: int | None = None
    queued_runs: int | None = None
    completed_runs: int | None = None
    failed_runs: int | None = None
    canceled_runs: int | None = None
    running_runs: int | None = None


class BenchmarkTaskSummaryMetricsPayload(BaseModel):
    fps: float | None = None
    latency_ms: float | None = None
    map: float | None = None
    power_w: float | None = None
    temperature_c: float | None = None
    frame_drop_rate: float | None = None
    pass_rate: float | None = None
    anomaly_rate: float | None = None


class BenchmarkTaskScenarioBreakdownPayload(BaseModel):
    total_runs: int
    completed: int
    failed: int
    canceled: int


class BenchmarkTaskOrderedRunPayload(BaseModel):
    position: int
    run_id: str
    scenario_id: str | None = None
    scenario_display_name: str
    display_map_name: str
    execution_backend: str
    status: str
    is_active: bool = False
    is_next: bool = False
    started_at_utc: str | None = None
    ended_at_utc: str | None = None
    error_reason: str | None = None


class BenchmarkTaskExecutionQueuePayload(BaseModel):
    active_run_id: str | None = None
    next_run_id: str | None = None
    completed_run_ids: list[str] = Field(default_factory=list)
    failed_run_ids: list[str] = Field(default_factory=list)
    canceled_run_ids: list[str] = Field(default_factory=list)
    queued_run_ids: list[str] = Field(default_factory=list)
    ordered_runs: list[BenchmarkTaskOrderedRunPayload] = Field(default_factory=list)


class BenchmarkTaskSummaryPayload(BaseModel):
    counts: BenchmarkTaskSummaryCountsPayload | None = None
    metrics: BenchmarkTaskSummaryMetricsPayload | None = None
    scenario_breakdown: dict[str, BenchmarkTaskScenarioBreakdownPayload] | None = None
    gateway_snapshot: dict[str, Any] | None = None
    execution_queue: BenchmarkTaskExecutionQueuePayload | None = None


class BenchmarkTaskPayload(BaseModel):
    benchmark_task_id: str
    project_id: str
    project_name: str
    dut_model: str | None = None
    benchmark_definition_id: str
    benchmark_name: str
    status: str
    planned_run_count: int
    counts_by_status: dict[str, int]
    run_ids: list[str]
    scenario_matrix: list[BenchmarkTaskScenarioMatrixEntryPayload]
    planning_mode: str
    selected_scenario_ids: list[str]
    requested_duration_seconds: int | None
    hil_config: HilConfigPayload | None
    evaluation_profile_name: str | None
    auto_start: bool
    summary: BenchmarkTaskSummaryPayload
    created_at_utc: str | None
    updated_at_utc: str | None
    started_at_utc: str | None
    ended_at_utc: str | None


class ReportPayload(BaseModel):
    report_id: str
    benchmark_task_id: str
    project_id: str
    benchmark_definition_id: str
    dut_model: str | None
    title: str
    status: str
    artifact_dir: str
    json_path: str
    markdown_path: str
    summary: BenchmarkTaskSummaryPayload
    created_at_utc: str | None
    updated_at_utc: str | None


class ReportsWorkspaceSummaryPayload(BaseModel):
    project_count: int
    report_count: int
    benchmark_task_count: int
    exportable_task_count: int
    pending_report_task_count: int
    recent_failure_count: int


class ReportsWorkspacePayload(BaseModel):
    summary: ReportsWorkspaceSummaryPayload
    projects: list[ProjectPayload]
    reports: list[ReportPayload]
    benchmark_tasks: list[BenchmarkTaskPayload]
    exportable_tasks: list[BenchmarkTaskPayload]
    pending_report_tasks: list[BenchmarkTaskPayload]
    recent_failures: list[RunPayload]


class BenchmarkDefinitionListPayload(BaseModel):
    definitions: list[BenchmarkDefinitionPayload]


class BenchmarkTaskListPayload(BaseModel):
    tasks: list[BenchmarkTaskPayload]


class ReportListPayload(BaseModel):
    reports: list[ReportPayload]


class RunCreateResponse(ApiResponse[RunCreatePayload]):
    pass


class RunResponse(ApiResponse[RunPayload]):
    pass


class RunListResponse(ApiResponse[list[RunPayload]]):
    pass


class RunEventListResponse(ApiResponse[list[RunEventPayload]]):
    pass


class RunEnvironmentStateResponse(ApiResponse[RunEnvironmentStatePayload]):
    pass


class RunViewerInfoResponse(ApiResponse[RunViewerInfoPayload]):
    pass


class SensorProfileResponse(ApiResponse[SensorProfilePayload]):
    pass


class SensorProfileListResponse(ApiResponse[SensorProfileListPayload]):
    pass


class BenchmarkDefinitionResponse(ApiResponse[BenchmarkDefinitionPayload]):
    pass


class BenchmarkDefinitionListResponse(ApiResponse[BenchmarkDefinitionListPayload]):
    pass


class BenchmarkTaskResponse(ApiResponse[BenchmarkTaskPayload]):
    pass


class BenchmarkTaskListResponse(ApiResponse[BenchmarkTaskListPayload]):
    pass


class ReportResponse(ApiResponse[ReportPayload]):
    pass


class ReportListResponse(ApiResponse[ReportListPayload]):
    pass


class ReportsWorkspaceResponse(ApiResponse[ReportsWorkspacePayload]):
    pass
