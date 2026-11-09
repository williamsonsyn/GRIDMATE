import type { Phase } from '../hooks/useSimulation';
import type { ScenarioId, ScenarioInfo } from '../types/api';

interface Props {
  scenarios: ScenarioInfo[];
  selected: ScenarioId;
  active: ScenarioId | null;
  phase: Phase;
  selectedDate: string;
  dateNote?: string | null;
  onSelect: (s: ScenarioId) => void;
  onDateChange: (d: string) => void;
  onRun: () => void;
  onCompare: () => void;
}

const STEP: Record<Phase, string> = {
  idle: '', forecasting: 'Forecasting...', optimizing: 'Optimizing dispatch...', updating: 'Updating digital twin...',
};
const ORDER: Phase[] = ['forecasting', 'optimizing', 'updating'];

export function ScenarioSelector({
  scenarios,
  selected,
  active,
  phase,
  selectedDate,
  dateNote,
  onSelect,
  onDateChange,
  onRun,
  onCompare,
}: Props) {
  const busy = phase !== 'idle';
  const current = scenarios.find((s) => s.id === selected);
  const stale = !busy && active !== null && active !== selected;
  return (
    <div className="panel flex flex-wrap items-end gap-x-6 gap-y-3 p-4">
      <div className="min-w-[200px]">
        <label htmlFor="scenario" className="mb-1 block text-sm font-medium">Scenario</label>
        <select id="scenario" value={selected} disabled={busy} onChange={(e) => onSelect(e.target.value as ScenarioId)}
          className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm disabled:opacity-60">
          {scenarios.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>
      <div className="min-w-[170px]">
        <label htmlFor="forecast-date" className="mb-1 block text-sm font-medium">Date</label>
        <input
          id="forecast-date"
          type="date"
          value={selectedDate}
          disabled={busy}
          onChange={(e) => onDateChange(e.target.value)}
          className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm disabled:opacity-60"
        />
      </div>
      <button type="button" onClick={onRun} disabled={busy}
        className="btn bg-teal-700 text-white hover:bg-teal-800 disabled:cursor-wait disabled:opacity-60">
        {busy ? 'Running...' : 'Run Simulation'}
      </button>
      <button type="button" onClick={onCompare} disabled={busy}
        className="btn bg-paper text-ink-soft hover:bg-line disabled:cursor-wait disabled:opacity-60">
        Compare all scenarios
      </button>
      <div className="min-w-[240px] flex-1 flex flex-wrap items-center gap-2" aria-live="polite">
        {busy ? (
          <ol className="flex gap-3 text-sm">
            {ORDER.map((p) => {
              const done = ORDER.indexOf(p) < ORDER.indexOf(phase);
              const now = p === phase;
              return <li key={p} className={now ? 'font-semibold text-teal-800' : done ? 'text-ink-mute line-through' : 'text-ink-mute'}>{STEP[p]}</li>;
            })}
          </ol>
        ) : stale ? (
          <p className="text-sm text-amber-800">Parameters changed. Click Run Simulation to update forecast and dispatch.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm text-ink-soft">{current?.description}</p>
            {dateNote && (
              <span className="inline-flex items-center rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 border border-amber-200">
                {dateNote}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
