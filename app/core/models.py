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
