import type { DispatchPoint, SystemInfo } from '../types/api';
import { fmt, fmtKw } from '../utils/format';

interface Props { point: DispatchPoint | null; system: SystemInfo | null }

export function BatteryStatus({ point, system }: Props) {
  if (!point || !system) return <section className="panel p-4"><h3 className="font-display text-base font-semibold">Battery</h3><p className="mt-2 text-sm text-ink-mute">No battery data yet.</p></section>;
  const cap = system.battery_capacity_kwh;
  const pct = Math.max(0, Math.min(100, (point.battery_soc_kwh / cap) * 100));
  const minPct = (system.battery_min_soc_kwh / cap) * 100;
  const state = point.battery_kw > 0.05 ? 'Discharging' : point.battery_kw < -0.05 ? 'Charging' : 'Idle';
  return (
    <section className="panel p-4" aria-label="Battery status">
      <div className="flex items-baseline justify-between">
        <h3 className="font-display text-base font-semibold">Battery</h3>
        <span className="text-sm font-medium text-battery">{state}{state !== 'Idle' && ` ${fmtKw(Math.abs(point.battery_kw))}`}</span>
      </div>
      <div className="relative mt-3 h-3 rounded-full bg-paper" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="State of charge">
        <div className="h-3 rounded-full bg-battery transition-all" style={{ width: `${pct}%` }} />
        <div className="absolute top-[-3px] h-[18px] w-px bg-ink" style={{ left: `${minPct}%` }} title="Minimum charge" />
      </div>
      <p className="num mt-2 text-xs text-ink-soft">
        {fmt(point.battery_soc_kwh, 0)} of {fmt(cap, 0)} kWh ({fmt(pct, 0)}%). Reserve floor {fmt(system.battery_min_soc_kwh, 0)} kWh.
      </p>
    </section>
  );
}
