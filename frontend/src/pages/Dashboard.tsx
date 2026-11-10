import { BatteryStatus } from '../components/BatteryStatus';
import { CompareScenarios } from '../components/CompareScenarios';
import { CostCard } from '../components/CostCard';
import { DemandChart } from '../components/DemandChart';
import { DispatchChart } from '../components/DispatchChart';
import { EnergyMix } from '../components/EnergyMix';
import { GenerationChart } from '../components/GenerationChart';
import { Header } from '../components/Header';
import { HourlyPowerCards } from '../components/HourlyPowerCards';
import { MapPanel } from '../components/MapPanel';
import { MetricCard } from '../components/MetricCard';
import { Notice } from '../components/Notice';
import { ResourcesAndSuggestions } from '../components/ResourcesAndSuggestions';
import { ScenarioComparisonModal } from '../components/ScenarioComparisonModal';
import { ScenarioSelector } from '../components/ScenarioSelector';
import { SystemStatus } from '../components/SystemStatus';
import { useSimulation } from '../hooks/useSimulation';
import type { CostMetrics } from '../types/api';

export function Dashboard() {
  const {
    state,
    select,
    selectAndRun,
    setDate,
    setHour,
    runSelected,
    retry,
    dismissError,
    openComparison,
    closeComparison,
    fetchComparison,
  } = useSimulation();
  const { phase, forecast, dispatch, metrics, assets, scenarios, active, previousMetrics, previousScenario, previousCost } = state;
  const busy = phase !== 'idle';
  const rows = dispatch?.dispatch ?? null;
  const hour = rows ? Math.min(state.hour, rows.length - 1) : 0;
  const point = rows ? rows[hour] ?? null : null;
  const prevHourIndex = rows && rows.length > 0 ? (hour - 1 + rows.length) % rows.length : null;
  const previousPoint = rows && prevHourIndex !== null ? rows[prevHourIndex] : null;
  const label = (id: typeof active) => scenarios.find((s) => s.id === id)?.label ?? null;
  const m = metrics?.metrics ?? null;
  const prev = previousMetrics;
  const prevLabel = label(previousScenario);
  const common = { busy, previousLabel: prevLabel };

  // Cast cost field to typed interface (backend sends a plain record)
  const cost = metrics?.cost as CostMetrics | null ?? null;

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-[1400px] space-y-4 px-4 py-4 sm:px-6">
        <ScenarioSelector
          scenarios={scenarios}
          selected={state.selected}
          active={active}
          phase={phase}
          selectedDate={state.selectedDate}
          dateNote={forecast?.note || forecast?.meta?.note}
          onSelect={select}
          onDateChange={setDate}
          onRun={() => void runSelected()}
          onCompare={() => void openComparison()}
        />

        {state.error && <Notice error={state.error} onRetry={() => void retry()} onDismiss={dismissError} />}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <MapPanel assets={assets} error={state.assetsError} dispatch={rows} hour={hour} onHour={setHour}
            busy={busy} scenarioLabel={label(active)} />
          <div className="space-y-4">
            <SystemStatus point={point} meta={dispatch?.meta ?? null} health={state.health} system={metrics?.system ?? null} />
            <BatteryStatus point={point} system={metrics?.system ?? null} />
            <CostCard cost={cost} busy={busy} previousCost={previousCost} previousLabel={prevLabel} />
          </div>
        </div>

        <HourlyPowerCards
          point={point}
          previousPoint={previousPoint}
          hour={hour}
          selectedDate={state.selectedDate}
          busy={busy}
        />

        <section aria-label="Key metrics">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="font-display text-lg font-semibold">Key metrics for {label(active) ?? 'the selected scenario'}</h2>
            <span className="text-xs text-ink-mute">Simulation result, 24-hour totals</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <MetricCard metric="renewable_penetration_percent" label="Renewable penetration" unit="%" value={m?.renewable_penetration_percent ?? null}
              previous={prev?.renewable_penetration_percent} hint="Share of demand met by renewables" {...common} />
            <MetricCard metric="grid_dependency_percent" label="Grid dependency" unit="%" value={m?.grid_dependency_percent ?? null}
              previous={prev?.grid_dependency_percent} hint="Share of demand imported from the grid" {...common} />
            <MetricCard metric="curtailment_percent" label="Curtailment" unit="%" value={m?.curtailment_percent ?? null}
              previous={prev?.curtailment_percent} hint="Renewable energy that could not be used or stored" {...common} />
            <MetricCard metric="battery_utilization_percent" label="Battery utilization" unit="%" value={m?.battery_utilization_percent ?? null}
              previous={prev?.battery_utilization_percent} hint="Battery throughput relative to capacity" {...common} />
            <MetricCard metric="estimated_co2_avoided_kg" label="CO₂ avoided" unit="kg" estimate value={m?.estimated_co2_avoided_kg ?? null}
              previous={prev?.estimated_co2_avoided_kg} hint="Estimated from an assumed grid emission factor" {...common} />
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          <GenerationChart forecast={forecast?.forecast ?? null} busy={busy} />
          <DemandChart forecast={forecast?.forecast ?? null} busy={busy} />
        </div>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <DispatchChart dispatch={rows} busy={busy} hour={hour} />
          <EnergyMix dispatch={rows} busy={busy} />
        </div>

        <ResourcesAndSuggestions
          suggestions={state.suggestions}
          busy={busy}
        />

        <CompareScenarios
          rows={state.comparisonRows}
          loading={state.comparisonLoading}
          error={state.comparisonError}
          activeScenario={active}
          onSelectScenario={selectAndRun}
          onRefresh={() => void fetchComparison()}
        />

        <footer className="pb-6 pt-2 text-xs text-ink-mute">
          GridMate prototype. Forecasts, capacities and demand are synthetic and illustrative, not measured Lonavala data.
          Water, road and power-line geometry from OpenStreetMap contributors.
        </footer>
      </main>

      {state.comparisonOpen && (
        <ScenarioComparisonModal
          rows={state.comparisonRows}
          loading={state.comparisonLoading}
          error={state.comparisonError}
          activeScenario={active}
          onClose={closeComparison}
        />
      )}
    </div>
  );
}
