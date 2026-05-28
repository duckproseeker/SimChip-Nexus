import { apiRequest, postJson } from './client';

export interface ScenarioAsset {
  id: string;
  name: string;
  recorder_log_path: string;
  map_name: string;
  duration_seconds: number;
  tags: string[];
  description: string;
  file_size_bytes: number;
  created_at: string;
  metadata: Record<string, unknown>;
}

export async function listScenarioAssets(params?: {
  tag?: string;
  map_name?: string;
}): Promise<ScenarioAsset[]> {
  return apiRequest<ScenarioAsset[]>('/scenario-assets', {
    query: {
      tag: params?.tag,
      map_name: params?.map_name,
    },
  });
}

export async function getScenarioAsset(id: string): Promise<ScenarioAsset> {
  return apiRequest<ScenarioAsset>(`/scenario-assets/${id}`);
}

export async function createScenarioAsset(body: {
  name: string;
  recorder_log_path: string;
  map_name?: string;
  duration_seconds?: number;
  tags?: string[];
  description?: string;
}): Promise<ScenarioAsset> {
  return postJson<ScenarioAsset>('/scenario-assets', body);
}

export async function updateScenarioAsset(
  id: string,
  body: Partial<Pick<ScenarioAsset, 'name' | 'tags' | 'description' | 'map_name'>>
): Promise<ScenarioAsset> {
  return apiRequest<ScenarioAsset>(`/scenario-assets/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteScenarioAsset(id: string): Promise<void> {
  return apiRequest<void>(`/scenario-assets/${id}`, { method: 'DELETE' });
}
