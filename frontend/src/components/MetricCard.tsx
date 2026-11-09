import type { MetricKey } from '../utils/format';
import { METRIC_DIRECTION, fmt } from '../utils/format';

interface Props {
  metric: MetricKey;
  label: string;
  value: number | null;
  unit: string;
  hint: string;
  previous?: number | null;
  previousLabel?: string | null;
  estimate?: boolean;
  busy?: boolean;
}

export function MetricCard({ metric, label, value, unit, hint, previous, previousLabel, estimate, busy }: Props) {
  const delta = value !== null && previous != null ? value - previous : null;
  const good = METRIC_DIRECTION[metric];
  const significant = delta !== null && Math.abs(delta) >= 0.05;
  const tone =
    !significant || good === null
      ? 'text-ink-mute'
      : (delta as number) > 0 === good
        ? 'text-emerald-700'
        : 'text-red-700';
  return (
    <div className="panel p-4" title={hint}>
      <p className="text-sm text-ink-soft">{label}{estimate && <span className="text-ink-mute"> (estimate)</span>}</p>
      <p className={`num mt-1 font-display text-4xl font-semibold leading-none transition-opacity ${busy ? 'opacity-40' : ''}`}>
        {value === null ? '–' : metric === 'estimated_co2_avoided_kg' ? Math.round(value).toLocaleString('en-IN') : fmt(value)}
        <span className="ml-1 text-base font-medium text-ink-mute">{unit}</span>
      </p>
      <p className={`num mt-2 min-h-[1.25rem] text-xs ${tone}`}>
        {significant
          ? `${(delta as number) > 0 ? '+' : ''}${fmt(delta as number, metric === 'estimated_co2_avoided_kg' ? 0 : 1)} vs ${previousLabel ?? 'previous run'}`
          : delta !== null ? `No change vs ${previousLabel ?? 'previous run'}` : hint}
      </p>
    </div>
  );
}
