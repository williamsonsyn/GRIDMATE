import type { Metrics } from '../types/api';

export function hourLabel(timestamp: string): string {
  const m = /T(\d{2}):(\d{2})/.exec(timestamp);
  return m ? `${m[1]}:${m[2]}` : timestamp;
}

export function fmt(n: number, digits = 1): string {
  return n.toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function fmtKw(n: number): string {
  return `${Math.round(n).toLocaleString('en-IN')} kW`;
}

export type MetricKey = keyof Metrics;

/** Whether a rising value is good (true), bad (false) or neutral (null). */
export const METRIC_DIRECTION: Record<MetricKey, boolean | null> = {
  renewable_penetration_percent: true,
  grid_dependency_percent: false,
  curtailment_percent: false,
  battery_utilization_percent: null,
  estimated_co2_avoided_kg: true,
};
