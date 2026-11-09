import { useState } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import type { ScenarioId, ScenarioSummaryRow } from '../types/api';
import { ChartFrame } from './ChartFrame';
import { AXIS } from '../utils/theme';

interface Props {
  rows: ScenarioSummaryRow[] | null;
  loading: boolean;
  error: string | null;
  activeScenario: ScenarioId | null;
  onSelectScenario: (scenario: ScenarioId) => void;
  onRefresh?: () => void;
}

type ViewMode = 'both' | 'chart' | 'table';

function fmtRs(n: number): string {
  if (n === 0) return '–';
  return `₹${Math.round(n).toLocaleString('en-IN')}`;
}

function fmt1(n: number): string {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function bestIdx(rows: ScenarioSummaryRow[], key: keyof ScenarioSummaryRow, direction: 'max' | 'min'): number {
  const vals = rows.map((r) => Number(r[key]));
  return direction === 'max'
    ? vals.indexOf(Math.max(...vals))
    : vals.indexOf(Math.min(...vals));
}

export function CompareScenarios({
  rows,
  loading,
  error,
  activeScenario,
  onSelectScenario,
  onRefresh,
}: Props) {
  const [view, setView] = useState<ViewMode>('both');

  const categories = rows?.map((r) => r.label || r.scenario) ?? [];
  const costData = rows?.map((r) => Math.round(r.total_grid_cost_rs)) ?? [];
  const savingsData = rows?.map((r) => Math.round(r.savings_rs)) ?? [];
  const batteryData = rows?.map((r) => Number(r.battery_utilization_percent.toFixed(1))) ?? [];

  const chartOption: EChartsCoreOption | null = rows?.length
    ? {
        animationDuration: 400,
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (params: unknown) => {
            const arr = params as Array<{
              axisValueLabel: string;
              marker: string;
              seriesName: string;
              value: number;
            }>;
            if (!Array.isArray(arr) || !arr.length) return '';
            const title = `<div style="font-weight:600;margin-bottom:6px;font-size:13px">${arr[0].axisValueLabel}</div>`;
            const lines = arr.map((p) => {
              const val = p.seriesName.includes('%')
                ? `${p.value}%`
                : `₹${Number(p.value).toLocaleString('en-IN')}`;
              return `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:12px;margin:2px 0">
                <span>${p.marker} ${p.seriesName}</span>
                <span style="font-weight:600;font-variant-numeric:tabular-nums">${val}</span>
              </div>`;
            });
            return title + lines.join('');
          },
        },
        legend: {
          top: 0,
          textStyle: AXIS,
          data: ['Total Grid Cost', 'Savings', 'Battery Utilization (%)'],
        },
        grid: { left: 60, right: 54, top: 40, bottom: 32 },
        xAxis: {
          type: 'category',
          data: categories,
          axisLabel: { ...AXIS, interval: 0, fontSize: 11 },
        },
        yAxis: [
          {
            type: 'value',
            name: 'Cost / Savings (₹)',
            nameTextStyle: AXIS,
            axisLabel: {
              ...AXIS,
              formatter: (v: number) => `₹${v >= 1000 ? `${Math.round(v / 1000)}k` : v}`,
            },
            splitLine: { lineStyle: { color: '#E6EAE6' } },
          },
          {
            type: 'value',
            name: 'Battery (%)',
            nameTextStyle: AXIS,
            min: 0,
            max: (value: { max: number }) => Math.max(10, Math.ceil(value.max * 1.25)),
            axisLabel: {
              ...AXIS,
              formatter: '{value}%',
            },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: 'Total Grid Cost',
            type: 'bar',
            data: costData,
            color: '#EF4444',
            barMaxWidth: 30,
            itemStyle: { borderRadius: [4, 4, 0, 0] },
          },
          {
            name: 'Savings',
            type: 'bar',
            data: savingsData,
            color: '#10B981',
            barMaxWidth: 30,
            itemStyle: { borderRadius: [4, 4, 0, 0] },
          },
          {
            name: 'Battery Utilization (%)',
            type: 'bar',
            yAxisIndex: 1,
            data: batteryData,
            color: '#8B5CF6',
            barMaxWidth: 20,
            itemStyle: { borderRadius: [4, 4, 0, 0] },
          },
        ],
      }
    : null;

  const minCostIdx = rows ? bestIdx(rows, 'total_grid_cost_rs', 'min') : -1;
  const maxSavingsIdx = rows ? bestIdx(rows, 'savings_rs', 'max') : -1;
  const maxRenewableIdx = rows ? bestIdx(rows, 'renewable_penetration_percent', 'max') : -1;

  return (
    <section className="panel p-5 space-y-4" aria-label="Compare Scenarios">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg font-semibold text-ink">Compare Scenarios</h2>
            <span className="rounded-full bg-paper px-2 py-0.5 text-[11px] font-medium text-ink-mute">
              optimization/src/run_scenarios.py
            </span>
          </div>
          <p className="mt-0.5 text-xs text-ink-mute">
            Side-by-side comparison of grid cost, ToD savings, and battery utilization across all 5 scenarios.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="btn btn-sm bg-paper text-ink-soft hover:bg-line disabled:opacity-50"
              title="Re-run scenario comparison"
            >
              {loading ? 'Running…' : '↻ Re-run all'}
            </button>
          )}

          <div className="flex rounded-md border border-line bg-paper/60 p-0.5 text-xs font-medium">
            <button
              type="button"
              onClick={() => setView('both')}
              className={`rounded px-2.5 py-1 transition-colors ${
                view === 'both' ? 'bg-white text-ink shadow-sm' : 'text-ink-mute hover:text-ink'
              }`}
            >
              Both
            </button>
            <button
              type="button"
              onClick={() => setView('chart')}
              className={`rounded px-2.5 py-1 transition-colors ${
                view === 'chart' ? 'bg-white text-ink shadow-sm' : 'text-ink-mute hover:text-ink'
              }`}
            >
              Bar Chart
            </button>
            <button
              type="button"
              onClick={() => setView('table')}
              className={`rounded px-2.5 py-1 transition-colors ${
                view === 'table' ? 'bg-white text-ink shadow-sm' : 'text-ink-mute hover:text-ink'
              }`}
            >
              Table
            </button>
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex h-36 items-center justify-center text-sm text-ink-mute">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />
            <span>Solving all 5 scenarios with PyPSA / HiGHS…</span>
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          Failed to load scenario comparison: {error}
        </div>
      )}

      {rows && !loading && (
        <div className={`grid gap-4 ${view === 'both' ? 'lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1.8fr)]' : 'grid-cols-1'}`}>
          {(view === 'both' || view === 'chart') && (
            <div className="rounded-[10px] border border-line bg-paper/30 p-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-mute">
                Cost, Savings & Battery Utilization Chart
              </h3>
              <ChartFrame
                title=""
                option={chartOption}
                height={300}
                busy={loading}
                empty="No scenario comparison data available."
              />
            </div>
          )}

          {(view === 'both' || view === 'table') && (
            <div className="overflow-x-auto rounded-[10px] border border-line bg-white p-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-mute">
                Side-by-Side Comparison Matrix
              </h3>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line text-ink-soft">
                    <th className="pb-2 text-left font-semibold">Scenario</th>
                    <th className="pb-2 px-2 text-right font-semibold">Grid Cost</th>
                    <th className="pb-2 px-2 text-right font-semibold">Savings</th>
                    <th className="pb-2 px-2 text-right font-semibold">Savings %</th>
                    <th className="pb-2 px-2 text-right font-semibold">Battery Use</th>
                    <th className="pb-2 px-2 text-right font-semibold">Renewable %</th>
                    <th className="pb-2 px-2 text-center font-semibold">Status</th>
                    <th className="pb-2 text-right font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((row, idx) => {
                    const isActive = row.scenario === activeScenario;
                    const isLowestCost = idx === minCostIdx;
                    const isHighestSavings = idx === maxSavingsIdx;
                    const isHighestRenewable = idx === maxRenewableIdx;

                    return (
                      <tr
                        key={row.scenario}
                        className={`transition-colors hover:bg-paper/60 ${
                          isActive ? 'bg-teal-50/70 font-medium' : idx % 2 === 1 ? 'bg-paper/30' : ''
                        }`}
                      >
                        <td className="py-2.5 pr-2 whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-ink">{row.label}</span>
                            {isActive && (
                              <span className="rounded-full bg-teal-700 px-1.5 py-0.2 text-[9px] font-bold tracking-wide text-white">
                                ACTIVE
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-ink-mute">{row.scenario}</span>
                        </td>

                        <td className={`py-2.5 px-2 text-right tabular-nums ${isLowestCost ? 'font-bold text-emerald-700' : 'text-ink'}`}>
                          {fmtRs(row.total_grid_cost_rs)}
                          {isLowestCost && <span className="ml-1 text-[10px] text-emerald-600 font-normal">min</span>}
                        </td>

                        <td className={`py-2.5 px-2 text-right tabular-nums ${isHighestSavings ? 'font-bold text-emerald-700' : 'text-ink'}`}>
                          {fmtRs(row.savings_rs)}
                          {isHighestSavings && <span className="ml-1 text-[10px] text-emerald-600 font-normal">max</span>}
                        </td>

                        <td className="py-2.5 px-2 text-right tabular-nums text-ink-soft">
                          {fmt1(row.savings_percent)}%
                        </td>

                        <td className="py-2.5 px-2 text-right tabular-nums font-medium text-purple-700">
                          {fmt1(row.battery_utilization_percent)}%
                        </td>

                        <td className={`py-2.5 px-2 text-right tabular-nums ${isHighestRenewable ? 'font-semibold text-teal-700' : 'text-ink-soft'}`}>
                          {fmt1(row.renewable_penetration_percent)}%
                        </td>

                        <td className="py-2.5 px-2 text-center">
                          <span className="inline-block rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">
                            {row.validation || 'PASS'}
                          </span>
                        </td>

                        <td className="py-2.5 text-right whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() => onSelectScenario(row.scenario)}
                            disabled={isActive}
                            className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                              isActive
                                ? 'bg-line/40 text-ink-mute cursor-default'
                                : 'bg-teal-50 text-teal-800 hover:bg-teal-100'
                            }`}
                          >
                            {isActive ? 'Selected' : 'Simulate'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="mt-2.5 flex flex-wrap items-center justify-between text-[11px] text-ink-mute">
                <span>Green highlights indicate optimal cost and savings across scenarios.</span>
                <span>Values generated via PyPSA linear programming with ToD grid tariffs.</span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
