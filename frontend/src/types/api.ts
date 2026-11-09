// Types mirroring backend/models/schemas.py. No `any` anywhere.

export type ScenarioId = 'normal' | 'cloudy' | 'heavy_monsoon' | 'high_wind' | 'peak_demand';
export type AssetType = 'solar' | 'wind' | 'hydro' | 'battery' | 'grid' | 'demand';

export interface Meta {
  scenario: ScenarioId;
  label: string;
  forecast_source: 'model' | 'mock';
  optimization_source: 'pypsa' | 'mock' | null;
  generated_at: string;
  warnings: string[];
  date?: string | null;
  note?: string | null;
}

export interface ForecastPoint {
  timestamp: string;
  solar_kw: number;
  wind_kw: number;
  hydro_kw: number;
  load_kw: number;
}

export interface DispatchPoint {
  timestamp: string;
  solar_kw: number;
  wind_kw: number;
  hydro_kw: number;
  /** > 0 discharging, < 0 charging */
  battery_kw: number;
  grid_kw: number;
  load_kw: number;
  curtailment_kw: number;
  battery_soc_kwh: number;
}

export interface ForecastResponse {
  location: string;
  forecast_horizon_hours: number;
  forecast: ForecastPoint[];
  scenario: ScenarioId;
  meta: Meta;
  date?: string | null;
  note?: string | null;
}

export interface DispatchResponse {
  location: string;
  dispatch: DispatchPoint[];
  scenario: ScenarioId;
  meta: Meta;
}

export interface Metrics {
  renewable_penetration_percent: number;
  grid_dependency_percent: number;
  curtailment_percent: number;
  battery_utilization_percent: number;
  estimated_co2_avoided_kg: number;
}

export interface Totals {
  load_kwh: number;
  renewable_generation_kwh: number;
  grid_import_kwh: number;
  curtailed_kwh: number;
  battery_charged_kwh: number;
  battery_discharged_kwh: number;
}

export interface SystemInfo {
  battery_capacity_kwh: number;
  battery_max_charge_kw: number;
  battery_max_discharge_kw: number;
  battery_min_soc_kwh: number;
  grid_capacity_kw: number;
}

export interface MetricsResponse {
  scenario: ScenarioId;
  metrics: Metrics;
  totals: Totals;
  system: SystemInfo;
  cost: Record<string, number | string> | null;
  meta: Meta;
}

export interface ScenarioInfo {
  id: ScenarioId;
  label: string;
  description: string;
}

/** Shape of cost figures returned by the backend /api/metrics .cost field. */
export interface CostMetrics {
  total_grid_cost_rs: number;
  grid_only_cost_rs: number;
  baseline_cost_rs: number;
  savings_rs: number;
  savings_percent: number;
  average_cost_rs_per_kwh_served: number;
  grid_only_average_cost_rs_per_kwh: number;
  label: string;
}

export interface ScenarioSummaryRow {
  scenario: ScenarioId;
  label: string;
  renewable_penetration_percent: number;
  grid_dependency_percent: number;
  curtailment_percent: number;
  battery_utilization_percent: number;
  estimated_co2_avoided_kg: number;
  total_grid_cost_rs: number;
  grid_only_cost_rs: number;
  savings_rs: number;
  savings_percent: number;
}

export interface ScenarioSummaryResponse {
  rows: ScenarioSummaryRow[];
}

export interface OptimizeResponse {
  scenario: ScenarioId;
  forecast: ForecastResponse;
  dispatch: DispatchResponse;
  metrics: MetricsResponse;
  timings_ms: { forecast: number; optimization: number };
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  mode: string;
  components: Record<string, boolean>;
  detail: Record<string, string>;
}

// ---- GeoJSON (Member 3 digital twin) ----
export interface GeoFeature<P> {
  type: 'Feature';
  geometry: { type: string; coordinates: unknown };
  properties: P;
}
export interface GeoCollection<P> {
  type: 'FeatureCollection';
  features: GeoFeature<P>[];
}

export interface AssetProps {
  id: string;
  type: AssetType;
  name: string;
  capacity_kw: number;
  status?: string;
  is_synthetic?: boolean;
  note?: string;
  location_source?: string;
}
export interface ZoneProps {
  id: string;
  name: string;
  zone_type?: string;
  base_load_kw: number;
  note?: string;
}
export interface FlowProps {
  id: string;
  source_id: string;
  source_type: AssetType;
  source_name: string;
  target_id: string;
}
export type LooseProps = Record<string, unknown>;

export interface Basemap {
  name: string;
  tiles: string[];
  tileSize?: number;
  maxzoom?: number;
  attribution?: string;
}
export interface MapConfig {
  center: [number, number];
  zoom: number;
  basemaps?: Record<string, Basemap>;
  asset_colors?: Partial<Record<AssetType, string>>;
}

export interface AssetsResponse {
  assets: GeoCollection<AssetProps>;
  demand_zones: GeoCollection<ZoneProps>;
  water_features: GeoCollection<LooseProps>;
  power_lines: GeoCollection<LooseProps>;
  energy_flow: GeoCollection<FlowProps>;
  map_config: MapConfig;
  source: 'digital_twin' | 'mock';
  label: string;
}
