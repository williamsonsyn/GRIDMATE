import type { ForecastPoint } from '../types/api';
import { AXIS } from '../utils/theme';
import { hourLabel } from '../utils/format';
import { ChartFrame } from './ChartFrame';

interface Props { forecast: ForecastPoint[] | null; busy: boolean }

/** Demand against total forecast renewable generation: the gap is what the battery and grid must cover. */
export function DemandChart({ forecast, busy }: Props) {
  const option = forecast?.length
    ? {
        animationDuration: 400,
        grid: { left: 48, right: 16, top: 36, bottom: 28 },
        tooltip: { trigger: 'axis' },
        legend: { top: 0, textStyle: AXIS },
        xAxis: { type: 'category', data: forecast.map((p) => hourLabel(p.timestamp)), axisLabel: { ...AXIS, interval: 2 } },
        yAxis: { type: 'value', name: 'kW', nameTextStyle: AXIS, axisLabel: AXIS, splitLine: { lineStyle: { color: '#E6EAE6' } } },
        series: [
          {
            name: 'Renewable generation', type: 'line', smooth: true, showSymbol: false, color: '#0F766E',
            areaStyle: { opacity: 0.18 },
            data: forecast.map((p) => +(p.solar_kw + p.wind_kw + p.hydro_kw).toFixed(1)),
          },
          { name: 'Demand', type: 'line', smooth: true, showSymbol: false, color: '#8B5CF6', lineStyle: { width: 3 }, data: forecast.map((p) => p.load_kw) },
        ],
      }
    : null;
  return (
    <ChartFrame
      title="Generation vs demand"
      caption="Where demand exceeds renewables, the battery and grid step in"
      option={option} busy={busy} empty="No forecast available."
    />
  );
}
