import type { DispatchPoint, HealthResponse, Meta, SystemInfo } from '../types/api';
import { fmtKw, hourLabel } from '../utils/format';

interface Props { point: DispatchPoint | null; meta: Meta | null; health: HealthResponse | null; system: SystemInfo | null }

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between gap-3 py-1 text-sm"><dt className="text-ink-soft">{k}</dt><dd className="num font-medium">{v}</dd></div>;
}

export function SystemStatus({ point, meta, health, system }: Props) {
  const renewable = point ? point.solar_kw + point.wind_kw + point.hydro_kw : 0;
  const fallback = meta && (meta.forecast_source === 'mock' || meta.optimization_source === 'mock');
  return (
    <section className="panel p-4" aria-label="System status">
      <h3 className="font-display text-base font-semibold">System status{point && <span className="ml-2 text-sm font-normal text-ink-mute">{hourLabel(point.timestamp)}</span>}</h3>
      {point ? (
        <dl className="mt-2 divide-y divide-line">
          <Row k="Demand" v={fmtKw(point.load_kw)} />
          <Row k="Renewable generation" v={fmtKw(renewable)} />
          <Row k="Grid import" v={system ? `${fmtKw(point.grid_kw)} of ${fmtKw(system.grid_capacity_kw)}` : fmtKw(point.grid_kw)} />
          <Row k="Curtailed" v={fmtKw(point.curtailment_kw)} />
        </dl>
      ) : <p className="mt-2 text-sm text-ink-mute">No dispatch data yet.</p>}
      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        <span className="rounded-full bg-paper px-2 py-1">Forecast: {meta ? (meta.forecast_source === 'model' ? 'AI model' : 'mock') : '–'}</span>
        <span className="rounded-full bg-paper px-2 py-1">Optimizer: {meta?.optimization_source === 'pypsa' ? 'PyPSA + HiGHS' : meta?.optimization_source === 'mock' ? 'mock' : '–'}</span>
        <span className={`rounded-full px-2 py-1 ${health?.status === 'ok' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
          API: {health ? (health.status === 'ok' ? 'connected' : 'degraded') : 'unknown'}
        </span>
      </div>
      {fallback && meta && meta.warnings.length > 0 && (
        <ul className="mt-3 space-y-1 rounded-md bg-amber-50 p-2 text-xs text-amber-900">
          {meta.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
    </section>
  );
}
