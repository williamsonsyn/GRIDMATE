import { describe, expect, it } from 'vitest';
import type { AssetProps } from '../types/api';
import type { AssetState } from '../utils/assetOutput';
import { popupHtml } from './MapPanel';

describe('MapPanel Asset Popup', () => {
  it('renders Wind Turbine Cluster 03 with wrapping and overflow containment', () => {
    const windAsset: AssetProps = {
      id: 'wind_03',
      type: 'wind',
      name: 'Wind Turbine Cluster 03 - Upper Central Ridge (Simulated)',
      capacity_kw: 100.0,
      status: 'active',
      is_synthetic: true,
      data_source: 'synthetic_demo',
      location_source: 'osm',
      note: 'Simulated prototype asset. Sited at real OSM wind turbine node/2925720173 (cluster of 8 turbines). Coordinates are illustrative, not surveyed infrastructure.',
    };
    const state: AssetState = {
      outputKw: 45.2,
      status: 'generating',
    };

    const html = popupHtml(windAsset, state, '14:00', 'Normal Day');

    // Box sizing and scrollable containment
    expect(html).toContain('box-sizing:border-box');
    expect(html).toContain('max-height:230px');
    expect(html).toContain('overflow-y:auto');
    expect(html).toContain('width:275px');

    // Title wrapping and badge
    expect(html).toContain('word-break:break-word');
    expect(html).toContain('overflow-wrap:break-word');
    expect(html).toContain('Wind Turbine Cluster 03 - Upper Central Ridge (Simulated)');
    expect(html).toContain('wind');

    // Rows use flex with min-width: 0
    expect(html).toContain('min-width:0');
    expect(html).toContain('45 kW');
    expect(html).toContain('GENERATING');
    expect(html).toContain('Real OSM site');

    // Note is wrapped and contained
    expect(html).toContain('Simulated prototype asset. Capacity and output are illustrative, not measured.');
  });

  it('renders Solar Farm 01 with proper capacity and output format', () => {
    const solarAsset: AssetProps = {
      id: 'solar_01',
      type: 'solar',
      name: 'Solar Farm 01 - Campole Valley (Simulated)',
      capacity_kw: 350.0,
      status: 'active',
      is_synthetic: true,
      data_source: 'synthetic_demo',
      location_source: 'osm',
    };
    const state: AssetState = {
      outputKw: 310.5,
      status: 'generating',
    };

    const html = popupHtml(solarAsset, state, '12:00', 'Cloudy Day');

    expect(html).toContain('Solar Farm 01 - Campole Valley (Simulated)');
    expect(html).toContain('solar');
    expect(html).toContain('350 kW');
    expect(html).toContain('311 kW');
    expect(html).toContain('Cloudy Day');
  });

  it('renders Battery Storage with charging / discharging status', () => {
    const batteryAsset: AssetProps = {
      id: 'battery_01',
      type: 'battery',
      name: 'BESS Central Substation (Simulated)',
      capacity_kw: 500.0,
      status: 'active',
      is_synthetic: true,
    };
    const state: AssetState = {
      outputKw: 120.0,
      status: 'charging',
    };

    const html = popupHtml(batteryAsset, state, '02:00', 'Heavy Monsoon');

    expect(html).toContain('BESS Central Substation (Simulated)');
    expect(html).toContain('battery');
    expect(html).toContain('CHARGING');
    expect(html).toContain('120 kW');
    expect(html).toContain('Heavy Monsoon');
  });
});
