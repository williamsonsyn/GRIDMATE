import type { Phase } from '../hooks/useSimulation';
import type { ScenarioId, ScenarioInfo } from '../types/api';

interface Props {
  scenarios: ScenarioInfo[];
  selected: ScenarioId;
  active: ScenarioId | null;
  phase: Phase;
  onSelect: (s: ScenarioId) => void;
  onRun: () => void;
}

const STEP: Record<Phase, string> = {
  idle: '', forecasting: 'Forecasting...', optimizing: 'Optimizing dispatch...', updating: 'Updating digital twin...',
};
const ORDER: Phase[] = ['forecasting', 'optimizing', 'updating'];

export function ScenarioSelector({ scenarios, selected, active, phase, onSelect, onRun }: Props) {
  const busy = phase !== 'idle';
  const current = scenarios.find((s) => s.id === selected);
  const stale = !busy && active !== null && active !== selected;
  return (
    <div className="panel flex flex-wrap items-end gap-x-6 gap-y-3 p-4">
      <div className="min-w-[220px]">
        <label htmlFor="scenario" className="mb-1 block text-sm font-medium">Scenario</label>
        <select id="scenario" value={selected} disabled={busy} onChange={(e) => onSelect(e.target.value as ScenarioId)}
          className="w-full rounded-md border border-line bg-white px-3 py-2 text-sm disabled:opacity-60">
          {scenarios.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>
      <button type="button" onClick={onRun} disabled={busy}
        className="btn bg-teal-700 text-white hover:bg-teal-800 disabled:cursor-wait disabled:opacity-60">
        {busy ? 'Running...' : 'Run Simulation'}
      </button>
      <div className="min-w-[240px] flex-1" aria-live="polite">
        {busy ? (
          <ol className="flex gap-3 text-sm">
            {ORDER.map((p) => {
              const done = ORDER.indexOf(p) < ORDER.indexOf(phase);
              const now = p === phase;
              return <li key={p} className={now ? 'font-semibold text-teal-800' : done ? 'text-ink-mute line-through' : 'text-ink-mute'}>{STEP[p]}</li>;
            })}
          </ol>
        ) : stale ? (
          <p className="text-sm text-amber-800">Scenario changed. Click Run Simulation to update the forecast, dispatch, metrics and map.</p>
        ) : (
          <p className="text-sm text-ink-soft">{current?.description}</p>
        )}
      </div>
    </div>
  );
}
