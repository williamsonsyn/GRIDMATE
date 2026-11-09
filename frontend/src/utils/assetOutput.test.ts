import { describe, expect, it } from 'vitest';
import type { AssetProps, DispatchPoint, GeoCollection } from '../types/api';
import { computeAssetStates } from './assetOutput';

const mk = (id: string, type: AssetProps['type'], cap: number) => ({
  type: 'Feature' as const,
  geometry: { type: 'Point', coordinates: [0, 0] },
  properties: { id, type, name: id, capacity_kw: cap },
});

const assets: GeoCollection<AssetProps> = {
  type: 'FeatureCollection',
  features: [mk('s1', 'solar', 300), mk('s2', 'solar', 100), mk('b1', 'battery', 250), mk('g1', 'grid', 1500)],
};

const point: DispatchPoint = {
  timestamp: '2026-01-01T12:00:00', solar_kw: 200, wind_kw: 0, hydro_kw: 0,
  battery_kw: -80, grid_kw: 0, load_kw: 500, curtailment_kw: 0, battery_soc_kwh: 300,
};

describe('computeAssetStates', () => {
  it('splits a source total by installed capacity', () => {
    const s = computeAssetStates(assets, point);
    expect(s.s1.outputKw).toBeCloseTo(150);
    expect(s.s2.outputKw).toBeCloseTo(50);
    expect(s.s1.outputKw + s.s2.outputKw).toBeCloseTo(point.solar_kw);
  });
  it('maps battery sign convention (negative = charging)', () => {
    const s = computeAssetStates(assets, point);
    expect(s.b1.status).toBe('charging');
    expect(s.b1.outputKw).toBe(80);
  });
  it('marks an unused grid intertie as idle', () => {
    expect(computeAssetStates(assets, point).g1.status).toBe('idle');
  });
});
