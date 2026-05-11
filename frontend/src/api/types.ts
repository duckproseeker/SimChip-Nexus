import type {
  BenchmarkDefinitionSchema,
  BenchmarkTaskSchema,
  CreateBenchmarkTaskPayloadSchema,
  CreateCapturePayloadSchema,
  CreateRunPayloadSchema,
  EvaluationProfilePayloadSchema,
  HilConfigPayloadSchema,
  ReportSchema,
  ReportExportPayloadSchema,
  ReportsWorkspaceSchema,
  RerunBenchmarkTaskPayloadSchema,
  RunEnvironmentStateSchema,
  RunEnvironmentUpdatePayloadSchema,
  RunEventSchema,
  RunRecordSchema,
  RunViewerInfoSchema
} from './generated/contracts';

export interface ApiError {
  code: string;
  message: string;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  error: ApiError | null;
}

type Present<T> = {
  [K in keyof T]-?: Exclude<T[K], undefined>;
};

export interface HealthStatus {
  status: string;
}

export interface ExecutorStatus {
  alive: boolean;
  status: string;
  active_run_id: string | null;
  last_command_run_id: string | null;
  last_heartbeat_at_utc: string | null;
  heartbeat_age_seconds: number | null;
  pending_commands: number;
  warning: string | null;
}

export interface SystemStatus {
  api: { status: string };
  executor: ExecutorStatus;
  counts: {
    runs: Record<string, number>;
    captures: Record<string, number>;
    gateways: Record<string, number>;
  };
  totals: {
    runs: number;
    captures: number;
    gateways: number;
  };
  capture_observability: {
    running_capture_ids: string[];
    completed_capture_ids: string[];
    latest_capture_id: string | null;
  };
  frontend: {
    bundle_present: boolean;
  };
  pi_gateway: PiGatewayRuntimeStatus;
}

export interface PiGatewayRuntimeStatus {
  status: 'READY' | 'OFFLINE' | 'UNKNOWN';
  configured: boolean;
  reachable: boolean;
  host: string | null;
  user: string | null;
  port: number | null;
  start_command_configured: boolean;
  stop_command_configured: boolean;
  last_probe_at_utc: string | null;
  warning: string | null;
}

export interface PiGatewayCommandResult {
  action: 'start' | 'stop';
  success: boolean;
  exit_code: number;
  output: string | null;
  status: PiGatewayRuntimeStatus;
}

export interface ScenarioDescriptor {
  version: number;
  scenario_name: string;
  map_name: string;
  weather: WeatherConfig;
  sync: {
    enabled: boolean;
    fixed_delta_seconds: number;
  };
  ego_vehicle: {
    blueprint: string;
    spawn_point: {
      x: number;
      y: number;
      z: number;
      roll: number;
      pitch: number;
      yaw: number;
    };
  };
  traffic: {
    enabled: boolean;
    num_vehicles: number;
    num_walkers: number;
    seed?: number | null;
    injection_mode?: string | null;
  };
  sensors: SensorsConfig;
  termination: {
    timeout_seconds: number;
    success_condition: string;
  };
  recorder: {
    enabled: boolean;
  };
  debug?: {
    viewer_friendly?: boolean;
  };
  metadata: {
    author: string;
    tags: string[];
    description: string;
    dut_model?: string | null;
  };
}

export interface WeatherConfig {
  preset: string;
  cloudiness?: number;
  precipitation?: number;
  precipitation_deposits?: number;
  wind_intensity?: number;
  wetness?: number;
  fog_density?: number;
  sun_altitude_angle?: number;
  sun_azimuth_angle?: number;
}

export interface SensorSpec {
  id: string;
  type: string;
  x?: number;
  y?: number;
  z?: number;
  roll?: number;
  pitch?: number;
  yaw?: number;
  width?: number;
  height?: number;
  fov?: number;
  horizontal_fov?: number;
  vertical_fov?: number;
  range?: number;
  channels?: number;
  points_per_second?: number;
  rotation_frequency?: number;
  reading_frequency?: number;
  attributes?: Record<string, unknown>;
}

export interface SensorsConfig {
  enabled: boolean;
  auto_start: boolean;
  profile_name?: string | null;
  config_yaml_path?: string | null;
  sensors: SensorSpec[];
}

