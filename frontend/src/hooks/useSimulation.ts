import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from '../services/api';
import type {
  AssetsResponse, CostMetrics, DispatchResponse, ForecastResponse, HealthResponse, Metrics, MetricsResponse,
  ScenarioId, ScenarioInfo, ScenarioSummaryRow,
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
  selectedDate: string;
  forecast: ForecastResponse | null;
  dispatch: DispatchResponse | null;
  metrics: MetricsResponse | null;
  previousMetrics: Metrics | null;
  previousScenario: ScenarioId | null;
  previousCost: CostMetrics | null;
  assets: AssetsResponse | null;
  assetsError: string | null;
  health: HealthResponse | null;
  error: UiError | null;
  hour: number;
  // scenario comparison
  comparisonOpen: boolean;
  comparisonRows: ScenarioSummaryRow[] | null;
  comparisonLoading: boolean;
  comparisonError: string | null;
}

const FALLBACK_SCENARIOS: ScenarioInfo[] = [
  { id: 'normal', label: 'Normal Day', description: 'Typical weather and demand.' },
  { id: 'cloudy', label: 'Cloudy Day', description: 'Heavy cloud cover reduces solar output.' },
  { id: 'heavy_monsoon', label: 'Heavy Monsoon', description: 'Low solar, stronger hydro flow.' },
  { id: 'high_wind', label: 'High Wind', description: 'Strong ridge winds.' },
  { id: 'peak_demand', label: 'Peak Demand', description: 'Evening demand surge.' },
];

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const getTodayStr = () => new Date().toISOString().split('T')[0];

function toUiError(e: unknown): UiError {
  if (e instanceof ApiError) return { kind: e.kind, message: e.message };
  return { kind: 'unknown', message: e instanceof Error ? e.message : 'Unexpected error.' };
}

export function useSimulation() {
  const [state, setState] = useState<SimulationState>({
    phase: 'forecasting', scenarios: FALLBACK_SCENARIOS, selected: 'normal', active: null,
    selectedDate: getTodayStr(),
    forecast: null, dispatch: null, metrics: null, previousMetrics: null, previousScenario: null,
    previousCost: null,
    assets: null, assetsError: null, health: null, error: null, hour: 12,
    comparisonOpen: false, comparisonRows: null, comparisonLoading: false, comparisonError: null,
  });
  const running = useRef(false);

  const patch = useCallback((p: Partial<SimulationState>) => setState((s) => ({ ...s, ...p })), []);

  const run = useCallback(async (scenario: ScenarioId, dateParam?: string | null) => {
    if (running.current) return;
    running.current = true;
    patch({ error: null, phase: 'forecasting' });
    try {
      const targetDate = dateParam !== undefined ? (dateParam || null) : (state.selectedDate || null);
      // Step 1: select scenario & date -> the forecast updates first.
      const forecast = await api.setScenario(scenario, targetDate);
      if (!forecast.forecast.length) throw new ApiError('The forecast came back empty.', 'pipeline', null);
      setState((s) => ({ ...s, forecast, phase: 'optimizing' }));
      // Step 2: optimization -> dispatch + metrics.
      const result = await api.optimize(scenario, targetDate);
      if (!result.dispatch.dispatch.length) throw new ApiError('The optimizer returned no dispatch.', 'pipeline', null);
      // Step 3: update digital twin and charts.
      setState((s) => ({ ...s, phase: 'updating' }));
      await sleep(450);
      setState((s) => ({
        ...s,
        phase: 'idle',
        active: scenario,
        selectedDate: targetDate || s.selectedDate,
        forecast: result.forecast,
        dispatch: result.dispatch,
        previousMetrics: s.metrics ? s.metrics.metrics : null,
        previousScenario: s.metrics ? s.active : null,
        previousCost: s.metrics?.cost as CostMetrics | null ?? null,
        metrics: result.metrics,
      }));
    } catch (e) {
      patch({ phase: 'idle', error: toUiError(e) });
    } finally {
      running.current = false;
    }
  }, [patch, state.selectedDate]);

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

  const openComparison = useCallback(async () => {
    patch({ comparisonOpen: true, comparisonLoading: true, comparisonError: null });
    try {
      const data = await api.scenariosSummary(state.selectedDate);
      patch({ comparisonRows: data.rows, comparisonLoading: false });
    } catch (e) {
      patch({ comparisonLoading: false, comparisonError: toUiError(e).message });
    }
  }, [patch, state.selectedDate]);

  return {
    state,
    select: (selected: ScenarioId) => patch({ selected }),
    setDate: (selectedDate: string) => {
      patch({ selectedDate });
      void run(state.selected, selectedDate);
    },
    setHour: (hour: number) => patch({ hour }),
    runSelected: () => run(state.selected, state.selectedDate),
    retry: () => run(state.selected, state.selectedDate),
    dismissError: () => patch({ error: null }),
    openComparison,
    closeComparison: () => patch({ comparisonOpen: false }),
  };
}
