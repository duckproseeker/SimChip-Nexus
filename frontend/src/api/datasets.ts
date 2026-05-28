import { apiRequest, postJson } from './client';

export interface SensorConfig {
  sensor_id: string;
  sensor_type: string;
  transform: Record<string, number>;
  attributes: Record<string, any>;
}

export interface Dataset {
  dataset_id: string;
  scenario_id: string;
  pipeline_id: string;
  name: string;
  status: 'PENDING' | 'RENDERING' | 'COMPLETED' | 'FAILED';
  sensor_configs: SensorConfig[];
  total_frames: number;
  rendered_frames: number;
  delta_seconds: number;
  duration_seconds: number;
  output_dir: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface GenerateRequest {
  scenario_id: string;
  name?: string;
  pipeline_id?: string;
  sensor_configs: SensorConfig[];
  delta_seconds?: number;
  duration?: number;
  start_time?: number;
}

export const datasetsApi = {
  list: (scenarioId?: string) =>
    apiRequest<Dataset[]>('/datasets', {
      query: scenarioId ? { scenario_id: scenarioId } : {},
    }),

  get: (id: string) => apiRequest<Dataset>(`/datasets/${id}`),

  generate: (req: GenerateRequest) =>
    postJson<{ dataset_id: string; status: string }>('/datasets/generate', req),

  delete: (id: string) => apiRequest<void>(`/datasets/${id}`, { method: 'DELETE' }),
};
