import type { BenchmarkDefinition, GatewayRecord, ProjectRecord, RunMetadata, RunRecord } from '../api/types';

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export function metricNumber(source: Record<string, unknown> | null | undefined, keys: string[]) {
  if (!source) {
    return null;
  }

  for (const key of keys) {
    const exact = toNumber(source[key]);
    if (exact !== null) {
      return exact;
    }
  }

  for (const [key, value] of Object.entries(source)) {
    if (keys.some((candidate) => key.toLowerCase() === candidate.toLowerCase())) {
      const match = toNumber(value);
      if (match !== null) {
        return match;
      }
    }
  }

  return null;
}

export function average(values: Array<number | null | undefined>) {
  const valid = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (valid.length === 0) {
    return null;
  }
  return valid.reduce((sum, value) => sum + value, 0) / valid.length;
}

export function toggleSelection(values: string[], value: string) {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
}

export function getMetadataTagValue(metadata: RunMetadata | undefined, prefix: string) {
  const tag = metadata?.tags?.find((item) => item.startsWith(`${prefix}:`));
  return tag ? tag.slice(prefix.length + 1) : null;
}

export function getRunProjectId(run: RunRecord) {
  return run.project_id ?? getMetadataTagValue(run.metadata, 'project') ?? getMetadataTagValue(run.metadata, 'chip');
}

export function getRunChipId(run: RunRecord) {
  return getRunProjectId(run);
}

export function getRunBenchmarkId(run: RunRecord) {
  return run.benchmark_definition_id ?? getMetadataTagValue(run.metadata, 'benchmark');
}

export function getRunTaskId(run: RunRecord) {
  return run.benchmark_task_id ?? getMetadataTagValue(run.metadata, 'task');
}

export function getRunDutModel(run: RunRecord) {
  return run.dut_model ?? run.metadata?.dut_model ?? null;
}

export function findProjectRecord(projects: ProjectRecord[], projectId: string | null | undefined) {
  return projects.find((item) => item.project_id === projectId) ?? null;
}

export function findBenchmarkDefinition(
  definitions: BenchmarkDefinition[],
  benchmarkDefinitionId: string | null | undefined
) {
  return definitions.find((item) => item.benchmark_definition_id === benchmarkDefinitionId) ?? null;
}

export function deriveRunFps(run: RunRecord) {
  if (run.achieved_tick_rate_hz !== null && run.achieved_tick_rate_hz > 0) {
    return run.achieved_tick_rate_hz;
  }
  if (
    run.executed_tick_count !== null &&
    run.wall_elapsed_seconds !== null &&
    run.wall_elapsed_seconds > 0
  ) {
    return run.executed_tick_count / run.wall_elapsed_seconds;
  }
  return null;
}

export function deriveGatewayInputFps(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['input_fps', 'fps', 'camera_fps']);
}

export function deriveGatewayOutputFps(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['output_fps', 'inference_fps', 'render_fps']);
}

export function deriveGatewayLatencyMs(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['avg_latency_ms', 'latency_ms', 'p95_latency_ms']);
}

export function deriveGatewayMap(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['map50', 'mAP', 'map']);
}

export function deriveGatewayPowerW(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['power_w', 'soc_power_w', 'board_power_w', 'total_power_w']);
}

export function deriveGatewayTemperatureC(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['temperature_c', 'soc_temp_c', 'cpu_temp_c', 'board_temp_c']);
}

export function deriveGatewayFrameDropRate(gateway: GatewayRecord) {
  return metricNumber(gateway.metrics, ['frame_drop_rate', 'drop_rate']);
}

export function calculatePassRate(runs: RunRecord[]) {
  const terminal = runs.filter((run) => ['COMPLETED', 'FAILED', 'CANCELED'].includes(run.status));
  if (terminal.length === 0) {
    return null;
  }
  const passed = terminal.filter((run) => run.status === 'COMPLETED').length;
  return (passed / terminal.length) * 100;
}

export function calculateAnomalyRate(runs: RunRecord[]) {
  if (runs.length === 0) {
    return null;
  }
  const anomalyCount = runs.filter((run) => ['FAILED', 'CANCELED'].includes(run.status)).length;
  return (anomalyCount / runs.length) * 100;
}

export function deriveBenchmarkSummary(runs: RunRecord[], gateways: GatewayRecord[]) {
  const fps = average([...runs.map(deriveRunFps), ...gateways.map(deriveGatewayOutputFps), ...gateways.map(deriveGatewayInputFps)]);
  const latencyMs = average(gateways.map(deriveGatewayLatencyMs));
  const map = average(gateways.map(deriveGatewayMap));
  const powerW = average(gateways.map(deriveGatewayPowerW));
  const temperatureC = average(gateways.map(deriveGatewayTemperatureC));
  const frameDropRate = average(gateways.map(deriveGatewayFrameDropRate));
  const passRate = calculatePassRate(runs);
  const anomalyRate = calculateAnomalyRate(runs);

  return {
    fps,
    latencyMs,
    map,
    powerW,
    temperatureC,
    frameDropRate,
    passRate,
    anomalyRate
  };
}

export function formatMetric(value: number | null, digits = 1, suffix = '') {
  if (value === null) {
    return '待接入';
  }
  return `${value.toFixed(digits)}${suffix}`;
}
