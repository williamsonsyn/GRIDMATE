import type { DispatchPoint } from '../types/api';
import { COLORS, AXIS } from '../utils/theme';
import { hourLabel } from '../utils/format';
import { ChartFrame } from './ChartFrame';

interface Props { dispatch: DispatchPoint[] | null; busy: boolean; hour: number }

/** Optimized dispatch: stacked supply above zero, battery charging and curtailment below zero. */
export function DispatchChart({ dispatch, busy, hour }: Props) {
  const labels = dispatch?.map((p) => hourLabel(p.timestamp)) ?? [];
  const bar = (name: string, color: string, stack: string, data: number[]) => ({
    name, type: 'bar', stack, color, data, barCategoryGap: '25%',
  });
  const option = dispatch?.length
    ? {
        animationDuration: 400,
        grid: { left: 48, right: 16, top: 50, bottom: 28 },
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { top: 0, textStyle: AXIS, type: 'scroll' },
        xAxis: { type: 'category', data: labels, axisLabel: { ...AXIS, interval: 2 } },
        yAxis: { type: 'value', name: 'kW', nameTextStyle: AXIS, axisLabel: AXIS, splitLine: { lineStyle: { color: '#E6EAE6' } } },
        series: [
          bar('Solar', COLORS.solar, 'supply', dispatch.map((p) => p.solar_kw)),
          bar('Wind', COLORS.wind, 'supply', dispatch.map((p) => p.wind_kw)),
          bar('Hydro', COLORS.hydro, 'supply', dispatch.map((p) => p.hydro_kw)),
          bar('Battery discharge', COLORS.battery, 'supply', dispatch.map((p) => Math.max(0, p.battery_kw))),
          bar('Grid import', COLORS.grid, 'supply', dispatch.map((p) => p.grid_kw)),
          bar('Battery charging', '#6EE7B7', 'sink', dispatch.map((p) => Math.min(0, p.battery_kw))),
          bar('Curtailment', '#9CA3AF', 'sink', dispatch.map((p) => -p.curtailment_kw)),
          {
            name: 'Demand', type: 'line', color: COLORS.demand, showSymbol: false, lineStyle: { width: 3 },
            data: dispatch.map((p) => p.load_kw),
            markLine: {
              symbol: 'none', silent: true, lineStyle: { color: '#14212B', type: 'dashed' },
              label: { formatter: 'selected hour', color: '#14212B', fontSize: 11 },
              data: [{ xAxis: labels[hour] ?? labels[0] }],
            },
          },
        ],
      }
    : null;
  return (
    <ChartFrame
      title="Optimized dispatch"
      caption="PyPSA / HiGHS schedule. Bars below zero are battery charging and curtailed energy (kW)"
      option={option} busy={busy} height={320} empty="No dispatch available."
    />
  );
}
