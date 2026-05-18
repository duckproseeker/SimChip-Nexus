import { apiRequest, postJson } from './client';
import type {
  ScenarioSource,
  ScenarioSourceDetail,
  ScenarioSourceLaunchRecordingPayload,
  ScenarioSourceLaunchRecordingResult,
  ScenarioSourceList,
  ScenarioSourceMaterialization,
  ScenarioSourceRescanResult
} from './types';

export interface ScenarioSourceFilters {
  provider?: string;
  map_name?: string;
  scenario_type?: string;
  corner_case_label?: string;
  compatibility_status?: string;
}

export function listScenarioSources(filters: ScenarioSourceFilters = {}) {
  return apiRequest<ScenarioSourceList>('/scenario-sources', {
    query: {
      provider: filters.provider,
      map_name: filters.map_name,
      scenario_type: filters.scenario_type,
      corner_case_label: filters.corner_case_label,
      compatibility_status: filters.compatibility_status
    }
  });
}

export function getScenarioSource(sourceId: string) {
  return apiRequest<ScenarioSourceDetail>(`/scenario-sources/${sourceId}`);
}

export function rescanScenarioSources() {
  return postJson<ScenarioSourceRescanResult>('/scenario-sources/rescan', {});
}

export function listScenarioSourceMaterializations(sourceId: string) {
  return apiRequest<ScenarioSourceMaterialization[]>(
    `/scenario-sources/${sourceId}/materializations`
  );
}

export function launchScenarioSourceRecording(
  sourceId: string,
  payload: ScenarioSourceLaunchRecordingPayload
) {
  return postJson<ScenarioSourceLaunchRecordingResult>(
    `/scenario-sources/${sourceId}/launch-recording`,
    payload
  );
}

export type { ScenarioSource };
