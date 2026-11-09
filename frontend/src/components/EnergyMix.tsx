import type { DispatchPoint } from '../types/api';
import { COLORS } from '../utils/theme';
import { ChartFrame } from './ChartFrame';

interface Props { dispatch: DispatchPoint[] | null; busy: boolean }

const sum = (rows: DispatchPoint[], f: (p: DispatchPoint) => number) =>
  Math.round(rows.reduce((s, p) => s + f(p), 0));

/** Where the 24-hour supply comes from, in kWh. */
export function EnergyMix({ dispatch, busy }: Props) {
  const option = dispatch?.length
    ? {
        animationDuration: 400,
        tooltip: { trigger: 'item', formatter: '{b}: {c} kWh ({d}%)' },
        legend: { bottom: 0, textStyle: { color: '#6B7A85' } },
        series: [{
          type: 'pie', radius: ['48%', '72%'], center: ['50%', '44%'],
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
          label: { show: false },
          data: [
            { name: 'Solar', value: sum(dispatch, (p) => p.solar_kw), itemStyle: { color: COLORS.solar } },
            { name: 'Wind', value: sum(dispatch, (p) => p.wind_kw), itemStyle: { color: COLORS.wind } },
            { name: 'Hydro', value: sum(dispatch, (p) => p.hydro_kw), itemStyle: { color: COLORS.hydro } },
            { name: 'Battery', value: sum(dispatch, (p) => Math.max(0, p.battery_kw)), itemStyle: { color: COLORS.battery } },
            { name: 'Grid', value: sum(dispatch, (p) => p.grid_kw), itemStyle: { color: COLORS.grid } },
          ],
        }],
      }
    : null;
  return (
    <ChartFrame title="Energy mix" caption="24-hour supply by source (kWh)" option={option} busy={busy} height={320} />
  );
}
