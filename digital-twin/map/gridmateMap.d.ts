/**
 * gridmateMap.d.ts
 * TypeScript type declarations for the GridMate Lonavala Digital Twin map module.
 * Consumed by Member 4 (React / TypeScript + FastAPI integration).
 *
 * Battery sign convention: battery_kw > 0 = discharging (supplying load),
 *                          battery_kw < 0 = charging (consuming from grid/RE surplus).
 */

// ── Dispatch contract ─────────────────────────────────────────────────────────

/** A single hourly dispatch row (Member 2 output format). */
export interface DispatchRow {
  timestamp: string;        // ISO-8601 or HH:MM
  solar_kw: number;         // >= 0
  wind_kw: number;          // >= 0
  hydro_kw: number;         // >= 0
  /** > 0 = discharging (supply), < 0 = charging (load), 0 = idle */
  battery_kw: number;
  grid_kw: number;          // >= 0 (import)
  load_kw: number;          // > 0
  curtailment_kw: number;   // >= 0
  battery_soc_kwh: number;  // 0 .. battery capacity_kwh (1000 kWh for BESS-01)
}

/** Contract-form dispatch file (as produced by Member 2). */
export interface DispatchContract {
  location: string;
  scenario_id?: string;
  scenario_name?: string;
  description?: string;
  battery_convention?: string;
  dispatch: DispatchRow[];
  metrics?: Record<string, number | string>;
  [key: string]: unknown;
}

// ── Asset GeoJSON types ───────────────────────────────────────────────────────

export type AssetType = 'solar' | 'wind' | 'hydro' | 'battery' | 'grid' | 'demand';

export type AssetStatus =
  | 'active'
  | 'idle'
  | 'charging'
  | 'discharging'
  | 'not_supplying';

export type LocationSource =
  | 'osm'
  | 'osm_dam_nearest'
  | 'osm_nearest_substation'
  | 'synthetic_demo_site'
  | string;

export interface AssetProperties {
  id: string;
  type: AssetType;
  name: string;
  capacity_kw: number;
  capacity_kwh?: number;      // Battery only: energy storage capacity
  status: AssetStatus;
  is_synthetic: boolean;
  data_source: string;
  location_source: LocationSource;
  note?: string;
  forecast_output_kw?: number;
  utilization_percent?: number;
  scenario?: string;
  battery_soc_kwh?: number;
  [key: string]: unknown;
}

export interface AssetFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] }; // [longitude, latitude]
  properties: AssetProperties;
}

export interface AssetFeatureCollection {
  type: 'FeatureCollection';
  features: AssetFeature[];
}

// ── Computed metrics ──────────────────────────────────────────────────────────

/**
 * Metrics returned by computeMetrics(). All percentages are 0–100.
 *
 * Renewable penetration = (solar + wind + hydro + battery_discharge) / load × 100
 *   Battery discharge is counted as renewable because stored RE is assumed.
 *   Grid import is NOT counted as renewable.
 *
 * Grid dependency = grid_kw / load × 100
 */
export interface Metrics {
  loadKw: number;
  solarKw: number;
  windKw: number;
  hydroKw: number;
  gridKw: number;
  batteryKw: number;
  rePct: number;
  gridPct: number;
  genTotal: number;
  batteryMode: string;
  batterySocKwh?: number;
}

// ── Init options ──────────────────────────────────────────────────────────────

export interface GridMateMapOptions {
  /**
   * Base URL prefix for all data/config fetches.
   * When consumed from a React app: pass the path to the digital-twin folder,
   * e.g. '/digital-twin/' or import.meta.env.VITE_TWIN_BASE_URL.
   * Defaults to '' (same-origin relative paths, works when served from digital-twin/).
   */
  basePath?: string;
  /** MapLibre GL JS instance. Required in bundled environments; falls back to window.maplibregl. */
  maplibregl?: object;
  /** Initial basemap: 'streets' | 'satellite' | 'plain_dark'. Default 'streets'. */
  basemap?: 'streets' | 'satellite' | 'plain_dark';
}

// ── Controller class ──────────────────────────────────────────────────────────

export declare class GridMateMapController {
  constructor(containerId: string | HTMLElement, options?: GridMateMapOptions);
  setDispatch(dispatchJson: DispatchContract | DispatchRow, indexOrTimestamp?: number | string): AssetFeatureCollection;
  setScenario(id: 'normal' | 'cloudy' | 'heavy_monsoon' | 'high_wind' | 'peak_demand' | 'sample_dispatch'): Promise<void>;
  setBasemap(mode: 'streets' | 'satellite' | 'plain_dark'): void;
  setLayerVisibility(layerId: string, visible: boolean): void;
  flyToAsset(id: string): AssetFeature | null;
  zoomToAssets(): void;
  zoomToRegion(): void;
  getAssets(): AssetFeatureCollection | null;
  setTerrain(enabled: boolean): void;
  destroy(): void;
}

// ── Module-level function exports ─────────────────────────────────────────────

/**
 * Initialises the map into the given container.
 * Safe to call, destroy, and call again (React StrictMode double-mount).
 * @param containerId  DOM element id string or HTMLElement.
 * @param options      Configuration options.
 * @returns            Resolves with the controller once the map is loaded.
 */
export declare function init(
  containerId: string | HTMLElement,
  options?: GridMateMapOptions
): Promise<GridMateMapController>;

export declare function setDispatch(
  dispatchJson: DispatchContract | DispatchRow,
  indexOrTimestamp?: number | string
): AssetFeatureCollection;

export declare function setScenario(
  id: 'normal' | 'cloudy' | 'heavy_monsoon' | 'high_wind' | 'peak_demand' | 'sample_dispatch'
): Promise<void>;

export declare function setBasemap(mode: 'streets' | 'satellite' | 'plain_dark'): void;

export declare function setLayerVisibility(layerId: string, visible: boolean): void;

export declare function flyToAsset(id: string): AssetFeature | null;

export declare function zoomToAssets(): void;

export declare function zoomToRegion(): void;

export declare function getAssets(): AssetFeatureCollection | null;

export declare function setTerrain(enabled: boolean): void;

export declare function destroy(): void;

// ── Pure helper exports ───────────────────────────────────────────────────────

export declare function normalizeDispatch(
  input: DispatchContract | DispatchRow,
  indexOrTimestamp?: number | string
): DispatchRow;

export declare function applyDispatchToAssets(
  assetsGeoJSON: AssetFeatureCollection,
  row: DispatchRow
): AssetFeatureCollection;

export declare function buildEnergyFlowData(
  dispatchInput: DispatchContract | DispatchRow,
  assetsGeoJSON: AssetFeatureCollection,
  timestampOrIndex?: number | string
): { type: 'FeatureCollection'; features: object[] };

export declare function distributeDemandLoadData(
  demandZonesGeoJSON: object,
  totalLoadKw: number
): object;

export declare function computeMetrics(row: DispatchRow): Metrics;

export declare function formatTimeLabel(ts: string | number): string;

export declare function createAssetPopupHTML(
  props: Partial<AssetProperties>,
  timeStr: string,
  scenarioLabel: string
): string;

export declare function setDispatchEngine(engine: object): void;
export declare function getDispatchEngine(): object | null;

