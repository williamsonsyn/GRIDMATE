/**
 * gridmateMap.js
 * Framework-agnostic MapLibre GL JS integration module for GridMate Lonavala Digital Twin.
 * Can be consumed in vanilla JS (map/index.html) or React / TypeScript without any Python dependency.
 *
 * Exports:
 * - init(containerId, options): Promise<GridMateMapController>
 * - setDispatch(dispatchJson, indexOrTimestamp)
 * - setScenario(id)
 * - setBasemap(mode)
 * - setLayerVisibility(layerId, bool)
 * - flyToAsset(id)
 * - zoomToAssets()
 * - zoomToRegion()
 * - getAssets()
 * - destroy()
 * - setTerrain(bool)
 * - Pure helpers: normalizeDispatch, applyDispatchToAssets, buildEnergyFlowData, distributeDemandLoadData, computeMetrics, formatTimeLabel, createAssetPopupHTML
 */

// Load applyDispatch engine if available in environment
let dispatchEngine = (typeof window !== 'undefined' && window.GridMateDispatch) ||
                     (typeof globalThis !== 'undefined' && globalThis.GridMateDispatch) || null;

if (!dispatchEngine && typeof process !== 'undefined') {
  try {
    const mod = await import('./applyDispatch.js');
    dispatchEngine = mod.default || mod;
  } catch (e) {
    // Fallback logic implemented below
  }
}

export function setDispatchEngine(engine) {
  dispatchEngine = engine;
}

export function getDispatchEngine() {
  return dispatchEngine || (typeof window !== 'undefined' ? window.GridMateDispatch : (typeof globalThis !== 'undefined' ? globalThis.GridMateDispatch : null));
}

// ==========================================
// Constants & Color Scales
// ==========================================

export const ASSET_TYPE_COLORS = {
  solar: '#f59e0b',
  wind: '#06b6d4',
  hydro: '#3b82f6',
  battery: '#10b981',
  grid: '#ef4444',
  demand: '#8b5cf6'
};

export const STATUS_COLORS = {
  active: '#10b981',
  discharging: '#10b981',
  charging: '#0284c7',
  idle: '#94a3b8',
  not_supplying: '#64748b'
};

export const DOT_COLORS = {
  solar: '#fef08a',
  wind: '#a5f3fc',
  hydro: '#93c5fd',
  battery: '#6ee7b7',
  grid: '#fca5a5'
};

export const CONTEXT_BBOX = [73.25, 18.62, 73.62, 18.92];
export const ASSET_BBOX = [73.33, 18.70, 73.61, 18.91];

export const SCENARIO_IDS = ['normal', 'cloudy', 'heavy_monsoon', 'high_wind', 'peak_demand'];

// ==========================================
// Pure Helper Functions (Node & Browser)
// ==========================================

/**
 * Normalizes dispatch input to a single dispatch row object.
 * Accepts BOTH the contract form {location, scenario_id, dispatch: [...], metrics}
 * and the flat single-object form {timestamp, solar_kw, ...}.
 */
export function normalizeDispatch(dispatchInput, timestampOrIndex) {
  const engine = getDispatchEngine();
  if (engine && typeof engine.parseDispatchRow === 'function') {
    return engine.parseDispatchRow(dispatchInput, timestampOrIndex);
  }

  if (!dispatchInput) return {};
  if (Array.isArray(dispatchInput.dispatch) && dispatchInput.dispatch.length > 0) {
    if (typeof timestampOrIndex === 'string') {
      const found = dispatchInput.dispatch.find(r => String(r.timestamp) === timestampOrIndex);
      if (found) return Object.assign({}, found, { scenario_id: dispatchInput.scenario_id });
    }
    let idx = (typeof timestampOrIndex === 'number') ? timestampOrIndex : 0;
    idx = Math.max(0, Math.min(idx, dispatchInput.dispatch.length - 1));
    return Object.assign({}, dispatchInput.dispatch[idx], { scenario_id: dispatchInput.scenario_id });
  }
  return Object.assign({}, dispatchInput);
}

/**
 * Applies dispatch row or contract JSON to assets GeoJSON.
 */
export function applyDispatchToAssets(assetsGeoJSON, dispatchInput, timestampOrIndex, scenarioId) {
  const row = normalizeDispatch(dispatchInput, timestampOrIndex);
  const effectiveScenario = scenarioId || (dispatchInput && dispatchInput.scenario_id) || row.scenario_id || 'Simulated Scenario';

  const engine = getDispatchEngine();
  if (engine && typeof engine.applyDispatch === 'function') {
    return engine.applyDispatch(assetsGeoJSON, row, effectiveScenario);
  }

  // Standalone fallback identical to applyDispatch.js
  const assetsFc = JSON.parse(JSON.stringify(assetsGeoJSON));
  const solarTotal = Math.max(0, Number(row.solar_kw) || 0);
  const windTotal = Math.max(0, Number(row.wind_kw) || 0);
  const hydroTotal = Math.max(0, Number(row.hydro_kw) || 0);
  const gridTotal = Math.max(0, Number(row.grid_kw) || 0);
  const loadTotal = Math.max(0, Number(row.load_kw) || 0);
  const batteryVal = Number(row.battery_kw) || 0;
  const batterySoc = row.battery_soc_kwh;

  const typeCapacities = {};
  (assetsFc.features || []).forEach(f => {
    const p = f.properties || {};
    const t = p.type;
    const cap = Number(p.capacity_kw) || 0;
    if (t) typeCapacities[t] = (typeCapacities[t] || 0) + cap;
  });

  assetsFc.features = (assetsFc.features || []).map(feature => {
    const f = JSON.parse(JSON.stringify(feature));
    const p = f.properties || {};
    const t = p.type;
    const cap = Number(p.capacity_kw) || 0;
    const totCap = typeCapacities[t] || 0;
    const ratio = totCap > 0 ? (cap / totCap) : 0;

    let forecastOutput = 0;
    let status = 'idle';

    if (t === 'solar') {
      forecastOutput = +(solarTotal * ratio).toFixed(2);
      status = forecastOutput > 0 ? 'active' : 'idle';
    } else if (t === 'wind') {
      forecastOutput = +(windTotal * ratio).toFixed(2);
      status = forecastOutput > 0 ? 'active' : 'idle';
    } else if (t === 'hydro') {
      forecastOutput = +(hydroTotal * ratio).toFixed(2);
      status = forecastOutput > 0 ? 'active' : 'idle';
    } else if (t === 'grid') {
      forecastOutput = +(gridTotal * ratio).toFixed(2);
      status = forecastOutput > 0 ? 'active' : 'not_supplying';
    } else if (t === 'battery') {
      forecastOutput = +(Math.abs(batteryVal) * ratio).toFixed(2);
      if (batteryVal > 0) status = 'discharging';
      else if (batteryVal < 0) status = 'charging';
      else status = 'idle';
      if (batterySoc !== undefined && batterySoc !== null) {
        p.battery_soc_kwh = Number(batterySoc);
      }
    } else if (t === 'demand') {
      forecastOutput = +(loadTotal * ratio).toFixed(2);
      status = 'active';
    }

    const utilization = cap > 0 ? +((forecastOutput / cap) * 100).toFixed(1) : 0;
    forecastOutput = Math.max(0, forecastOutput);

    p.forecast_output_kw = forecastOutput;
    p.status = status;
    p.scenario = effectiveScenario;
    p.utilization_percent = utilization;
    f.properties = p;
    return f;
  });

  return assetsFc;
}

