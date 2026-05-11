import { apiRequest, postJson } from './client';
import type {
  BenchmarkDefinitionListSchema,
  BenchmarkTaskListSchema
} from './generated/contracts';
import type {
  BenchmarkDefinition,
  BenchmarkTaskRecord,
  CreateBenchmarkTaskPayload,
  RerunBenchmarkTaskPayload
} from './types';

export function listBenchmarkDefinitions() {
  return apiRequest<BenchmarkDefinitionListSchema>('/benchmark-definitions').then(
    (data) => (data.definitions ?? []) as BenchmarkDefinition[]
  );
}

export function listBenchmarkTasks(filters: { projectId?: string; status?: string } = {}) {
  return apiRequest<BenchmarkTaskListSchema>('/benchmark-tasks', {
    query: {
      project_id: filters.projectId,
      status: filters.status
    }
  }).then((data) => (data.tasks ?? []) as BenchmarkTaskRecord[]);
}

export function getBenchmarkTask(benchmarkTaskId: string) {
  return apiRequest<BenchmarkTaskRecord>(`/benchmark-tasks/${benchmarkTaskId}`);
}

export function createBenchmarkTask(payload: CreateBenchmarkTaskPayload) {
  return postJson<BenchmarkTaskRecord>('/benchmark-tasks', payload);
}

export function rerunBenchmarkTask(benchmarkTaskId: string, autoStart = true) {
  const payload: RerunBenchmarkTaskPayload = {
    auto_start: autoStart
  };
  return postJson<BenchmarkTaskRecord>(`/benchmark-tasks/${benchmarkTaskId}/rerun`, payload);
}

export function stopBenchmarkTask(benchmarkTaskId: string) {
  return postJson<BenchmarkTaskRecord>(`/benchmark-tasks/${benchmarkTaskId}/stop`);
}
