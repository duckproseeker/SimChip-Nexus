import { apiRequest, postJson } from './client';
import type {
  Pipeline,
  PipelineEdgeDef,
  PipelineExecution,
  PipelineNodeDef,
  PipelineValidationResult,
  ProjectRecord,
  ScenarioCatalogItem,
  EnvironmentPreset,
  ScenarioRecording,
} from './types';

export function listPipelines(): Promise<Pipeline[]> {
  return apiRequest<Pipeline[]>('/pipelines');
}

export function createPipeline(name: string, description = ''): Promise<Pipeline> {
  return postJson<Pipeline>('/pipelines', { name, description });
}

export function getPipeline(pipelineId: string): Promise<Pipeline> {
  return apiRequest<Pipeline>(`/pipelines/${pipelineId}`);
}

export function updatePipeline(
  pipelineId: string,
  patch: {
    name?: string;
    description?: string;
    nodes?: PipelineNodeDef[];
    edges?: PipelineEdgeDef[];
  }
): Promise<Pipeline> {
  return postJson<Pipeline>(`/pipelines/${pipelineId}`, patch, 'PUT');
}

export function deletePipeline(pipelineId: string): Promise<void> {
  return apiRequest<void>(`/pipelines/${pipelineId}`, { method: 'DELETE' });
}

export function validatePipeline(pipelineId: string): Promise<PipelineValidationResult> {
  return postJson<PipelineValidationResult>(`/pipelines/${pipelineId}/validate`);
}

export interface ExecuteBody {
  mode?: 'offline_render' | 'online_play' | 'legacy';
  options?: Record<string, unknown>;
}

export function executePipeline(pipelineId: string, body?: ExecuteBody): Promise<PipelineExecution> {
  return postJson<PipelineExecution>(`/pipelines/${pipelineId}/execute`, body);
}

export function getPipelineExecution(executionId: string): Promise<PipelineExecution> {
  return apiRequest<PipelineExecution>(`/pipeline-executions/${executionId}`);
}

export function listPipelineExecutions(pipelineId: string): Promise<PipelineExecution[]> {
  return apiRequest<PipelineExecution[]>(`/pipelines/${pipelineId}/executions`);
}

export function stopPipelineExecution(executionId: string): Promise<void> {
  return postJson<void>(`/pipeline-executions/${executionId}/stop`);
}

export function fetchProjects(): Promise<ProjectRecord[]> {
  return apiRequest<ProjectRecord[]>('/projects');
}

export function fetchScenarioCatalog(): Promise<ScenarioCatalogItem[]> {
  return apiRequest<ScenarioCatalogItem[]>('/scenarios/catalog');
}

export function fetchEnvironmentPresets(): Promise<EnvironmentPreset[]> {
  return apiRequest<EnvironmentPreset[]>('/scenarios/environment-presets');
}

export function fetchRecordings(): Promise<ScenarioRecording[]> {
  return apiRequest<ScenarioRecording[]>('/scenario-recordings');
}