export interface SensorCaptureRuntimeControl {
  enabled: boolean;
  auto_start: boolean;
  desired_state: string;
  active: boolean;
  status: string;
  profile_name: string | null;
  sensor_count: number;
  output_root: string | null;
  manifest_path: string | null;
  manifest: Record<string, unknown> | null;
  saved_frames: number;
  saved_samples: number;
  sensor_outputs: SensorCaptureOutputSummary[];
  worker_state_path: string | null;
  worker_log_path: string | null;
  worker_log_tail: string | null;
  download_url: string | null;
  last_error: string | null;
  updated_at_utc: string | null;
}

export interface SensorCaptureOutputSummary {
  sensor_id: string;
  relative_dir: string;
  sample_count: number;
  file_count: number;
  frame_file_count: number;
  record_count: number;
  latest_artifact_path: string | null;
}

export interface RecorderRuntimeControl {
  enabled: boolean;
  active: boolean;
  status: string;
  output_path: string | null;
  last_error: string | null;
  updated_at_utc: string | null;
}

export interface ScenarioCatalogItem {
  scenario_id: string;
  scenario_name: string;
  display_name: string;
  description: string;
  category: string;
  default_map_name: string;
  execution_support: 'native' | 'scenario_runner';
  execution_backend: 'native' | 'scenario_runner';
  launch_capabilities: ScenarioLaunchCapabilities;
  source: {
    provider: string;
    version?: string;
    class_name?: string;
    source_file?: string;
    reference?: string;
    relative_xosc_path?: string | null;
    resolved_xosc_path?: string | null;
  };
  preset: {
    locked_map_name: string;
    map_locked: boolean;
    event_locked: boolean;
    actors_locked: boolean;
    weather_runtime_editable: boolean;
    event_summary: string;
    actors_summary: string;
  };
  parameter_declarations: Array<{
    name: string;
    parameter_type: string;
    default_value: string;
  }>;
  parameter_schema: ScenarioTemplateParameterSchema[];
  descriptor_template: ScenarioDescriptor;
}

export type ScenarioTemplateParamValue = string | number | boolean;

export interface ScenarioTemplateParameterSchema {
  field: string;
  label: string;
  description?: string | null;
  type: 'number' | 'boolean' | 'text' | 'enum';
  parameter_type?: string | null;
  required: boolean;
  default?: ScenarioTemplateParamValue | null;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  unit?: string | null;
  options: string[];
}

export interface ScenarioLaunchCapabilities {
  map_editable: boolean;
  weather_editable: boolean;
  traffic_vehicle_count_editable: boolean;
  traffic_walker_count_editable: boolean;
  sensor_profile_editable: boolean;
  timeout_editable: boolean;
  max_vehicle_count: number;
  max_walker_count: number;
  notes: string[];
}

export interface EnvironmentPreset {
  preset_id: string;
  display_name: string;
  description: string;
  weather: WeatherConfig;
}

export interface SensorProfile {
  profile_name: string;
  display_name: string;
  description: string;
  vehicle_model?: string | null;
  sensors: SensorSpec[];
  raw_yaml: string;
  source_path: string;
  metadata: Record<string, unknown>;
}

export interface SensorProfileSavePayload {
  profile_name: string;
  display_name: string;
  description: string;
  vehicle_model?: string | null;
  sensors: SensorSpec[];
  metadata: Record<string, unknown>;
}

export interface MapOption {
  map_name: string;
  display_name: string;
  available_variants?: string[];
  preferred_variant?: 'optimized' | 'standard';
  family_key?: string;
}

export interface EvaluationProfile {
  profile_name: string;
  display_name: string;
  description: string;
  metrics: string[];
  iou_threshold: number;
  classes: string[];
}

export interface RunMetadata {
  author?: string;
  tags?: string[];
  description?: string;
  dut_model?: string | null;
}

export interface TrafficPayload {
  num_vehicles: number;
  num_walkers: number;
  seed?: number;
}

export interface ScenarioLaunchPayload {
  scenario_id: string;
  map_name?: string;
  weather?: WeatherConfig;
  traffic?: TrafficPayload;
  sensor_profile_name?: string;
  template_params?: Record<string, ScenarioTemplateParamValue>;
  timeout_seconds?: number;
  auto_start?: boolean;
  metadata?: RunMetadata;
}

export interface ProjectRecord {
  project_id: string;
  name: string;
  vendor: string;
  processor: string;
  description: string;
  benchmark_focus: string[];
  target_metrics: string[];
  input_modes: string[];
  status: 'ACTIVE' | 'PILOT' | 'ARCHIVED';
  created_at_utc: string | null;
  updated_at_utc: string | null;
}

