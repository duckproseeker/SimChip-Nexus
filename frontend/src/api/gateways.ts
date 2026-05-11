import { apiRequest } from './client';
import type { GatewayRecord } from './types';

export function listGateways() {
  return apiRequest<{ gateways: GatewayRecord[] }>('/gateways').then((data) => data.gateways);
}

export function getGateway(gatewayId: string) {
  return apiRequest<GatewayRecord>(`/gateways/${gatewayId}`);
}
