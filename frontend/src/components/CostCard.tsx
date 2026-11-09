import type { CostMetrics } from '../types/api';

interface Props {
  cost: CostMetrics | null;
  busy: boolean;
  previousCost?: CostMetrics | null;
  previousLabel?: string | null;
}

function fmtRs(n: number): string {
  return `₹${Math.round(n).toLocaleString('en-IN')}`;
}

function fmtRsKwh(n: number): string {
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/kWh`;
}

interface RowProps { label: string; value: string; sub?: string; tone?: 'good' | 'bad' | 'neutral' }

function Row({ label, value, sub, tone }: RowProps) {
  const toneClass =
    tone === 'good' ? 'text-emerald-700' : tone === 'bad' ? 'text-red-700' : 'text-ink-soft';
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-sm">
      <dt className="text-ink-soft">{label}</dt>
      <dd className={`num text-right font-medium ${toneClass}`}>
        {value}
        {sub && <span className="ml-1.5 text-xs font-normal text-ink-mute">{sub}</span>}
      </dd>
    </div>
  );
}

export function CostCard({ cost, busy, previousCost, previousLabel }: Props) {
  const prevSavings = previousCost?.savings_rs ?? null;
  const delta = cost && prevSavings !== null ? cost.savings_rs - prevSavings : null;
  const significant = delta !== null && Math.abs(delta) >= 1;

  return (
    <section className="panel p-4" aria-label="Cost and tariff metrics">
      <h3 className="font-display text-base font-semibold">Cost &amp; tariff</h3>
      {cost ? (
        <>
          <dl className={`mt-2 divide-y divide-line transition-opacity ${busy ? 'opacity-40' : ''}`}>
            <Row
              label="Grid cost (actual)"
              value={fmtRs(cost.total_grid_cost_rs)}
              sub="24 h"
              tone="neutral"
            />
            <Row
              label="Baseline (grid-only)"
              value={fmtRs(cost.grid_only_cost_rs)}
              sub="24 h"
              tone="neutral"
            />
            <Row
              label="Savings vs baseline"
              value={`${fmtRs(cost.savings_rs)} (${cost.savings_percent.toFixed(1)}%)`}
              tone="good"
            />
            <Row
              label="Avg cost served"
              value={fmtRsKwh(cost.average_cost_rs_per_kwh_served)}
              tone="neutral"
            />
            <Row
              label="Grid-only avg tariff"
              value={fmtRsKwh(cost.grid_only_average_cost_rs_per_kwh)}
              tone="neutral"
            />
          </dl>
          <p className={`num mt-2 min-h-[1.25rem] text-xs ${significant ? (delta! > 0 ? 'text-emerald-700' : 'text-red-700') : 'text-ink-mute'}`}>
            {significant
              ? `Savings ${delta! > 0 ? '+' : ''}${fmtRs(delta!)} vs ${previousLabel ?? 'previous run'}`
              : delta !== null
                ? `Savings unchanged vs ${previousLabel ?? 'previous run'}`
                : 'Cost estimate based on assumed ToD tariff.'}
          </p>
        </>
      ) : (
        <p className="mt-2 text-sm text-ink-mute">
          {busy ? 'Calculating cost metrics…' : 'Run a simulation to see cost estimates.'}
        </p>
      )}
    </section>
  );
}