/**
 * Builds dynamic energy flow lines GeoJSON from dispatch row and assets GeoJSON.
 */
export function buildEnergyFlowData(dispatchInput, assetsGeoJSON, timestampOrIndex) {
  const row = normalizeDispatch(dispatchInput, timestampOrIndex);
  const engine = getDispatchEngine();
  if (engine && typeof engine.buildEnergyFlow === 'function') {
    return engine.buildEnergyFlow(row, assetsGeoJSON);
  }

  const appliedAssets = applyDispatchToAssets(assetsGeoJSON, row);
  let demandHub = null;
  const supplyAssets = [];

  (appliedAssets.features || []).forEach(f => {
    if ((f.properties || {}).type === 'demand') demandHub = f;
    else supplyAssets.push(f);
  });

  if (!demandHub) return { type: 'FeatureCollection', features: [] };

  const hubCoords = demandHub.geometry.coordinates;
  const flowFeatures = [];

  supplyAssets.forEach(src => {
    const p = src.properties || {};
    const srcCoords = src.geometry.coordinates;
    let outputKw = Number(p.forecast_output_kw) || 0;
    const status = p.status || 'idle';

    let direction = 'to_demand';
    let coords = [srcCoords, hubCoords];

    if (p.type === 'battery') {
      if (status === 'charging') {
        direction = 'to_battery';
        coords = [hubCoords, srcCoords];
      } else if (status === 'idle') {
        outputKw = 0;
      }
    } else if (p.type === 'grid') {
      if (status === 'not_supplying') {
        outputKw = 0;
      }
    }

    const flowActive = outputKw > 0;
    const lineWeight = Math.max(1.5, Math.min(8.0, 1.5 + (outputKw / 100.0)));

    flowFeatures.push({
      type: 'Feature',
      properties: {
        id: 'flow_' + p.id + '_to_demand',
        source_id: p.id,
        source_type: p.type,
        source_name: p.name,
        target_id: demandHub.properties.id,
        flow_kw: +outputKw.toFixed(2),
        status: flowActive ? 'active' : 'idle',
        direction: direction,
        line_weight: +lineWeight.toFixed(2),
        is_synthetic: true,
        note: 'Simulated dynamic energy flow'
      },
      geometry: {
        type: 'LineString',
        coordinates: coords
      }
    });
  });

  return {
    type: 'FeatureCollection',
    name: 'GridMate_Dynamic_Energy_Flow',
    features: flowFeatures
  };
}

/**
 * Distributes total load across demand zones proportionally to base_load_kw.
 */
export function distributeDemandLoadData(demandZonesGeoJSON, totalLoadKw) {
  const engine = getDispatchEngine();
  if (engine && typeof engine.distributeDemandLoad === 'function') {
    return engine.distributeDemandLoad(demandZonesGeoJSON, totalLoadKw);
  }

  const zonesFc = JSON.parse(JSON.stringify(demandZonesGeoJSON));
  const loadVal = Math.max(0, Number(totalLoadKw) || 0);

  let totalBaseLoad = 0;
  (zonesFc.features || []).forEach(f => {
    totalBaseLoad += Number((f.properties || {}).base_load_kw) || 0;
  });

  zonesFc.features = (zonesFc.features || []).map(feature => {
    const f = JSON.parse(JSON.stringify(feature));
    const p = f.properties || {};
    const baseLoad = Number(p.base_load_kw) || 0;
    const ratio = totalBaseLoad > 0 ? (baseLoad / totalBaseLoad) : 0;
    const zoneLoad = +(loadVal * ratio).toFixed(2);
    const sharePct = +(ratio * 100).toFixed(1);

    p.load_kw = Math.max(0, zoneLoad);
    p.load_share_pct = sharePct;
    p.label = 'illustrative zone';
    f.properties = p;
    return f;
  });

  return zonesFc;
}

/**
 * Computes high-level system metrics from a dispatch row.
 */
export function computeMetrics(row) {
  const loadKw = Number(row.load_kw) || 0;
  const solarKw = Number(row.solar_kw) || 0;
  const windKw = Number(row.wind_kw) || 0;
  const hydroKw = Number(row.hydro_kw) || 0;
  const gridKw = Number(row.grid_kw) || 0;
  const batKw = Number(row.battery_kw) || 0;
  const batDischarge = batKw > 0 ? batKw : 0;

  const reGen = solarKw + windKw + hydroKw + batDischarge;
  const rePct = loadKw > 0 ? Math.min(100, Math.max(0, (reGen / loadKw) * 100)) : 100;
  const gridPct = loadKw > 0 ? Math.min(100, Math.max(0, (gridKw / loadKw) * 100)) : 0;
  const genTotal = solarKw + windKw + hydroKw + gridKw + batDischarge;

  let batteryMode = 'Idle (0 kW)';
  if (batKw > 0) batteryMode = `Discharging (${batKw} kW)`;
  else if (batKw < 0) batteryMode = `Charging (${Math.abs(batKw)} kW)`;

  return {
    loadKw,
    solarKw,
    windKw,
    hydroKw,
    gridKw,
    batteryKw: batKw,
    rePct,
    gridPct,
    genTotal,
    batteryMode,
    batterySocKwh: row.battery_soc_kwh
  };
}

