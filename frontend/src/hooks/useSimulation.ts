import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../services/api';
import type {
  AssetsResponse, DispatchResponse, ForecastResponse, HealthResponse, Metrics, MetricsResponse,
  ScenarioId, ScenarioInfo,
} from '../types/api';

export type Phase = 'idle' | 'forecasting' | 'optimizing' | 'updating';

export interface UiError {
  kind: 'unavailable' | 'validation' | 'pipeline' | 'unknown';
  message: string;
}

export interface SimulationState {
  phase: Phase;
  scenarios: ScenarioInfo[];
  selected: ScenarioId;
  active: ScenarioId | null;
  forecast: ForecastResponse | null;
  dispatch: DispatchResponse | null;
  metrics: MetricsResponse | null;
  previousMetrics: Metrics | null;
  previousScenario: ScenarioId | null;
  assets: AssetsResponse | null;
  assetsError: string | null;
  health: HealthResponse | null;
  error: UiError | null;
  hour: number;
}

const FALLBACK_SCENARIOS: ScenarioInfo[] = [
  { id: 'normal', label: 'Normal Day', description: 'Typical weather and demand.' },
  { id: 'cloudy', label: 'Cloudy Day', description: 'Heavy cloud cover reduces solar output.' },
  { id: 'heavy_monsoon', label: 'Heavy Monsoon', description: 'Low solar, stronger hydro flow.' },
  { id: 'high_wind', label: 'High Wind', description: 'Strong ridge winds.' },
  { id: 'peak_demand', label: 'Peak Demand', description: 'Evening demand surge.' },
];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

function toUiError(e: unknown): UiError {
  if (e instanceof ApiError) return { kind: e.kind, message: e.message };
  return { kind: 'unknown', message: e instanceof Error ? e.message : 'Unexpected error.' };
}

export function useSimulation() {
  const [state, setState] = useState<SimulationState>({
    phase: 'forecasting', scenarios: FALLBACK_SCENARIOS, selected: 'normal', active: null,
    forecast: null, dispatch: null, metrics: null, previousMetrics: null, previousScenario: null,
    assets: null, assetsError: null, health: null, error: null, hour: 12,
  });
  const running = useRef(false);

  const patch = useCallback((p: Partial<SimulationState>) => setState((s) => ({ ...s, ...p })), []);

  const run = useCallback(async (scenario: ScenarioId) => {
    if (running.current) return;
    running.current = true;
    patch({ error: null, phase: 'forecasting' });
    try {
      // Step 1: select scenario -> the forecast updates first.
      const forecast = await api.setScenario(scenario);
      if (!forecast.forecast.length) throw new ApiError('The forecast came back empty.', 'pipeline', null);
      setState((s) => ({ ...s, forecast, phase: 'optimizing' }));
      // Step 2: optimization -> dispatch + metrics.
      const result = await api.optimize(scenario);
      if (!result.dispatch.dispatch.length) throw new ApiError('The optimizer returned no dispatch.', 'pipeline', null);
      // Step 3: update digital twin and charts.
      setState((s) => ({ ...s, phase: 'updating' }));
      await sleep(450);
      setState((s) => ({
        ...s,
        phase: 'idle',
        active: scenario,
        forecast: result.forecast,
        dispatch: result.dispatch,
        previousMetrics: s.metrics ? s.metrics.metrics : null,
        previousScenario: s.metrics ? s.active : null,
        metrics: result.metrics,
      }));
    } catch (e) {
      patch({ phase: 'idle', error: toUiError(e) });
    } finally {
      running.current = false;
    }
  }, [patch]);

  // Initial load: scenarios, health, assets, then the default "normal" run.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [sc, hl, as] = await Promise.allSettled([api.scenarios(), api.health(), api.assets()]);
      if (cancelled) return;
      setState((s) => ({
        ...s,
        scenarios: sc.status === 'fulfilled' ? sc.value : s.scenarios,
        health: hl.status === 'fulfilled' ? hl.value : null,
        assets: as.status === 'fulfilled' ? as.value : null,
        assetsError: as.status === 'rejected' ? toUiError(as.reason).message : null,
      }));
      await run('normal');
    })();
    return () => { cancelled = true; };
  }, [run]);

  return {
    state,
    select: (selected: ScenarioId) => patch({ selected }),
    setHour: (hour: number) => patch({ hour }),
    runSelected: () => run(state.selected),
    retry: () => run(state.selected),
    dismissError: () => patch({ error: null }),
  };
}
