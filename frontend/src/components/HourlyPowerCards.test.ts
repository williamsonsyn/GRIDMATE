import { describe, expect, it } from 'vitest';
import type { DispatchPoint } from '../types/api';

describe('HourlyPowerCards calculations', () => {
  const current: DispatchPoint = {
    timestamp: '2026-11-10T14:00:00',
    solar_kw: 320.0,
    wind_kw: 110.0,
    hydro_kw: 210.0,
    battery_kw: 60.0, // discharging
    grid_kw: 100.0,
    load_kw: 800.0,
    curtailment_kw: 0.0,
    battery_soc_kwh: 350.0,
  };

  const prev: DispatchPoint = {
    timestamp: '2026-11-10T13:00:00',
    solar_kw: 350.0,
    wind_kw: 90.0,
    hydro_kw: 210.0,
    battery_kw: -40.0, // charging
    grid_kw: 190.0,
    load_kw: 800.0,
    curtailment_kw: 0.0,
    battery_soc_kwh: 320.0,
  };

  it('calculates demand shares correctly', () => {
    const solarShare = (current.solar_kw / current.load_kw) * 100;
    const windShare = (current.wind_kw / current.load_kw) * 100;
    const hydroShare = (current.hydro_kw / current.load_kw) * 100;
    const gridShare = (current.grid_kw / current.load_kw) * 100;

    expect(solarShare).toBeCloseTo(40.0);
    expect(windShare).toBeCloseTo(13.75);
    expect(hydroShare).toBeCloseTo(26.25);
    expect(gridShare).toBeCloseTo(12.5);
  });

  it('identifies battery discharging vs charging', () => {
    expect(current.battery_kw > 0.05).toBe(true);
    expect(prev.battery_kw < -0.05).toBe(true);

    const dischargePower = Math.abs(current.battery_kw);
    expect(dischargePower).toBe(60.0);

    const chargePower = Math.abs(prev.battery_kw);
    expect(chargePower).toBe(40.0);
  });

  it('computes hour-over-hour deltas correctly', () => {
    const solarDelta = current.solar_kw - prev.solar_kw;
    const windDelta = current.wind_kw - prev.wind_kw;
    const hydroDelta = current.hydro_kw - prev.hydro_kw;
    const gridDelta = current.grid_kw - prev.grid_kw;

    expect(solarDelta).toBe(-30.0);
    expect(windDelta).toBe(20.0);
    expect(hydroDelta).toBe(0.0);
    expect(gridDelta).toBe(-90.0);
  });
});