/**
 * Formats ISO timestamp to HH:MM.
 */
export function formatTimeLabel(ts) {
  if (!ts) return "00:00";
  if (typeof ts === 'string' && ts.includes('T')) {
    const timePart = ts.split('T')[1];
    return timePart.substring(0, 5);
  }
  return String(ts);
}

/**
 * Injects scoped popup styling prefixed with .gm- into the DOM once.
 */
function injectPopupStyles() {
  if (typeof document === 'undefined') return;
  if (document.getElementById('gm-popup-styles')) return;

  const style = document.createElement('style');
  style.id = 'gm-popup-styles';
  style.textContent = `
    .maplibregl-popup-content {
      background: #0f172a !important;
      color: #f8fafc !important;
      border: 1px solid #334155 !important;
      border-radius: 10px !important;
      padding: 14px 16px !important;
      font-size: 0.85rem !important;
      box-shadow: 0 10px 25px rgba(0,0,0,0.6) !important;
      max-width: 320px !important;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }
    .maplibregl-popup-close-button {
      color: #94a3b8 !important;
      padding: 4px 8px !important;
    }
    .gm-popup-title {
      font-weight: 700;
      font-size: 0.95rem;
      margin-bottom: 8px;
      color: #ffffff;
      border-bottom: 1px solid #334155;
      padding-bottom: 6px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      flex-wrap: wrap;
    }
    .gm-popup-sim-tag {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      background: #dc2626;
      color: #ffffff;
      padding: 2px 7px;
      border-radius: 9999px;
      box-shadow: 0 0 6px rgba(220, 38, 38, 0.4);
    }
    .gm-popup-illustrative-tag {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      background: #7c3aed;
      color: #ffffff;
      padding: 2px 7px;
      border-radius: 9999px;
    }
    .gm-popup-row {
      display: flex;
      justify-content: space-between;
      margin: 4px 0;
    }
    .gm-popup-label { color: #94a3b8; }
    .gm-popup-val { font-weight: 600; color: #f8fafc; }
    .gm-popup-util-container { margin: 6px 0; }
    .gm-popup-util-bar-track {
      width: 100%;
      height: 6px;
      background: #334155;
      border-radius: 3px;
      overflow: hidden;
      margin-top: 3px;
    }
    .gm-popup-util-bar-fill {
      height: 100%;
      background: #38bdf8;
      border-radius: 3px;
      transition: width 0.3s ease;
    }
    .gm-status-badge {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 9999px;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
    }
    .gm-status-active { background: #166534; color: #86efac; }
    .gm-status-discharging { background: #065f46; color: #6ee7b7; }
    .gm-status-charging { background: #075985; color: #7dd3fc; }
    .gm-status-idle { background: #334155; color: #cbd5e1; }
    .gm-status-not_supplying { background: #475569; color: #94a3b8; }
    .gm-popup-disclaimer {
      font-size: 0.68rem;
      color: #cbd5e1;
      background: rgba(220, 38, 38, 0.15);
      border-left: 3px solid #ef4444;
      padding: 5px 8px;
      margin-top: 8px;
      border-radius: 2px;
    }
  `;
  document.head.appendChild(style);
}

/**
 * Creates HTML string for asset popup with scoped gm- classes and legacy classes for styling parity.
 */
export function createAssetPopupHTML(p, timeStr, scenarioLabel) {
  const status = p.status || 'idle';
  const statusKey = status.toLowerCase().replace(/\s+/g, '_');
  const utilPct = Math.min(100, Math.max(0, Number(p.utilization_percent) || 0));

  let outputRow = '';
  if (p.type === 'demand') {
    outputRow = `<div class="gm-popup-row popup-row"><span class="gm-popup-label popup-label">Current Demand:</span><span class="gm-popup-val popup-val">${p.forecast_output_kw !== undefined ? p.forecast_output_kw : 0} kW</span></div>`;
  } else {
    outputRow = `<div class="gm-popup-row popup-row"><span class="gm-popup-label popup-label">Forecast Output:</span><span class="gm-popup-val popup-val">${p.forecast_output_kw !== undefined ? p.forecast_output_kw : 0} kW</span></div>`;
  }

  let batterySocRow = '';
  if (p.type === 'battery' && p.battery_soc_kwh !== undefined) {
    batterySocRow = `<div class="gm-popup-row popup-row"><span class="gm-popup-label popup-label">Battery SOC:</span><span class="gm-popup-val popup-val">${p.battery_soc_kwh} kWh</span></div>`;
  }

  const effectiveScenario = (scenarioLabel || p.scenario || 'Normal Day').replace(/_/g, ' ');

  return `
    <div class="gm-popup-title popup-title">
      <span>${p.name}</span>
      <span class="gm-popup-sim-tag popup-sim-tag">Simulated asset</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Type:</span>
      <span class="gm-popup-val popup-val" style="text-transform: capitalize;">${p.type}</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Capacity:</span>
      <span class="gm-popup-val popup-val">${p.capacity_kw} kW ${p.capacity_kwh ? `(${p.capacity_kwh} kWh)` : ''}</span>
    </div>
    ${outputRow}
    <div class="gm-popup-util-container popup-util-container">
      <div class="gm-popup-row popup-row" style="margin-bottom: 2px;">
        <span class="gm-popup-label popup-label">Utilization:</span>
        <span class="gm-popup-val popup-val">${utilPct.toFixed(1)}%</span>
      </div>
      <div class="gm-popup-util-bar-track popup-util-bar-track">
        <div class="gm-popup-util-bar-fill popup-util-bar-fill" style="width: ${utilPct}%;"></div>
      </div>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Status:</span>
      <span class="gm-status-badge status-badge gm-status-${statusKey} status-${statusKey}">${status}</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Scenario:</span>
      <span class="gm-popup-val popup-val" style="text-transform: capitalize;">${effectiveScenario}</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Timestamp:</span>
      <span class="gm-popup-val popup-val">${timeStr || '00:00'}</span>
    </div>
    ${batterySocRow}
    ${p.location_source ? `
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Location Source:</span>
      <span class="gm-popup-val popup-val" style="text-transform: capitalize;">${p.location_source.replace(/_/g, ' ')}</span>
    </div>` : ''}
    <div class="gm-popup-disclaimer popup-disclaimer">
      ${p.note || 'Simulated prototype asset. Coordinates are illustrative.'}
    </div>
  `;
}

