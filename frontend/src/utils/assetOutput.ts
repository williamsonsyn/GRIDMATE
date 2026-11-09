import type {
  AssetProps, AssetType, DispatchPoint, FlowProps, GeoCollection, GeoFeature, ZoneProps,
} from '../types/api';

export type AssetStatus = 'generating' | 'charging' | 'discharging' | 'importing' | 'serving' | 'idle';

export interface AssetState {
  outputKw: number;
  status: AssetStatus;
}

const GENERATORS: AssetType[] = ['solar', 'wind', 'hydro'];
const EPS = 0.05;

function generated(point: DispatchPoint, type: AssetType): number {
  if (type === 'solar') return point.solar_kw;
  if (type === 'wind') return point.wind_kw;
  return point.hydro_kw;
}

/**
 * Distribute the dispatched total of each source type across its individual
 * assets in proportion to installed capacity. Battery/grid/demand map directly.
 */
export function computeAssetStates(
  assets: GeoCollection<AssetProps>,
  point: DispatchPoint,
): Record<string, AssetState> {
  const capByType: Partial<Record<AssetType, number>> = {};
  for (const f of assets.features) {
    const t = f.properties.type;
    capByType[t] = (capByType[t] ?? 0) + f.properties.capacity_kw;
  }
  const out: Record<string, AssetState> = {};
  for (const f of assets.features) {
    const { id, type, capacity_kw } = f.properties;
    if (GENERATORS.includes(type)) {
      const total = capByType[type] ?? 0;
      const kw = total > 0 ? (generated(point, type) * capacity_kw) / total : 0;
      out[id] = { outputKw: kw, status: kw > EPS ? 'generating' : 'idle' };
    } else if (type === 'battery') {
      const kw = point.battery_kw;
      out[id] = {
        outputKw: Math.abs(kw),
        status: kw > EPS ? 'discharging' : kw < -EPS ? 'charging' : 'idle',
      };
    } else if (type === 'grid') {
      out[id] = { outputKw: point.grid_kw, status: point.grid_kw > EPS ? 'importing' : 'idle' };
    } else {
      out[id] = { outputKw: point.load_kw, status: 'serving' };
    }
  }
  return out;
}

/** Split the system load across demand zones by their base-load share. */
export function computeZoneLoads(
  zones: GeoCollection<ZoneProps>,
  point: DispatchPoint,
): Record<string, number> {
  const total = zones.features.reduce((s, f) => s + f.properties.base_load_kw, 0);
  const out: Record<string, number> = {};
  for (const f of zones.features) {
    out[f.properties.id] = total > 0 ? (point.load_kw * f.properties.base_load_kw) / total : 0;
  }
  return out;
}

export interface FlowState {
  flowKw: number;
  /** battery charging flows towards the battery */
  towardsAsset: boolean;
}

export function computeFlows(
  flows: GeoFeature<FlowProps>[],
  states: Record<string, AssetState>,
): Record<string, FlowState> {
  const out: Record<string, FlowState> = {};
  for (const f of flows) {
    const s = states[f.properties.source_id];
    out[f.properties.id] = {
      flowKw: s ? s.outputKw : 0,
      towardsAsset: s?.status === 'charging',
    };
  }
  return out;
}