export type BenchmarkPlanningMode =
  | 'single_scenario'
  | 'timed_single_scenario'
  | 'all_runnable'
  | 'custom_multi_scenario';

export type BenchmarkDefinition = Present<BenchmarkDefinitionSchema> & {
  planning_mode: BenchmarkPlanningMode;
};

export interface BenchmarkTaskScenarioMatrixEntry {
  scenario_id: string;
  scenario_name: string;
  scenario_display_name: string;
  execution_backend: 'native' | 'scenario_runner';
  requested_map_name: string;
  resolved_map_name: string;
  display_map_name: string;
  environment_preset_id: string;
  environment_name: string;
  sensor_profile_name: string;
  requested_timeout_seconds: number | null;
  resolved_timeout_seconds: number;
}

export interface BenchmarkTaskSummary {
  counts?: {
    total_runs?: number;
    created_runs?: number;
    queued_runs?: number;
    completed_runs?: number;
    failed_runs?: number;
    canceled_runs?: number;
    running_runs?: number;
  };
  metrics?: {
    fps?: number | null;
    latency_ms?: number | null;
    map?: number | null;
    power_w?: number | null;
    temperature_c?: number | null;
    frame_drop_rate?: number | null;
    pass_rate?: number | null;
    anomaly_rate?: number | null;
  };
  scenario_breakdown?: Record<
    string,
    { total_runs: number; completed: number; failed: number; canceled: number }
  >;
  gateway_snapshot?: Record<string, unknown>;
  execution_queue?: {
    active_run_id?: string | null;
    next_run_id?: string | null;
    completed_run_ids?: string[];
    failed_run_ids?: string[];
    canceled_run_ids?: string[];
    queued_run_ids?: string[];
    ordered_runs?: Array<{
      position: number;
      run_id: string;
      scenario_id: string | null;
      scenario_display_name: string;
      display_map_name: string;
      execution_backend: string;
      status: string;
      is_active: boolean;
      is_next: boolean;
      started_at_utc: string | null;
      ended_at_utc: string | null;
      error_reason: string | null;
    }>;
  };
}

export type BenchmarkTaskRecord = Omit<
  Present<BenchmarkTaskSchema>,
  'status' | 'planning_mode' | 'scenario_matrix' | 'summary'
> & {
  status: 'CREATED' | 'RUNNING' | 'COMPLETED' | 'PARTIAL_FAILED' | 'FAILED' | 'CANCELED';
  planning_mode: BenchmarkPlanningMode;
  scenario_matrix: BenchmarkTaskScenarioMatrixEntry[];
  summary: BenchmarkTaskSummary;
};

export type ReportRecord = Omit<Present<ReportSchema>, 'status' | 'summary'> & {
  status: 'READY' | 'FAILED';
  summary: BenchmarkTaskSummary;
};

export type ReportsWorkspace = Omit<
  Present<ReportsWorkspaceSchema>,
  'projects' | 'reports' | 'benchmark_tasks' | 'exportable_tasks' | 'pending_report_tasks' | 'recent_failures'
> & {
  projects: ProjectRecord[];
  reports: ReportRecord[];
  benchmark_tasks: BenchmarkTaskRecord[];
  exportable_tasks: BenchmarkTaskRecord[];
  pending_report_tasks: BenchmarkTaskRecord[];
  recent_failures: RunRecord[];
};

export type RunRecord = Omit<
  Present<RunRecordSchema>,
  | 'execution_backend'
  | 'metadata'
  | 'weather'
  | 'sensors'
  | 'recorder'
  | 'debug'
  | 'runtime_capabilities'
  | 'device_metrics'
> & {
  execution_backend: 'native' | 'scenario_runner';
  device_metrics: Record<string, unknown> | null;
  metadata: RunMetadata;
  weather: WeatherConfig;
  sensors: SensorsConfig;
  recorder: {
    enabled: boolean;
  };
  debug: {
    viewer_friendly?: boolean | null;
  };
  runtime_capabilities: {
    weather_update: boolean;
    viewer_friendly: boolean;
  };
};

export type RunEvent = Omit<Present<RunEventSchema>, 'payload'> & {
  payload: Record<string, unknown>;
};