/**
 * Creates HTML string for demand zone popup.
 */
export function createDemandZonePopupHTML(p, timeStr, totalLoad) {
  const isRealOsm = p.geometry_source === 'osm_landuse';
  const tagText = isRealOsm ? 'Real OSM Landuse' : 'illustrative zones (hand-defined polygons)';
  const tagBg = isRealOsm ? '#0284c7' : '#7c3aed';
  const disclaimerText = isRealOsm
    ? `Real OSM landuse polygon geometry (OSM ODbL). Base load ${p.base_load_kw} kW of 900 kW total is simulated.`
    : `illustrative zones (hand-defined polygons), not OSM-derived. Base load ${p.base_load_kw} kW of 900 kW total.`;

  return `
    <div class="gm-popup-title popup-title">
      <span>${p.name}</span>
      <span class="gm-popup-illustrative-tag popup-illustrative-tag" style="background:${tagBg};">${tagText}</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Zone Type:</span>
      <span class="gm-popup-val popup-val" style="text-transform: capitalize;">${p.zone_type}</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Base Load:</span>
      <span class="gm-popup-val popup-val">${p.base_load_kw} kW</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Current Load:</span>
      <span class="gm-popup-val popup-val" style="color:#38bdf8; font-weight:700;">${p.load_kw || p.base_load_kw} kW</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Share of Load:</span>
      <span class="gm-popup-val popup-val">${p.load_share_pct || (((p.base_load_kw || 0)/900)*100).toFixed(1)}%</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Total System Load:</span>
      <span class="gm-popup-val popup-val">${totalLoad || 900} kW</span>
    </div>
    <div class="gm-popup-row popup-row">
      <span class="gm-popup-label popup-label">Timestamp:</span>
      <span class="gm-popup-val popup-val">${timeStr || '00:00'}</span>
    </div>
    <div class="gm-popup-disclaimer popup-disclaimer">
      ${disclaimerText}
    </div>
  `;
}

// Module-level pointer to the currently active map controller instance
let activeMapController = null;

// ==========================================
// Controller Class & Factory
// ==========================================

export class GridMateMapController {
  constructor(containerId, options = {}) {
    this.containerId = containerId;
    this.options = options;
    this.basePath = options.basePath !== undefined ? options.basePath : '../';

    // MapLibre instance
    this.maplibregl = options.maplibregl || (typeof window !== 'undefined' ? window.maplibregl : null);
    if (!this.maplibregl) {
      throw new Error('MapLibre GL JS instance not found. Pass options.maplibregl or include window.maplibregl.');
    }

    this.map = null;
    this.config = null;
    this.rawAssets = null;
    this.rawWater = null;
    this.rawRoads = null;
    this.rawDemandZones = null;

    this.currentScenarioData = null;
    this.currentDispatchRow = null;
    this.currentAppliedAssets = null;
    this.currentFlowData = null;
    this.currentDemandData = null;
    this.currentBasemap = options.basemap || 'streets';
    this.isTerrainActive = Boolean(options.terrain);

    this.activePopup = null;
    this.activePopupAssetId = null;

    this.animFrameId = null;
    this.isDestroyed = false;
    this.onVisibilityChange = null;

    injectPopupStyles();
  }

  resolveUrl(subpath) {
    if (!this.basePath) return subpath;
    const base = this.basePath.endsWith('/') ? this.basePath : this.basePath + '/';
    // If subpath is 'data/...' and base ends with 'data/', avoid duplication
    if (subpath.startsWith('data/') && base.endsWith('data/')) {
      return base + subpath.substring(5);
    }
    return base + subpath;
  }

