import { apiRequest, postJson } from './client';
import type {
  PiGatewayCommandResult,
  PiGatewayRuntimeStatus,
  SystemStatus,
  WeatherConfig
} from './types';

export function getSystemStatus() {
  return apiRequest<SystemStatus>('/system/status');
}

export function updateCarlaWeather(payload: WeatherConfig) {
  return postJson<{ message: string }>('/system/carla/weather', payload, 'PUT');
}

export function getPiGatewayStatus() {
  return apiRequest<PiGatewayRuntimeStatus>('/system/pi-gateway');
}

export function startPiGateway() {
  return postJson<PiGatewayCommandResult>('/system/pi-gateway/start');
}

export function stopPiGateway() {
  return postJson<PiGatewayCommandResult>('/system/pi-gateway/stop');
}
