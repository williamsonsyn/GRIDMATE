import type { ForecastPoint } from '../types/api';
import { COLORS, AXIS } from '../utils/theme';
import { hourLabel } from '../utils/format';
import { ChartFrame } from './ChartFrame';

interface Props { forecast: ForecastPoint[] | null; busy: boolean }

/** AI forecast: solar, wind, hydro and demand over the 24-hour horizon. */
export function GenerationChart({ forecast, busy }: Props) {
  const option = forecast?.length
    ? {
        animationDuration: 400,
        color: [COLORS.solar, COLORS.wind, COLORS.hydro, COLORS.demand],
        grid: { left: 48, right: 16, top: 36, bottom: 28 },
        tooltip: { trigger: 'axis' },
        legend: { top: 0, textStyle: AXIS },
        xAxis: { type: 'category', data: forecast.map((p) => hourLabel(p.timestamp)), axisLabel: { ...AXIS, interval: 2 } },
        yAxis: { type: 'value', name: 'kW', nameTextStyle: AXIS, axisLabel: AXIS, splitLine: { lineStyle: { color: '#E6EAE6' } } },
        series: [
          { name: 'Solar', type: 'line', smooth: true, showSymbol: false, data: forecast.map((p) => p.solar_kw) },
          { name: 'Wind', type: 'line', smooth: true, showSymbol: false, data: forecast.map((p) => p.wind_kw) },
          { name: 'Hydro', type: 'line', smooth: true, showSymbol: false, data: forecast.map((p) => p.hydro_kw) },
          { name: 'Demand', type: 'line', smooth: true, showSymbol: false, lineStyle: { width: 3 }, data: forecast.map((p) => p.load_kw) },
        ],
      }
    : null;
  return (
    <ChartFrame
      title="AI forecast"
      caption="Predicted generation and demand for the next 24 hours (kW)"
      option={option} busy={busy} empty="No forecast available."
    />
  );
}