  async _fetchResource(subpath, isRequired = true, label = '') {
    const url = this.resolveUrl(subpath);
    const displayLabel = label || subpath;
    try {
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText || 'Not Found'}`);
      }
      const text = await res.text();
      if (!text || !text.trim()) {
        throw new Error(`File is empty (0 bytes)`);
      }
      return JSON.parse(text);
    } catch (err) {
      if (isRequired) {
        throw new Error(`Failed to load core file: ${displayLabel} (${err.message})`);
      } else {
        console.warn(`[GridMate] Optional layer '${displayLabel}' skipped (${err.message})`);
        return null;
      }
    }
  }

  _showVisibleError(message) {
    if (typeof document === 'undefined') return;
    const el = typeof this.containerId === 'string'
      ? document.getElementById(this.containerId)
      : this.containerId;
    if (el) {
      const safeMsg = (message || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
      el.innerHTML = `
        <div class="gridmate-error-overlay" style="display:flex; flex-direction:column; align-items:center; justify-content:center; width:100%; height:100%; background:#0f172a; color:#f8fafc; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding:24px; box-sizing:border-box; text-align:center; z-index:100;">
          <div style="max-width:540px; background:rgba(30,41,59,0.95); border:1px solid #ef4444; border-radius:12px; padding:28px 24px; box-shadow:0 10px 30px rgba(0,0,0,0.6);">
            <div style="font-size:2.2rem; margin-bottom:12px;">⚠️</div>
            <h2 style="color:#ef4444; font-size:1.25rem; font-weight:700; margin-bottom:12px;">Initialization Error</h2>
            <p style="color:#cbd5e1; font-size:0.95rem; line-height:1.5; margin-bottom:16px;">The map could not load because a required core data file failed to load or is invalid:</p>
            <div style="background:#090d16; border:1px solid #334155; border-radius:6px; padding:12px; font-family:monospace; font-size:0.85rem; color:#f87171; word-break:break-all;">
              ${safeMsg}
            </div>
            <p style="color:#94a3b8; font-size:0.8rem; margin-top:16px;">Check the server log or run data generation scripts in digital-twin/.</p>
          </div>
        </div>
      `;
    }
  }

  async _loadData() {
    // Determine configuration path
    let configData = null;
    let configErr = null;
    const configCandidates = [
      this.resolveUrl('map/map_config.json'),
      'map_config.json',
      this.resolveUrl('map_config.json')
    ];
    for (const cUrl of [...new Set(configCandidates)]) {
      try {
        const res = await fetch(cUrl);
        if (res.ok) {
          const text = await res.text();
          if (text && text.trim()) {
            configData = JSON.parse(text);
            break;
          }
        }
      } catch (e) {
        configErr = e;
      }
    }
    if (!configData) {
      throw new Error(`Failed to load core file: map_config.json (${configErr ? configErr.message : 'Not found or empty'})`);
    }

    this.config = configData;

    // Load core layers and optional layers
    const [assets, water, roads, demand, flowTemplate, power] = await Promise.all([
      this._fetchResource('data/assets.geojson', true, 'data/assets.geojson'),
      this._fetchResource('data/water_features.geojson', true, 'data/water_features.geojson'),
      this._fetchResource('data/roads.geojson', true, 'data/roads.geojson'),
      this._fetchResource('data/demand_zones.geojson', true, 'data/demand_zones.geojson'),
      this._fetchResource('data/energy_flow_template.geojson', true, 'data/energy_flow_template.geojson'),
      this._fetchResource('data/power_lines.geojson', false, 'data/power_lines.geojson')
    ]);

    this.rawAssets = assets;
    this.rawWater = water;
    this.rawRoads = roads;
    this.rawDemandZones = demand;
    this.rawEnergyFlowTemplate = flowTemplate;
    this.rawPowerLines = power;
  }

  _initMapInstance() {
    return new Promise((resolve, reject) => {
      try {
        const ctx = this.config.context_bbox || CONTEXT_BBOX;
        const contextBounds = [[ctx[0], ctx[1]], [ctx[2], ctx[3]]];
        const maxBounds = [
          [ctx[0] - 0.05, ctx[1] - 0.05],
          [ctx[2] + 0.05, ctx[3] + 0.05]
        ];

        const initialStyle = {
          version: 8,
          sources: {
            'osm-tiles': {
              type: 'raster',
              tiles: [
                'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png'
              ],
              tileSize: 256,
              maxzoom: 19
            },
            'satellite-tiles': {
              type: 'raster',
              tiles: [
                'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
              ],
              tileSize: 256,
              maxzoom: 19
            }
          },
          layers: [
            {
              id: 'background-fallback',
              type: 'background',
              paint: { 'background-color': '#0f172a' }
            },
            {
              id: 'satellite-tiles-layer',
              type: 'raster',
              source: 'satellite-tiles',
              layout: { 'visibility': this.currentBasemap === 'satellite' ? 'visible' : 'none' },
              minzoom: 0,
              maxzoom: 19
            },
            {
              id: 'osm-tiles-layer',
              type: 'raster',
              source: 'osm-tiles',
              layout: { 'visibility': this.currentBasemap === 'streets' ? 'visible' : 'none' },
              minzoom: 0,
              maxzoom: 19
            }
          ]
        };

        this.map = new this.maplibregl.Map({
          container: this.containerId,
          style: initialStyle,
          maxBounds: maxBounds,
          minZoom: 9.8,
          attributionControl: false
        });

        this.map.addControl(new this.maplibregl.NavigationControl(), 'bottom-right');

        this.map.on('load', () => {
          if (this.isDestroyed) return;
          this.map.resize();
          this.map.fitBounds(contextBounds, { padding: 40, duration: 0 });

          this._addVectorLayers();
          this._bindMapEvents();
          this._startAnimation();

          if (this.isTerrainActive) {
            this.setTerrain(true);
          }

          if (this.currentBasemap) {
            this.setBasemap(this.currentBasemap);
          }

          if (typeof this.options.onReady === 'function') {
            this.options.onReady(this);
          }

          resolve(this);
        });

        this.map.on('error', (e) => {
          const errObj = (e && e.error) || e;
          const errMsg = (errObj && errObj.message) || String(errObj || '');
          console.warn("[GridMate] Non-fatal MapLibre map warning:", errMsg, errObj);
        });
      } catch (err) {
        reject(err);
      }
    });
  }

  _addVectorLayers() {
    const map = this.map;

    // 1. Water features (OSM)
    map.addSource('water-src', { type: 'geojson', data: this.rawWater });
    map.addLayer({
      id: 'water-fill',
      type: 'fill',
      source: 'water-src',
      filter: ['==', '$type', 'Polygon'],
      paint: {
        'fill-color': '#0284c7',
        'fill-opacity': 0.55
      }
    });
    map.addLayer({
      id: 'water-line',
      type: 'line',
      source: 'water-src',
      paint: {
        'line-color': '#38bdf8',
        'line-width': ['case', ['==', '$type', 'Polygon'], 1.8, 2.4],
        'line-opacity': 0.95
      }
    });

    // 2. Roads network
    map.addSource('roads-src', { type: 'geojson', data: this.rawRoads });
    map.addLayer({
      id: 'roads-casing',
      type: 'line',
      source: 'roads-src',
      paint: {
        'line-color': '#090d16',
        'line-width': [
          'match', ['get', 'highway_type'],
          'motorway', 4.8,
          'trunk', 4.2,
          'primary', 3.8,
          2.8
        ],
        'line-opacity': 0.85
      }
    });
    map.addLayer({
      id: 'roads-line',
      type: 'line',
      source: 'roads-src',
      paint: {
        'line-color': [
          'match', ['get', 'highway_type'],
          'motorway', '#f97316',
          'trunk', '#fb923c',
          'primary', '#fbbf24',
          'secondary', '#38bdf8',
          '#94a3b8'
        ],
        'line-width': [
          'match', ['get', 'highway_type'],
          'motorway', 3.0,
          'trunk', 2.6,
          'primary', 2.2,
          1.6
        ],
        'line-opacity': 0.95
      }
    });

    // 2b. Power Transmission Lines (OSM) - Optional layer
    if (this.rawPowerLines && Array.isArray(this.rawPowerLines.features) && this.rawPowerLines.features.length > 0) {
      map.addSource('power-lines-src', {
        type: 'geojson',
        data: this.rawPowerLines
      });
      map.addLayer({
        id: 'power-lines-layer',
        type: 'line',
        source: 'power-lines-src',
        layout: { 'visibility': 'none' },
        paint: {
          'line-color': '#a855f7',
          'line-width': 1.6,
          'line-dasharray': [3, 1.5],
          'line-opacity': 0.85
        }
      });
    }

    // 3. Demand Zones (step scale on load_kw, 4 levels)
    map.addSource('demand-src', { type: 'geojson', data: this.currentDemandData || this.rawDemandZones });
    map.addLayer({
      id: 'demand-fill',
      type: 'fill',
      source: 'demand-src',
      paint: {
        'fill-color': [
          'step',
          ['coalesce', ['get', 'load_kw'], 0],
          '#38bdf8',
          120, '#818cf8',
          250, '#f59e0b',
          400, '#ef4444'
        ],
        'fill-opacity': 0.35
      }
    });
    map.addLayer({
      id: 'demand-line',
      type: 'line',
      source: 'demand-src',
      paint: {
        'line-color': '#c084fc',
        'line-width': 2.0,
        'line-dasharray': [2, 1]
      }
    });

    // 4. Energy Flow lines (width & color scaled by flow_kw)
    map.addSource('flow-src', {
      type: 'geojson',
      data: this.currentFlowData || { type: 'FeatureCollection', features: [] }
    });
    map.addLayer({
      id: 'flow-line',
      type: 'line',
      source: 'flow-src',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': [
          'case',
          ['<=', ['get', 'flow_kw'], 0], '#475569',
          [
            'match', ['get', 'source_type'],
            'solar', '#f59e0b',
            'wind', '#06b6d4',
            'hydro', '#3b82f6',
            'battery', '#10b981',
            'grid', '#ef4444',
            '#6366f1'
          ]
        ],
        'line-width': [
          'case',
          ['<=', ['get', 'flow_kw'], 0], 1.2,
          [
            'interpolate', ['linear'], ['get', 'flow_kw'],
            1, 2.0,
            100, 3.5,
            300, 5.5,
            600, 8.0
          ]
        ],
        'line-opacity': [
          'case',
          ['<=', ['get', 'flow_kw'], 0], 0.35,
          0.88
        ]
      }
    });

    // 5. Flow moving dots
    map.addSource('flow-dots-src', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    });
    map.addLayer({
      id: 'flow-dots-layer',
      type: 'circle',
      source: 'flow-dots-src',
      paint: {
        'circle-radius': ['coalesce', ['get', 'radius'], 4],
        'circle-color': ['coalesce', ['get', 'color'], '#ffffff'],
        'circle-opacity': 0.95,
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#ffffff'
      }
    });

    // 6. Assets (Halo ring + Circle + Labels)
    map.addSource('assets-src', { type: 'geojson', data: this.currentAppliedAssets || this.rawAssets });

    map.addLayer({
      id: 'assets-halo',
      type: 'circle',
      source: 'assets-src',
      paint: {
        'circle-radius': 18,
        'circle-color': [
          'match', ['get', 'status'],
          'active', '#22c55e',
          'discharging', '#10b981',
          'charging', '#0284c7',
          'not_supplying', '#64748b',
          '#475569'
        ],
        'circle-opacity': 0.45
      }
    });

    map.addLayer({
      id: 'assets-circle',
      type: 'circle',
      source: 'assets-src',
      paint: {
        'circle-radius': 9.5,
        'circle-color': [
          'match', ['get', 'type'],
          'solar', '#f59e0b',
          'wind', '#06b6d4',
          'hydro', '#3b82f6',
          'battery', '#10b981',
          'grid', '#ef4444',
          'demand', '#8b5cf6',
          '#64748b'
        ],
        'circle-stroke-width': 2.5,
        'circle-stroke-color': '#ffffff'
      }
    });

    map.addLayer({
      id: 'assets-label',
      type: 'symbol',
      source: 'assets-src',
      minzoom: 13,
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 11.5,
        'text-offset': [0, 1.5],
        'text-anchor': 'top',
        'text-max-width': 12
      },
      paint: {
        'text-color': '#0f172a',
        'text-halo-color': '#ffffff',
        'text-halo-width': 2.5
      }
    });
  }

  _bindMapEvents() {
    const map = this.map;

    // Asset clicks
    map.on('click', 'assets-circle', (e) => {
      if (!e.features || e.features.length === 0) return;
      const clicked = e.features[0];
      const coords = clicked.geometry.coordinates.slice();
      const aid = clicked.properties.id;
      const fullFeat = this.currentAppliedAssets && this.currentAppliedAssets.features
        ? this.currentAppliedAssets.features.find(f => f.properties && f.properties.id === aid) || clicked
        : clicked;

      if (typeof this.options.onAssetClick === 'function') {
        this.options.onAssetClick(fullFeat, coords);
      }
      this.openAssetPopup(fullFeat, coords);
    });

    map.on('mouseenter', 'assets-circle', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'assets-circle', () => { map.getCanvas().style.cursor = ''; });

    // Demand zones click
    map.on('click', 'demand-fill', (e) => {
      if (!e.features || e.features.length === 0) return;
      const clicked = e.features[0];
      const zid = clicked.properties.id;
      const feat = this.currentDemandData && this.currentDemandData.features
        ? this.currentDemandData.features.find(f => f.properties && f.properties.id === zid) || clicked
        : clicked;
      const p = feat.properties;
      const timeStr = this.currentDispatchRow ? formatTimeLabel(this.currentDispatchRow.timestamp) : '00:00';
      const totalLoad = this.currentDispatchRow ? (this.currentDispatchRow.load_kw || 900) : 900;

      const html = createDemandZonePopupHTML(p, timeStr, totalLoad);
      new this.maplibregl.Popup({ offset: 10 })
        .setLngLat(e.lngLat)
        .setHTML(html)
        .addTo(map);
    });

    map.on('mouseenter', 'demand-fill', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'demand-fill', () => { map.getCanvas().style.cursor = ''; });
  }

  _startAnimation() {
    let startTime = performance.now();

    const animateLoop = (now) => {
      if (this.isDestroyed) return;

      if (typeof document !== 'undefined' && !document.hidden &&
          this.currentFlowData && this.currentFlowData.features &&
          this.map && this.map.getSource('flow-dots-src')) {

        const elapsed = (now - startTime) / 1000;
        const dotFeatures = [];

        this.currentFlowData.features.forEach(f => {
          const kw = Number(f.properties.flow_kw) || 0;
          if (kw <= 0) return;

          const coords = f.geometry.coordinates;
          if (!coords || coords.length < 2) return;

          const srcType = f.properties.source_type;
          const dotColor = DOT_COLORS[srcType] || '#ffffff';
          const radius = Math.max(3.0, Math.min(6.5, 3.0 + (kw / 120)));
          const speed = 0.35 + Math.min(1.2, kw / 300);

          const offsets = [0.0, 0.5];
          offsets.forEach(offset => {
            const progress = (elapsed * speed + offset) % 1.0;
            const lon = coords[0][0] + (coords[1][0] - coords[0][0]) * progress;
            const lat = coords[0][1] + (coords[1][1] - coords[0][1]) * progress;

            dotFeatures.push({
              type: 'Feature',
              properties: { radius, color: dotColor },
              geometry: { type: 'Point', coordinates: [lon, lat] }
            });
          });
        });

        const dotsSrc = this.map.getSource('flow-dots-src');
        if (dotsSrc && typeof dotsSrc.setData === 'function') {
          dotsSrc.setData({ type: 'FeatureCollection', features: dotFeatures });
        }
      }

      this.animFrameId = requestAnimationFrame(animateLoop);
    };

    this.animFrameId = requestAnimationFrame(animateLoop);

    if (typeof document !== 'undefined') {
      this.onVisibilityChange = () => {
        if (document.hidden) {
          if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
          }
        } else {
          startTime = performance.now();
          if (!this.animFrameId) {
            this.animFrameId = requestAnimationFrame(animateLoop);
          }
        }
      };
      document.addEventListener('visibilitychange', this.onVisibilityChange);
    }
  }

  // ==========================================
  // Public Controller Methods
  // ==========================================

  setDispatch(dispatchJson, indexOrTimestamp) {
    if (!dispatchJson) return null;
    const row = normalizeDispatch(dispatchJson, indexOrTimestamp);
    this.currentDispatchRow = row;

    // Check if dispatchJson carries scenario metadata
    const scenarioId = dispatchJson.scenario_id || (this.currentScenarioData && this.currentScenarioData.scenario_id);
    this.currentAppliedAssets = applyDispatchToAssets(this.rawAssets, row, 0, scenarioId);
    this.currentFlowData = buildEnergyFlowData(row, this.rawAssets);
    this.currentDemandData = distributeDemandLoadData(this.rawDemandZones, row.load_kw);

    if (this.map && typeof this.map.getSource === 'function') {
      const aSrc = this.map.getSource('assets-src');
      if (aSrc && typeof aSrc.setData === 'function') aSrc.setData(this.currentAppliedAssets);

      const fSrc = this.map.getSource('flow-src');
      if (fSrc && typeof fSrc.setData === 'function') fSrc.setData(this.currentFlowData);

      const dSrc = this.map.getSource('demand-src');
      if (dSrc && typeof dSrc.setData === 'function') dSrc.setData(this.currentDemandData);
    }

    // Refresh active popup if an asset is open
    if (this.activePopup && this.activePopupAssetId && this.currentAppliedAssets) {
      const found = this.currentAppliedAssets.features.find(f => f.properties && f.properties.id === this.activePopupAssetId);
      if (found) {
        const timeStr = formatTimeLabel(row.timestamp);
        const scenarioLabel = (this.currentScenarioData && (this.currentScenarioData.scenario_name || this.currentScenarioData.scenario_id)) || 'Normal Day';
        this.activePopup.setHTML(createAssetPopupHTML(found.properties, timeStr, scenarioLabel));
      }
    }

    return {
      dispatchRow: row,
      appliedAssets: this.currentAppliedAssets,
      flowData: this.currentFlowData,
      demandData: this.currentDemandData,
      metrics: computeMetrics(row)
    };
  }

  async setScenario(id) {
    const filename = id === 'sample_dispatch' ? 'data/sample_dispatch.json' : `data/scenarios/${id}.json`;
    const url = this.resolveUrl(filename);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load scenario ${id} from ${url}: HTTP ${res.status}`);
    const data = await res.json();
    this.currentScenarioData = data;
    return this.setDispatch(data, 0);
  }

  setBasemap(mode) {
    this.currentBasemap = mode;
    if (!this.map) return;

    const isStreets = mode === 'streets';
    const isSat = mode === 'satellite';

    if (this.map.getLayer('osm-tiles-layer')) {
      this.map.setLayoutProperty('osm-tiles-layer', 'visibility', isStreets ? 'visible' : 'none');
    }
    if (this.map.getLayer('satellite-tiles-layer')) {
      this.map.setLayoutProperty('satellite-tiles-layer', 'visibility', isSat ? 'visible' : 'none');
    }
  }

  setLayerVisibility(layerId, bool) {
    if (!this.map) return;
    if (layerId === 'terrain') {
      this.setTerrain(bool);
      return;
    }
    const vis = bool ? 'visible' : 'none';

    const groupMap = {
      'assets': ['assets-halo', 'assets-circle', 'assets-label'],
      'flow': ['flow-line', 'flow-dots-layer'],
      'demand': ['demand-fill', 'demand-line'],
      'water': ['water-fill', 'water-line'],
      'roads': ['roads-casing', 'roads-line'],
      'power': ['power-lines-layer'],
      'power-lines': ['power-lines-layer'],
      'terrain': ['terrarium-hillshade']
    };

    const targetLayers = groupMap[layerId] || [layerId];
    targetLayers.forEach(id => {
      if (this.map.getLayer(id)) {
        this.map.setLayoutProperty(id, 'visibility', vis);
      }
    });
  }

  flyToAsset(id) {
    if (!id) return null;
    const features = (this.currentAppliedAssets && this.currentAppliedAssets.features) ||
                     (this.rawAssets && this.rawAssets.features) || [];
    const feature = features.find(f => f.properties && f.properties.id === id);
    if (!feature || !feature.geometry) return null;

    const coords = feature.geometry.coordinates.slice();
    if (this.map && typeof this.map.flyTo === 'function') {
      this.map.flyTo({ center: coords, zoom: 13.8, speed: 1.2 });
    }
    this.openAssetPopup(feature, coords);
    return feature;
  }

  openAssetPopup(feature, coords) {
    if (this.activePopup) {
      this.activePopup.remove();
    }
    this.activePopupAssetId = (feature && feature.properties) ? feature.properties.id : null;
    const timeStr = this.currentDispatchRow ? formatTimeLabel(this.currentDispatchRow.timestamp) : '00:00';
    const scenarioLabel = (this.currentScenarioData && (this.currentScenarioData.scenario_name || this.currentScenarioData.scenario_id)) || 'Normal Day';
    const html = createAssetPopupHTML((feature && feature.properties) || {}, timeStr, scenarioLabel);

    if (this.map && this.maplibregl && this.maplibregl.Popup) {
      this.activePopup = new this.maplibregl.Popup({ offset: 14 })
        .setLngLat(coords)
        .setHTML(html)
        .addTo(this.map);

      this.activePopup.on('close', () => {
        this.activePopup = null;
        this.activePopupAssetId = null;
      });
    }
  }

  zoomToAssets() {
    if (!this.map) return;
    const ab = (this.config && this.config.asset_bbox) || ASSET_BBOX;
    this.map.fitBounds([[ab[0], ab[1]], [ab[2], ab[3]]], { padding: 60 });
  }

  zoomToRegion() {
    if (!this.map) return;
    const cb = (this.config && this.config.context_bbox) || CONTEXT_BBOX;
    this.map.fitBounds([[cb[0], cb[1]], [cb[2], cb[3]]], { padding: 40 });
  }

  getAssets() {
    return this.currentAppliedAssets || this.rawAssets;
  }

  getMap() {
    return this.map;
  }

  getConfig() {
    return this.config;
  }

  setTerrain(enabled) {
    this.isTerrainActive = Boolean(enabled);
    if (!this.map) return;

    if (this.isTerrainActive) {
      try {
        // Ensure terrarium-dem raster-dem source exists
        if (!this.map.getSource('terrarium-dem')) {
          this.map.addSource('terrarium-dem', {
            type: 'raster-dem',
            tiles: [
              'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
            ],
            encoding: 'terrarium',
            tileSize: 256,
            maxzoom: 14
          });
        }

        // Add hillshade layer dynamically only when terrain is enabled
        if (!this.map.getLayer('terrarium-hillshade')) {
          const beforeLayer = this.map.getLayer('water-fill') ? 'water-fill' : undefined;
          this.map.addLayer({
            id: 'terrarium-hillshade',
            type: 'hillshade',
            source: 'terrarium-dem',
            layout: { 'visibility': 'visible' },
            paint: {
              'hillshade-exaggeration': 0.25,
              'hillshade-shadow-color': 'rgba(15, 23, 42, 0.35)',
              'hillshade-highlight-color': 'rgba(255, 255, 255, 0.25)',
              'hillshade-accent-color': 'rgba(56, 189, 248, 0.15)',
              'hillshade-illumination-direction': 315
            }
          }, beforeLayer);
        } else {
          this.map.setLayoutProperty('terrarium-hillshade', 'visibility', 'visible');
        }

        if (typeof this.map.setTerrain === 'function') {
          this.map.setTerrain({ source: 'terrarium-dem', exaggeration: 1.0 });
        }
      } catch (err) {
        console.warn("[GridMate] Could not enable 3D terrain/hillshade:", err);
      }
    } else {
      try {
        if (typeof this.map.setTerrain === 'function') {
          this.map.setTerrain(null);
        }
        if (this.map.getLayer('terrarium-hillshade')) {
          this.map.setLayoutProperty('terrarium-hillshade', 'visibility', 'none');
        }
      } catch (err) {
        console.warn("[GridMate] Could not disable 3D terrain:", err);
      }
    }
  }

  destroy() {
    this.isDestroyed = true;

    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }

    if (this.onVisibilityChange && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.onVisibilityChange);
      this.onVisibilityChange = null;
    }

    if (this.activePopup) {
      this.activePopup.remove();
      this.activePopup = null;
    }

    if (this.map) {
      this.map.remove();
      this.map = null;
    }

    if (activeMapController === this) {
      activeMapController = null;
    }
  }
}

