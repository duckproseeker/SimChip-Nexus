import { apiRequest, postJson } from './client';
import type { RunCreateResponseSchema } from './generated/contracts';
import type {
  CreateRunPayload,
  RunEnvironmentState,
  RunEnvironmentUpdatePayload,
  RunEvent,
  RunRecord,
  RunViewerInfo
} from './types';

export function listRuns(status?: string) {
  return apiRequest<RunRecord[]>('/runs', {
    query: { status }
  });
}

export function getRun(runId: string) {
  return apiRequest<RunRecord>(`/runs/${runId}`);
}

export function getRunEvents(runId: string) {
  return apiRequest<RunEvent[]>(`/runs/${runId}/events`);
}

export function createRun(payload: CreateRunPayload) {
  return postJson<RunCreateResponseSchema>('/runs', payload);
}

export function startRun(runId: string) {
  return postJson<RunRecord>(`/runs/${runId}/start`);
}

export function stopRun(runId: string) {
  return postJson<RunRecord>(`/runs/${runId}/stop`);
}

export function cancelRun(runId: string) {
  return postJson<RunRecord>(`/runs/${runId}/cancel`);
}

export function getRunEnvironment(runId: string) {
  return apiRequest<RunEnvironmentState>(`/runs/${runId}/environment`);
}

export function updateRunEnvironment(runId: string, payload: RunEnvironmentUpdatePayload) {
  return postJson<RunEnvironmentState>(`/runs/${runId}/environment`, payload);
}

export function startRunSensorCapture(runId: string) {
  return postJson<RunEnvironmentState>(`/runs/${runId}/sensor-capture/start`);
}

export function stopRunSensorCapture(runId: string) {
  return postJson<RunEnvironmentState>(`/runs/${runId}/sensor-capture/stop`);
}

export function getRunViewer(runId: string) {
  return apiRequest<RunViewerInfo>(`/runs/${runId}/viewer`);
}
