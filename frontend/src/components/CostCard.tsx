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

function fmtRsKwh(n: number, digits = 2): string {
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })}/kWh`;
}

interface RowProps { label: string; value: string; sub?: string; tone?: 'good' | 'bad' | 'neutral' }

function Row({ label, value, sub, tone }: RowProps) {
  const toneClass =
    tone === 'good' ? 'text-emerald-700' : tone === 'bad' ? 'text-red-700' : 'text-ink-soft';
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-sm">
      <dt className="shrink-0 text-ink-soft">{label}</dt>
      <dd className={`num text-right font-medium ${toneClass}`}>
        {value}
        {sub && <span className="ml-1.5 text-xs font-normal text-ink-mute">{sub}</span>}
      </dd>
    </div>
  );
}

interface TodSlotProps { label: string; hours: string; rate: number; highlight?: boolean }

function TodSlot({ label, hours, rate, highlight }: TodSlotProps) {
  return (
    <div className={`flex flex-col rounded-md px-2 py-1.5 text-center ${highlight ? 'bg-amber-50 ring-1 ring-amber-200' : 'bg-paper'}`}>
      <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-mute">{label}</span>
      <span className="num mt-0.5 text-xs font-medium text-ink">{hours}</span>
      <span className={`num mt-0.5 text-sm font-semibold ${highlight ? 'text-amber-800' : 'text-ink-soft'}`}>
        {fmtRsKwh(rate)}
      </span>
    </div>
  );
}

export function CostCard({ cost, busy, previousCost, previousLabel }: Props) {
  const prevSavings = previousCost?.savings_rs ?? null;
  const delta = cost && prevSavings !== null ? cost.savings_rs - prevSavings : null;
  const significant = delta !== null && Math.abs(delta) >= 1;

  // Derive ToD slot rates from the base tariff.
  // Base = grid_only_average_cost_rs_per_kwh (₹8.00/kWh from system_config.json)
  // Slots: normal 00–09 × 1.00 | solar 09–17 × 0.75–0.85 | peak 17–24 × 1.20
  // We use the mid-season multiplier (0.80) for the solar slot display since the
  // actual value varies by season; the disclaimer note clarifies this.
  const base = cost?.grid_only_average_cost_rs_per_kwh ?? null;
  const todSlots = base
    ? [
        { label: 'Normal', hours: '00:00–09:00', rate: base * 1.00, highlight: false },
        { label: 'Solar', hours: '09:00–17:00', rate: base * 0.80, highlight: false },
        { label: 'Peak', hours: '17:00–24:00', rate: base * 1.20, highlight: true },
      ]
    : null;

  return (
    <section className="panel p-4" aria-label="Cost and tariff metrics">
      <h3 className="font-display text-base font-semibold">Cost &amp; tariff</h3>

      {cost ? (
        <div className={`transition-opacity ${busy ? 'opacity-40' : ''}`}>
          {/* ---- ToD tariff breakdown ---- */}
          {todSlots && (
            <div className="mt-3">
              <p className="mb-1.5 text-xs font-medium text-ink-mute uppercase tracking-wide">ToD tariff slots</p>
              <div className="grid grid-cols-3 gap-1.5">
                {todSlots.map((s) => (
                  <TodSlot key={s.label} {...s} />
                ))}
              </div>
              <p className="mt-1 text-[10px] text-ink-mute">
                Solar slot: ×0.75 Oct–Mar, ×0.85 Apr–Sep. Display shows mid-season avg.
              </p>
            </div>
          )}

          {/* ---- Cost summary rows ---- */}
          <dl className="mt-3 divide-y divide-line">
            <Row
              label="Actual grid cost"
              value={fmtRs(cost.total_grid_cost_rs)}
              sub="24 h"
              tone="neutral"
            />
            <Row
              label="Grid-only baseline"
              value={fmtRs(cost.grid_only_cost_rs)}
              sub="24 h"
              tone="neutral"
            />
            <Row
              label="Savings"
              value={`${fmtRs(cost.savings_rs)} (${cost.savings_percent.toFixed(1)}%)`}
              tone="good"
            />
            <Row
              label="Avg served cost"
              value={fmtRsKwh(cost.average_cost_rs_per_kwh_served)}
              tone="neutral"
            />
          </dl>

          {/* ---- Delta hint ---- */}
          <p className={`num mt-2 min-h-[1.25rem] text-xs ${significant ? (delta! > 0 ? 'text-emerald-700' : 'text-red-700') : 'text-ink-mute'}`}>
            {significant
              ? `Savings ${delta! > 0 ? '+' : ''}${fmtRs(delta!)} vs ${previousLabel ?? 'previous run'}`
              : delta !== null
                ? `Savings unchanged vs ${previousLabel ?? 'previous run'}`
                : 'Cost estimate based on assumed MERC/MSEDCL ToD tariff.'}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-sm text-ink-mute">
          {busy ? 'Calculating cost metrics…' : 'Run a simulation to see cost estimates.'}
        </p>
      )}
    </section>
  );
}