export interface GatewayRecord {
  gateway_id: string;
  name: string;
  status: string;
  status_detail?: string | null;
  capabilities: Record<string, unknown>;
  metrics: Record<string, unknown>;
  agent_version: string | null;
  address: string | null;
  current_run_id: string | null;
  last_heartbeat_at_utc: string | null;
  last_seen_at_utc: string | null;
  created_at_utc: string | null;
  updated_at_utc: string | null;
}

export interface ProjectWorkspace {
  project: ProjectRecord;
  summary: {
    benchmark_definition_count: number;
    benchmark_task_count: number;
    recent_run_count: number;
    active_run_count: number;
    online_gateway_count: number;
    total_gateway_count: number;
  };
  benchmark_definitions: BenchmarkDefinition[];
  benchmark_tasks: BenchmarkTaskRecord[];
  recent_runs: RunRecord[];
  gateways: GatewayRecord[];
  scenario_presets: ScenarioCatalogItem[];
}

export interface DevicesWorkspace {
  summary: {
    online_device_count: number;
    running_capture_count: number;
    avg_input_fps: number | null;
    avg_output_fps: number | null;
    avg_frame_drop_rate: number | null;
    avg_power_w: number | null;
    avg_temperature_c: number | null;
  };
  gateways: GatewayRecord[];
  captures: CaptureRecord[];
  benchmark_tasks: BenchmarkTaskRecord[];
}

export interface DeviceWorkspace {
  gateway: GatewayRecord;
  summary: {
    capture_count: number;
    active_capture_count: number;
    linked_benchmark_task_count: number;
    input_fps: number | null;
    output_fps: number | null;
    latency_ms: number | null;
    frame_drop_rate: number | null;
    power_w: number | null;
    temperature_c: number | null;
  };
  captures: CaptureRecord[];
  benchmark_tasks: BenchmarkTaskRecord[];
}

export interface CaptureRecord {
  capture_id: string;
  gateway_id: string;
  source: string;
  save_format: string;
  sample_fps: number;
  max_frames: number | null;
  save_dir: string;
  manifest_path: string;
  note: string | null;
  status: string;
  saved_frames: number;
  created_at_utc: string | null;
  updated_at_utc: string | null;
  started_at_utc: string | null;
  ended_at_utc: string | null;
  error_reason: string | null;
}

export interface CaptureFrame {
  frame_index: number;
  captured_at_utc: string | null;
  relative_path: string;
  width: number | null;
  height: number | null;
  size_bytes: number | null;
}

export interface CaptureManifest {
  capture_id: string;
  gateway_id: string;
  source: string;
  save_format: string;
  sample_fps: number;
  max_frames: number | null;
  save_dir: string;
  status: string;
  note: string | null;
  saved_frames: number;
  created_at_utc: string | null;
  started_at_utc: string | null;
  ended_at_utc: string | null;
  error_reason: string | null;
  frames: CaptureFrame[];
}

export type HilConfigPayload = HilConfigPayloadSchema;

export type EvaluationProfilePayload = EvaluationProfilePayloadSchema;

export type CreateRunPayload = Omit<CreateRunPayloadSchema, 'descriptor'> & {
  descriptor?: ScenarioDescriptor;
};

export type CreateBenchmarkTaskPayload = CreateBenchmarkTaskPayloadSchema;

export type RunEnvironmentState = Omit<
  Present<RunEnvironmentStateSchema>,
  'descriptor_weather' | 'descriptor_debug' | 'runtime_control' | 'weather'
> & {
  descriptor_weather: WeatherConfig;
  descriptor_debug: {
    viewer_friendly?: boolean | null;
  };
  weather: WeatherConfig | null;
  runtime_control: Omit<
    Present<Exclude<RunEnvironmentStateSchema['runtime_control'], undefined>>,
    'weather' | 'debug' | 'sensor_capture' | 'recorder'
  > & {
    weather: WeatherConfig | null;
    debug: {
      viewer_friendly?: boolean | null;
    } | null;
    sensor_capture: SensorCaptureRuntimeControl | null;
    recorder: RecorderRuntimeControl | null;
  };
};

export type RunEnvironmentUpdatePayload = RunEnvironmentUpdatePayloadSchema;

export type RunViewerInfo = Omit<Present<RunViewerInfoSchema>, 'views'> & {
  views: Array<{
    view_id: string;
    label: string;
  }>;
};

export type CreateCapturePayload = CreateCapturePayloadSchema;

export type ReportExportPayload = ReportExportPayloadSchema;

export type RerunBenchmarkTaskPayload = RerunBenchmarkTaskPayloadSchema;
