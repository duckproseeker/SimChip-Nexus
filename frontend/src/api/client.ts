import type { ApiEnvelope } from './types';

export class ApiClientError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 500, code = 'API_ERROR') {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions extends RequestInit {
  query?: Record<string, string | number | boolean | null | undefined>;
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '';

function buildUrl(path: string, query?: RequestOptions['query']) {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    params.set(key, String(value));
  });

  const suffix = params.toString() ? `?${params.toString()}` : '';
  return `${apiBaseUrl}${path}${suffix}`;
}

function isEnvelope<T>(value: unknown): value is ApiEnvelope<T> {
  if (!value || typeof value !== 'object') {
    return false;
  }
  return 'success' in value && 'data' in value;
}

async function parseResponseBody(response: Response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(buildUrl(path, options.query), {
    ...options,
    headers
  });

  const body = await parseResponseBody(response);

  if (!response.ok) {
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? (body as { detail?: { code?: string; message?: string } }).detail
        : null;
    throw new ApiClientError(
      detail?.message ?? `Request failed with status ${response.status}`,
      response.status,
      detail?.code ?? 'HTTP_ERROR'
    );
  }

  if (isEnvelope<T>(body)) {
    if (!body.success) {
      throw new ApiClientError(
        body.error?.message ?? 'Unknown API error',
        response.status,
        body.error?.code ?? 'API_ERROR'
      );
    }
    return body.data;
  }

  return body as T;
}

export function postJson<T>(path: string, body?: unknown, method: 'POST' | 'PUT' = 'POST') {
  return apiRequest<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}
