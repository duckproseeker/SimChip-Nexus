import { apiRequest, postJson } from './client';
import type { SensorProfile, SensorProfileCopyPayload, SensorProfileSavePayload } from './types';

export function listSensorProfiles() {
  return apiRequest<{ items: SensorProfile[] }>('/sensor-profiles').then((data) => data.items);
}

export function getSensorProfile(sensorProfileId: string) {
  return apiRequest<SensorProfile>(`/sensor-profiles/${sensorProfileId}`);
}

export function createSensorProfile(payload: SensorProfileSavePayload) {
  return postJson<SensorProfile>('/sensor-profiles', payload);
}

export function updateSensorProfile(sensorProfileId: string, payload: SensorProfileSavePayload) {
  return postJson<SensorProfile>(`/sensor-profiles/${sensorProfileId}`, payload, 'PUT');
}

export function copySensorProfile(sensorProfileId: string, payload: SensorProfileCopyPayload) {
  return postJson<SensorProfile>(`/sensor-profiles/${sensorProfileId}/copy`, payload);
}
