import { apiRequest, postJson } from './client';
import type {
  CaptureFrame,
  CaptureManifest,
  CaptureRecord,
  CreateCapturePayload
} from './types';

export function listCaptures(filters: { status?: string; gatewayId?: string } = {}) {
  return apiRequest<{ captures: CaptureRecord[] }>('/captures', {
    query: {
      status: filters.status,
      gateway_id: filters.gatewayId
    }
  }).then((data) => data.captures);
}

export function getCapture(captureId: string) {
  return apiRequest<CaptureRecord>(`/captures/${captureId}`);
}

export function getCaptureFrames(captureId: string, offset = 0, limit = 50) {
  return apiRequest<CaptureFrame[]>(`/captures/${captureId}/frames`, {
    query: { offset, limit }
  });
}

export function getCaptureManifest(captureId: string) {
  return apiRequest<CaptureManifest>(`/captures/${captureId}/manifest`);
}

export function createCapture(payload: CreateCapturePayload) {
  return postJson<CaptureRecord>('/captures', payload);
}

export function startCapture(captureId: string) {
  return postJson<CaptureRecord>(`/captures/${captureId}/start`);
}

export function stopCapture(captureId: string) {
  return postJson<CaptureRecord>(`/captures/${captureId}/stop`);
}
