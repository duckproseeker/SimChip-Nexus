import { apiRequest, postJson } from './client';
import type {
  ScenarioRecording,
  ScenarioRecordingDetail,
  ScenarioRecordingLaunchPayload,
  ScenarioRecordingLaunchResult,
  ScenarioRecordingList,
  ScenarioRecordingPublishPayload
} from './types';

export interface ScenarioRecordingFilters {
  map_name?: string;
  tag?: string;
  corner_case_label?: string;
  determinism_level?: string;
}

export function listScenarioRecordings(filters: ScenarioRecordingFilters = {}) {
  return apiRequest<ScenarioRecordingList>('/scenario-recordings', {
    query: {
      map_name: filters.map_name,
      tag: filters.tag,
      corner_case_label: filters.corner_case_label,
      determinism_level: filters.determinism_level
    }
  });
}

export function getScenarioRecording(recordingId: string) {
  return apiRequest<ScenarioRecordingDetail>(`/scenario-recordings/${recordingId}`);
}

export function publishScenarioRecordingFromRun(payload: ScenarioRecordingPublishPayload) {
  return postJson<ScenarioRecording>('/scenario-recordings/from-run', payload);
}

export function launchScenarioRecording(recordingId: string, payload: ScenarioRecordingLaunchPayload) {
  return postJson<ScenarioRecordingLaunchResult>(
    `/scenario-recordings/${recordingId}/launch`,
    payload
  );
}
