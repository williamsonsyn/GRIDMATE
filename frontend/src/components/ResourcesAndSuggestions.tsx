import type { SuggestionsResponse } from '../types/api';
import { fmtKw } from '../utils/format';
import { COLORS } from '../utils/theme';

interface Props {
  suggestions: SuggestionsResponse | null;
  busy?: boolean;
}

const SOURCE_COLORS: Record<string, string> = {
  solar: COLORS.solar,
  wind: COLORS.wind,
  hydro: COLORS.hydro,
  battery: COLORS.battery,
  grid: COLORS.grid,
};

export function ResourcesAndSuggestions({ suggestions, busy }: Props) {
  if (!suggestions) {
    return (
      <section className="panel p-6" aria-label="Resources & suggestions">
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <h2 className="font-display text-lg font-semibold text-ink">Resources & suggestions to reduce grid use</h2>
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-ink-mute">
            estimates from the simulation
          </span>
        </div>
        <p className="mt-4 text-sm text-ink-mute">Loading resource utilization and optimization suggestions...</p>
      </section>
    );
  }

  const { resources, suggestions: rankedOptions, peak_grid_hours, peak_grid_reason } = suggestions;

  return (
    <section className="space-y-4" aria-label="Resources & suggestions to reduce grid use">
      {/* Section Header */}
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">
            Resources & suggestions to reduce grid use
          </h2>
          <p className="text-xs text-ink-mute">
            Resource capacity headroom vs utilization and linear programming (PyPSA) options to minimize grid dependence
          </p>
        </div>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-800 border border-cyan-200">
          estimates from the simulation
        </span>
      </div>

      {/* Main Grid: Resources utilization on left, Peak analysis + Suggestions on right */}
      <div className="grid gap-4 lg:grid-cols-12">
        {/* 1. Resources Capacity & Headroom Table (5 cols on lg) */}
        <div className={`panel p-4 lg:col-span-5 transition-opacity ${busy ? 'opacity-50' : ''}`}>
          <div className="border-b border-slate-100 pb-2.5 mb-3">
            <h3 className="font-display text-base font-semibold text-ink">Resource Capacity & Headroom</h3>
            <p className="text-xs text-ink-mute">Installed capacity vs average & peak use, with available unused headroom</p>
          </div>

          <div className="space-y-3">
            {resources.map((res) => {
              const dotColor = SOURCE_COLORS[res.source] || '#64748b';
              const utilPct = res.installed_kw > 0 ? Math.min(100, (res.peak_use_kw / res.installed_kw) * 100) : 0;
              const headroomPct = res.headroom_percent;

              return (
                <div key={res.source} className="rounded-lg border border-slate-100 bg-slate-50/60 p-2.5">
                  <div className="flex items-center justify-between text-xs font-medium mb-1">
                    <span className="flex items-center gap-1.5 text-ink">
                      <span className="h-2 w-2 rounded-full shrink-0" style={{ background: dotColor }} />
                      <strong className="font-semibold">{res.name}</strong>
                    </span>
                    <span className="font-mono text-ink-mute text-[11px]">
                      Cap: {fmtKw(res.installed_kw)}
                      {res.capacity_kwh ? ` (${res.capacity_kwh} kWh)` : ''}
                    </span>
                  </div>

                  {/* Progress Bar showing peak use vs headroom */}
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 flex my-1.5">
                    <div
                      className="h-full transition-all duration-500 rounded-l-full"
                      style={{ width: `${utilPct}%`, background: dotColor }}
                      title={`Peak Use: ${fmtKw(res.peak_use_kw)} (${utilPct.toFixed(0)}%)`}
                    />
                    <div
                      className="h-full bg-emerald-200/80 transition-all duration-500"
                      style={{ width: `${headroomPct}%` }}
                      title={`Unused Headroom: ${fmtKw(res.headroom_kw)} (${headroomPct.toFixed(0)}%)`}
                    />
                  </div>

                  {/* Metrics Row */}
                  <div className="flex items-center justify-between text-[11px] text-ink-soft">
                    <span>
                      Avg: <strong className="font-mono text-ink">{fmtKw(res.avg_use_kw)}</strong> • Peak: <strong className="font-mono text-ink">{fmtKw(res.peak_use_kw)}</strong>
                    </span>
                    <span className={`font-semibold ${headroomPct > 20 ? 'text-emerald-700' : 'text-amber-700'}`}>
                      {fmtKw(res.headroom_kw)} headroom ({headroomPct.toFixed(0)}%)
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 2. Peak Hours Root Cause & Top Ranked Suggestions (7 cols on lg) */}
        <div className="space-y-4 lg:col-span-7">
          {/* Peak Grid Hours & Reason Card */}
          <div className={`panel p-4 border-l-4 border-l-rose-500 transition-opacity ${busy ? 'opacity-50' : ''}`}>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
              <h4 className="text-sm font-bold text-ink flex items-center gap-2">
                <span className="flex h-2 w-2 rounded-full bg-rose-500" />
                Peak Grid Import Hours: {peak_grid_hours.join(', ')}
              </h4>
              <span className="text-[11px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                Highest Grid Strain
              </span>
            </div>
            <p className="text-xs text-ink-soft leading-relaxed">
              {peak_grid_reason}
            </p>
          </div>

          {/* Top 3 Ranked Suggestion Cards */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-base font-semibold text-ink">
                Top Optimization Suggestions to Reduce Grid
              </h3>
              <span className="text-xs text-ink-mute">Tested with PyPSA solver • Ranked by cost savings</span>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {rankedOptions.map((opt) => {
                const isRank1 = opt.rank === 1;
                const dotColor = SOURCE_COLORS[opt.option_type] || '#06b6d4';

                return (
                  <div
                    key={opt.id}
                    className={`panel p-3.5 flex flex-col justify-between transition-all hover:shadow-md ${
                      isRank1 ? 'border-cyan-500/80 bg-gradient-to-b from-cyan-50/40 to-white shadow-sm' : ''
                    }`}
                  >
                    <div>
                      {/* Rank Badge & Option Type */}
                      <div className="flex items-center justify-between gap-1 mb-2">
                        <span
                          className={`text-[10px] font-bold uppercase rounded px-1.5 py-0.5 ${
                            isRank1
                              ? 'bg-cyan-600 text-white'
                              : opt.rank === 2
                              ? 'bg-emerald-600 text-white'
                              : 'bg-slate-700 text-white'
                          }`}
                        >
                          Rank #{opt.rank}
                        </span>
                        <span
                          className="text-[10px] font-semibold rounded px-1.5 py-0.5 text-white"
                          style={{ background: dotColor }}
                        >
                          {opt.capacity_added}
                        </span>
                      </div>

                      {/* Title */}
                      <h4 className="text-xs font-bold text-ink leading-snug">
                        {opt.title}
                      </h4>

                      {/* Description */}
                      <p className="text-[11px] text-ink-soft mt-1.5 line-clamp-3 leading-relaxed">
                        {opt.description}
                      </p>
                    </div>

                    {/* Impact Numbers */}
                    <div className="mt-3 pt-2.5 border-t border-slate-100 space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-ink-mute text-[11px]">Grid Reduction:</span>
                        <span className="font-mono font-bold text-emerald-700">
                          -{opt.grid_reduction_kwh.toLocaleString('en-IN')} kWh ({opt.grid_reduction_percent}%)
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-ink-mute text-[11px]">Est. Savings:</span>
                        <span className="font-mono font-bold text-cyan-800">
                          ₹{Math.round(opt.savings_rs).toLocaleString('en-IN')} / day
                        </span>
                      </div>
                      <div className="text-[9px] text-ink-mute text-right pt-0.5">
                        * estimates from the simulation
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
