import { useEffect, useRef } from 'react';
import type { ScenarioSummaryRow } from '../types/api';

interface Props {
  rows: ScenarioSummaryRow[] | null;
  loading: boolean;
  error: string | null;
  activeScenario: string | null;
  onClose: () => void;
}

function fmt1(n: number): string {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtRs(n: number): string {
  if (n === 0) return '–';
  return `₹${Math.round(n).toLocaleString('en-IN')}`;
}

function fmtKg(n: number): string {
  return Math.round(n).toLocaleString('en-IN');
}

/** Highlight the best value in a column; direction: 'max' = higher is better, 'min' = lower is better */
function bestIdx(rows: ScenarioSummaryRow[], key: keyof ScenarioSummaryRow, direction: 'max' | 'min'): number {
  const vals = rows.map((r) => Number(r[key]));
  return direction === 'max'
    ? vals.indexOf(Math.max(...vals))
    : vals.indexOf(Math.min(...vals));
}

export function ScenarioComparisonModal({ rows, loading, error, activeScenario, onClose }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (!el.open) el.showModal();
    const handler = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      if (
        e.clientX < rect.left || e.clientX > rect.right ||
        e.clientY < rect.top || e.clientY > rect.bottom
      ) onClose();
    };
    el.addEventListener('click', handler);
    return () => el.removeEventListener('click', handler);
  }, [onClose]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const cols: Array<{
    key: keyof ScenarioSummaryRow;
    label: string;
    unit: string;
    best: 'max' | 'min' | null;
    fmt: (v: number) => string;
  }> = [
    { key: 'renewable_penetration_percent', label: 'Renewable %', unit: '%', best: 'max', fmt: fmt1 },
    { key: 'grid_dependency_percent',       label: 'Grid dep. %', unit: '%', best: 'min', fmt: fmt1 },
    { key: 'curtailment_percent',           label: 'Curtail. %',  unit: '%', best: 'min', fmt: fmt1 },
    { key: 'battery_utilization_percent',   label: 'Battery util.',unit: '%', best: null,  fmt: fmt1 },
    { key: 'estimated_co2_avoided_kg',      label: 'CO₂ avoided', unit: 'kg', best: 'max', fmt: fmtKg },
    { key: 'total_grid_cost_rs',            label: 'Grid cost',   unit: '₹',  best: 'min', fmt: fmtRs },
    { key: 'savings_rs',                    label: 'Savings',     unit: '₹',  best: 'max', fmt: fmtRs },
    { key: 'savings_percent',               label: 'Savings %',   unit: '%',  best: 'max', fmt: fmt1 },
  ];

  return (
    <dialog
      ref={dialogRef}
      className="m-auto max-h-[90vh] w-full max-w-4xl overflow-auto rounded-[12px] border border-line bg-white p-6 shadow-2xl backdrop:bg-ink/40"
      aria-modal="true"
      aria-label="Scenario comparison"
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-xl font-semibold">Scenario comparison</h2>
          <p className="mt-0.5 text-sm text-ink-mute">
            All 5 weather scenarios, full pipeline — forecast → dispatch → metrics.
            {rows && rows[0]?.total_grid_cost_rs === 0 && (
              <> Cost figures require the PyPSA optimizer (not available in mock mode).</>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close comparison"
          className="btn bg-paper text-ink-soft hover:bg-line shrink-0"
        >
          ✕
        </button>
      </div>

      {loading && (
        <div className="flex h-40 items-center justify-center text-sm text-ink-mute">
          Running all scenarios… this may take a moment.
        </div>
      )}

      {error && !loading && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">{error}</div>
      )}

      {rows && !loading && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="pb-2 pr-4 text-left font-medium text-ink-soft">Scenario</th>
                {cols.map((c) => (
                  <th key={c.key} className="pb-2 px-2 text-right font-medium text-ink-soft whitespace-nowrap">
                    {c.label}
                    <span className="ml-0.5 text-xs font-normal text-ink-mute">({c.unit})</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((row, ri) => {
                const isActive = row.scenario === activeScenario;
                return (
                  <tr key={row.scenario} className={isActive ? 'bg-teal-50' : ri % 2 === 1 ? 'bg-paper/50' : ''}>
                    <td className="py-2 pr-4 font-medium whitespace-nowrap">
                      {row.label}
                      {isActive && (
                        <span className="ml-2 rounded-full bg-teal-700 px-1.5 py-0.5 text-[10px] font-semibold text-white">active</span>
                      )}
                    </td>
                    {cols.map((c) => {
                      const val = Number(row[c.key]);
                      const isBest = c.best ? bestIdx(rows, c.key, c.best) === ri : false;
                      return (
                        <td
                          key={c.key}
                          className={`num py-2 px-2 text-right tabular-nums ${isBest ? 'font-semibold text-emerald-700' : ''}`}
                        >
                          {c.fmt(val)}
                          {isBest && <span className="ml-1 text-[10px]">↑</span>}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-ink-mute">
            Best value per column highlighted in green (↑). Cost figures are prototype estimates based on assumed ToD tariffs, not billing-grade values.
          </p>
        </div>
      )}
    </dialog>
  );
}

