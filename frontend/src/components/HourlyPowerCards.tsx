import type { DispatchPoint } from '../types/api';
import { fmtKw, hourLabel } from '../utils/format';
import { COLORS } from '../utils/theme';

interface Props {
  point: DispatchPoint | null;
  previousPoint: DispatchPoint | null;
  hour: number;
  selectedDate: string;
  busy?: boolean;
}

interface SourceCardProps {
  name: string;
  dotColor: string;
  kw: number;
  totalLoadKw: number;
  deltaKw: number | null;
  subLabel?: string;
  statusText?: string;
  statusTone?: string;
  busy?: boolean;
}

function SourceCard({
  name,
  dotColor,
  kw,
  totalLoadKw,
  deltaKw,
  subLabel,
  statusText,
  statusTone,
  busy,
}: SourceCardProps) {
  const sharePct = totalLoadKw > 0 ? Math.min(100, Math.max(0, (kw / totalLoadKw) * 100)) : 0;
  const hasDelta = deltaKw !== null;
  const deltaSignificant = hasDelta && Math.abs(deltaKw) >= 0.1;

  return (
    <div className="panel p-4 flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between gap-1.5">
          <span className="flex items-center gap-2 text-sm font-medium text-ink-soft">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: dotColor }} />
            {name}
          </span>
          {statusText && (
            <span className={`text-[10px] font-bold uppercase rounded px-1.5 py-0.5 ${statusTone || 'bg-slate-100 text-slate-600'}`}>
              {statusText}
            </span>
          )}
        </div>

        <p className={`num mt-2 font-display text-3xl xl:text-4xl font-semibold leading-none transition-opacity ${busy ? 'opacity-40' : ''}`}>
          {fmtKw(kw)}
        </p>

        <p className="mt-2 text-xs font-medium text-ink-soft">
          {subLabel || `${sharePct.toFixed(1)}% of total demand`}
        </p>
      </div>

      <p className="num mt-2 pt-2 border-t border-slate-100 min-h-[1.25rem] text-xs text-ink-mute">
        {deltaSignificant
          ? `${deltaKw > 0 ? '+' : ''}${fmtKw(deltaKw)} vs previous hour`
          : hasDelta
          ? 'No change vs previous hour'
          : 'First hour of forecast'}
      </p>
    </div>
  );
}

export function HourlyPowerCards({ point, previousPoint, hour, selectedDate, busy }: Props) {
  const loadKw = point?.load_kw ?? 0;
  const timeText = point ? hourLabel(point.timestamp) : `${String(hour).padStart(2, '0')}:00`;

  // Battery status and power calculation
  const batteryKw = point?.battery_kw ?? 0;
  const prevBatteryKw = previousPoint?.battery_kw ?? 0;
  const isDischarging = batteryKw > 0.05;
  const isCharging = batteryKw < -0.05;
  const batteryAbsKw = Math.abs(batteryKw);
  const batteryStatus = isDischarging ? 'Discharging' : isCharging ? 'Charging' : 'Idle';
  const batteryTone = isDischarging
    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
    : isCharging
    ? 'bg-sky-50 text-sky-700 border border-sky-200'
    : 'bg-slate-100 text-slate-600';

  const batteryDelta = point && previousPoint ? batteryAbsKw - Math.abs(prevBatteryKw) : null;
  const batterySubLabel = isDischarging
    ? `${((batteryAbsKw / (loadKw || 1)) * 100).toFixed(1)}% of demand met`
    : isCharging
    ? `Charging (${point?.battery_soc_kwh.toFixed(0)} kWh SOC)`
    : `Idle (${point ? point.battery_soc_kwh.toFixed(0) : '--'} kWh SOC)`;

  return (
    <section aria-label="Expected hourly power breakdown">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-lg font-semibold">
          Expected power for <span className="text-cyan-700 font-mono">{timeText}</span> on <span className="font-mono">{selectedDate}</span>
        </h2>
        <span className="text-xs text-ink-mute">
          Selected hour dispatch • Total demand load: <strong className="text-ink">{fmtKw(loadKw)}</strong>
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <SourceCard
          name="Solar"
          dotColor={COLORS.solar}
          kw={point?.solar_kw ?? 0}
          totalLoadKw={loadKw}
          deltaKw={point && previousPoint ? point.solar_kw - previousPoint.solar_kw : null}
          busy={busy}
        />
        <SourceCard
          name="Wind"
          dotColor={COLORS.wind}
          kw={point?.wind_kw ?? 0}
          totalLoadKw={loadKw}
          deltaKw={point && previousPoint ? point.wind_kw - previousPoint.wind_kw : null}
          busy={busy}
        />
        <SourceCard
          name="Hydro"
          dotColor={COLORS.hydro}
          kw={point?.hydro_kw ?? 0}
          totalLoadKw={loadKw}
          deltaKw={point && previousPoint ? point.hydro_kw - previousPoint.hydro_kw : null}
          busy={busy}
        />
        <SourceCard
          name="Battery"
          dotColor={COLORS.battery}
          kw={batteryAbsKw}
          totalLoadKw={loadKw}
          deltaKw={batteryDelta}
          statusText={batteryStatus}
          statusTone={batteryTone}
          subLabel={batterySubLabel}
          busy={busy}
        />
        <SourceCard
          name="Grid Import"
          dotColor={COLORS.grid}
          kw={point?.grid_kw ?? 0}
          totalLoadKw={loadKw}
          deltaKw={point && previousPoint ? point.grid_kw - previousPoint.grid_kw : null}
          busy={busy}
        />
      </div>
    </section>
  );
}
