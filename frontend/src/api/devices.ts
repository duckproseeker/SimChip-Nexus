import { apiRequest } from './client';
import type { DevicesWorkspace, DeviceWorkspace } from './types';

export function getDevicesWorkspace() {
  return apiRequest<DevicesWorkspace>('/devices/workspace');
}

export function getDeviceWorkspace(gatewayId: string) {
  return apiRequest<DeviceWorkspace>(`/devices/${gatewayId}/workspace`);
}