// ==========================================
// Top-Level Module Exports
// ==========================================

/**
 * Initializes the GridMate Map into containerId with options.
 * Returns Promise<GridMateMapController>.
 */
export async function init(containerId, options = {}) {
  const controller = new GridMateMapController(containerId, options);
  activeMapController = controller;
  try {
    await controller._loadData();
    await controller._initMapInstance();
    return controller;
  } catch (err) {
    controller._showVisibleError(err.message || String(err));
    throw err;
  }
}

export function setDispatch(dispatchJson, indexOrTimestamp) {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.setDispatch(dispatchJson, indexOrTimestamp);
}

export function setScenario(id) {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.setScenario(id);
}

export function setBasemap(mode) {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.setBasemap(mode);
}

export function setLayerVisibility(layerId, bool) {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.setLayerVisibility(layerId, bool);
}

export function flyToAsset(id) {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.flyToAsset(id);
}

export function zoomToAssets() {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.zoomToAssets();
}

export function zoomToRegion() {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.zoomToRegion();
}

export function getAssets() {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.getAssets();
}

export function destroy() {
  if (activeMapController) {
    activeMapController.destroy();
    activeMapController = null;
  }
}

export function setTerrain(bool) {
  if (!activeMapController) throw new Error("GridMate map not initialized. Call init() first.");
  return activeMapController.setTerrain(bool);
}

// Default export
export default {
  init,
  setDispatch,
  setScenario,
  setBasemap,
  setLayerVisibility,
  flyToAsset,
  zoomToAssets,
  zoomToRegion,
  getAssets,
  destroy,
  setTerrain,
  normalizeDispatch,
  applyDispatchToAssets,
  buildEnergyFlowData,
  distributeDemandLoadData,
  computeMetrics,
  formatTimeLabel,
  createAssetPopupHTML,
  createDemandZonePopupHTML,
  GridMateMapController
};

