import type {
  AssetsResponse, ForecastResponse, HealthResponse, OptimizeResponse, ScenarioId, ScenarioInfo,
  ScenarioSummaryResponse,
} from '../types/api';

const BASE: string = import.meta.env.VITE_API_BASE ?? '';

export type ApiErrorKind = 'unavailable' | 'validation' | 'pipeline' | 'unknown';

export class ApiError extends Error {
  constructor(message: string, public readonly kind: ApiErrorKind, public readonly status: number | null) {
    super(message);
    this.name = 'ApiError';
  }
}

interface ErrorBody { detail?: unknown }

function detailText(body: ErrorBody | null, fallback: string): string {
  if (body && typeof body.detail === 'string') return body.detail;
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      'Cannot reach the GridMate API. Check that the backend is running on port 8000.',
      'unavailable',
      null,
    );
  }
  if (!res.ok) {
    let body: ErrorBody | null = null;
    try { body = (await res.json()) as ErrorBody; } catch { /* non-JSON error body */ }
    if (res.status === 422) throw new ApiError('Invalid scenario selected.', 'validation', 422);
    if (res.status === 503) throw new ApiError(detailText(body, 'The simulation pipeline failed.'), 'pipeline', 503);
    if (res.status >= 500 || res.status === 502 || res.status === 504) {
      throw new ApiError('The GridMate API is unavailable. Check that the backend is running.', 'unavailable', res.status);
    }
    throw new ApiError(detailText(body, `Request failed (${res.status}).`), 'unknown', res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  scenarios: () => request<ScenarioInfo[]>('/api/scenarios'),
  scenariosSummary: () => request<ScenarioSummaryResponse>('/api/scenarios/summary'),
  assets: () => request<AssetsResponse>('/api/assets'),
  setScenario: (scenario: ScenarioId, date?: string | null) =>
    request<ForecastResponse>('/api/scenario', {
      method: 'POST',
      body: JSON.stringify({ scenario, date: date || null }),
    }),
  optimize: (scenario: ScenarioId, date?: string | null) =>
    request<OptimizeResponse>('/api/optimize', {
      method: 'POST',
      body: JSON.stringify({ scenario, date: date || null }),
    }),
  forecastByDate: (date: string, scenario?: ScenarioId) => {
    const sc = scenario ? `&scenario=${scenario}` : '';
    return request<ForecastResponse>(`/api/forecast?date=${date}${sc}`);
  },
};
