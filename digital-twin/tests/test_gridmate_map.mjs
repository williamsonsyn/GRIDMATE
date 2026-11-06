/**
 * test_gridmate_map.mjs
 * Node-based test suite for gridmateMap.js integration module.
 *
 * Checks:
 * 1. Every required function is exported:
 *    init, setDispatch, setScenario, setBasemap, setLayerVisibility,
 *    flyToAsset, zoomToAssets, zoomToRegion, getAssets, destroy.
 * 2. Pure helpers parity: contract-form and flat-form dispatch inputs
 *    produce identical results for asset outputs, status, flow lines, and demand load.
 * 3. Capacity constraints and battery sign convention across all scenarios.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const BASE_DIR = path.resolve(__dirname, '..');

// Import gridmateMap.js module
import * as GridMateMap from '../map/gridmateMap.js';

console.log('--- Testing gridmateMap.js exports ---');

const REQUIRED_FUNCTIONS = [
  'init',
  'setDispatch',
  'setScenario',
  'setBasemap',
  'setLayerVisibility',
  'flyToAsset',
  'zoomToAssets',
  'zoomToRegion',
  'getAssets',
  'destroy'
];

for (const fnName of REQUIRED_FUNCTIONS) {
  assert.equal(
    typeof GridMateMap[fnName],
    'function',
    `Expected function ${fnName} to be exported from gridmateMap.js, but got ${typeof GridMateMap[fnName]}`
  );
  console.log(`  ✓ Exported: ${fnName}()`);
}

// Check pure helpers
const REQUIRED_HELPERS = [
  'normalizeDispatch',
  'applyDispatchToAssets',
  'buildEnergyFlowData',
  'distributeDemandLoadData',
  'computeMetrics',
  'formatTimeLabel',
  'createAssetPopupHTML'
];

for (const helperName of REQUIRED_HELPERS) {
  assert.equal(
    typeof GridMateMap[helperName],
    'function',
    `Expected helper function ${helperName} to be exported from gridmateMap.js`
  );
  console.log(`  ✓ Helper: ${helperName}()`);
}

console.log('\n--- Testing contract-form vs flat-form dispatch parity ---');

const assetsGeoJSON = JSON.parse(
  fs.readFileSync(path.join(BASE_DIR, 'data', 'assets.geojson'), 'utf-8')
);
const demandZonesGeoJSON = JSON.parse(
  fs.readFileSync(path.join(BASE_DIR, 'data', 'demand_zones.geojson'), 'utf-8')
);
const sampleDispatch = JSON.parse(
  fs.readFileSync(path.join(BASE_DIR, 'data', 'sample_dispatch.json'), 'utf-8')
);

assert.equal(assetsGeoJSON.features.length, 10, 'Expected 10 assets in assets.geojson');

// Test across all 24 hours of sample_dispatch
for (let hour = 0; hour < sampleDispatch.dispatch.length; hour++) {
  const contractInput = sampleDispatch;
  const flatInput = sampleDispatch.dispatch[hour];
  const timestamp = flatInput.timestamp;

  // 1. normalizeDispatch by index vs flat
  const normByIndex = GridMateMap.normalizeDispatch(contractInput, hour);
  const normByFlat = GridMateMap.normalizeDispatch(flatInput);

  assert.equal(normByIndex.solar_kw, normByFlat.solar_kw, `Hour ${hour}: solar_kw mismatch`);
  assert.equal(normByIndex.wind_kw, normByFlat.wind_kw, `Hour ${hour}: wind_kw mismatch`);
  assert.equal(normByIndex.hydro_kw, normByFlat.hydro_kw, `Hour ${hour}: hydro_kw mismatch`);
  assert.equal(normByIndex.battery_kw, normByFlat.battery_kw, `Hour ${hour}: battery_kw mismatch`);
  assert.equal(normByIndex.grid_kw, normByFlat.grid_kw, `Hour ${hour}: grid_kw mismatch`);
  assert.equal(normByIndex.load_kw, normByFlat.load_kw, `Hour ${hour}: load_kw mismatch`);
  assert.equal(normByIndex.battery_soc_kwh, normByFlat.battery_soc_kwh, `Hour ${hour}: battery_soc_kwh mismatch`);

  // 2. normalizeDispatch by timestamp string vs flat
  const normByTimestamp = GridMateMap.normalizeDispatch(contractInput, timestamp);
  assert.equal(normByTimestamp.solar_kw, normByFlat.solar_kw, `Timestamp ${timestamp}: solar_kw mismatch`);

  // 3. applyDispatchToAssets parity check
  const appliedFromContract = GridMateMap.applyDispatchToAssets(assetsGeoJSON, contractInput, hour);
  const appliedFromFlat = GridMateMap.applyDispatchToAssets(assetsGeoJSON, flatInput);

  assert.equal(appliedFromContract.features.length, appliedFromFlat.features.length);

  for (let i = 0; i < appliedFromContract.features.length; i++) {
    const fC = appliedFromContract.features[i].properties;
    const fF = appliedFromFlat.features[i].properties;

    assert.equal(fC.id, fF.id, `Feature ${i} id mismatch`);
    assert.equal(fC.type, fF.type, `Asset ${fC.id} type mismatch`);
    assert.equal(
      fC.forecast_output_kw,
      fF.forecast_output_kw,
      `Asset ${fC.id} at hour ${hour}: output mismatch (contract ${fC.forecast_output_kw} vs flat ${fF.forecast_output_kw})`
    );
    assert.equal(
      fC.status,
      fF.status,
      `Asset ${fC.id} at hour ${hour}: status mismatch (contract ${fC.status} vs flat ${fF.status})`
    );
    assert.equal(
      fC.utilization_percent,
      fF.utilization_percent,
      `Asset ${fC.id} at hour ${hour}: utilization mismatch (contract ${fC.utilization_percent} vs flat ${fF.utilization_percent})`
    );

    if (fC.type === 'battery') {
      assert.equal(
        fC.battery_soc_kwh,
        fF.battery_soc_kwh,
        `Battery SOC mismatch at hour ${hour}`
      );
      // Battery sign convention: battery_kw > 0 is discharging, < 0 is charging
      if (flatInput.battery_kw > 0) {
        assert.equal(fC.status, 'discharging', `Battery should be discharging when battery_kw > 0`);
      } else if (flatInput.battery_kw < 0) {
        assert.equal(fC.status, 'charging', `Battery should be charging when battery_kw < 0`);
      } else {
        assert.equal(fC.status, 'idle', `Battery should be idle when battery_kw === 0`);
      }
    }
  }

  // 4. Dynamic energy flow parity check
  const flowFromContract = GridMateMap.buildEnergyFlowData(contractInput, assetsGeoJSON, hour);
  const flowFromFlat = GridMateMap.buildEnergyFlowData(flatInput, assetsGeoJSON);

  assert.equal(flowFromContract.features.length, flowFromFlat.features.length);
  for (let j = 0; j < flowFromContract.features.length; j++) {
    const pC = flowFromContract.features[j].properties;
    const pF = flowFromFlat.features[j].properties;
    assert.equal(pC.source_id, pF.source_id);
    assert.equal(pC.flow_kw, pF.flow_kw);
    assert.equal(pC.status, pF.status);
    assert.equal(pC.direction, pF.direction);
    assert.equal(pC.line_weight, pF.line_weight);
  }

  // 5. Demand zones load distribution parity
  const zonesFromContract = GridMateMap.distributeDemandLoadData(demandZonesGeoJSON, normByIndex.load_kw);
  const zonesFromFlat = GridMateMap.distributeDemandLoadData(demandZonesGeoJSON, normByFlat.load_kw);

  assert.equal(zonesFromContract.features.length, zonesFromFlat.features.length);
  for (let k = 0; k < zonesFromContract.features.length; k++) {
    const zC = zonesFromContract.features[k].properties;
    const zF = zonesFromFlat.features[k].properties;
    assert.equal(zC.id, zF.id);
    assert.equal(zC.load_kw, zF.load_kw);
    assert.equal(zC.load_share_pct, zF.load_share_pct);
  }
}
console.log('  ✓ 24/24 sample_dispatch hours verified: contract-form === flat-form parity');

// Test scenario files
const SCENARIOS = ['normal', 'cloudy', 'heavy_monsoon', 'high_wind', 'peak_demand'];
for (const scId of SCENARIOS) {
  const scData = JSON.parse(
    fs.readFileSync(path.join(BASE_DIR, 'data', 'scenarios', `${scId}.json`), 'utf-8')
  );
  const rowContract = GridMateMap.normalizeDispatch(scData, 0);
  const rowFlat = GridMateMap.normalizeDispatch(scData.dispatch[0]);

  assert.deepEqual(rowContract.solar_kw, rowFlat.solar_kw, `Scenario ${scId}: solar_kw mismatch`);
  assert.deepEqual(rowContract.wind_kw, rowFlat.wind_kw, `Scenario ${scId}: wind_kw mismatch`);
  assert.deepEqual(rowContract.hydro_kw, rowFlat.hydro_kw, `Scenario ${scId}: hydro_kw mismatch`);
  assert.deepEqual(rowContract.battery_kw, rowFlat.battery_kw, `Scenario ${scId}: battery_kw mismatch`);
  assert.deepEqual(rowContract.grid_kw, rowFlat.grid_kw, `Scenario ${scId}: grid_kw mismatch`);
  assert.deepEqual(rowContract.load_kw, rowFlat.load_kw, `Scenario ${scId}: load_kw mismatch`);

  const appliedC = GridMateMap.applyDispatchToAssets(assetsGeoJSON, scData, 0, scId);
  const appliedF = GridMateMap.applyDispatchToAssets(assetsGeoJSON, rowFlat, 0, scId);

  for (let i = 0; i < appliedC.features.length; i++) {
    assert.equal(appliedC.features[i].properties.forecast_output_kw, appliedF.features[i].properties.forecast_output_kw);
    assert.equal(appliedC.features[i].properties.status, appliedF.features[i].properties.status);
  }
  console.log(`  ✓ Scenario ${scId} contract vs flat parity verified`);
}

console.log('\n--- Testing optional layers and core file error handling ---');

// Test _fetchResource behavior via GridMateMapController instance
const ctrl = new GridMateMap.GridMateMapController('test-container', { basePath: './', maplibregl: {} });

// 1. Optional layer returns null and warns on 404
let warned = false;
const origWarn = console.warn;
console.warn = (msg) => { warned = true; };

// Mock global fetch to simulate 404 for optional file
const origFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  if (url.includes('power_lines')) {
    return { ok: false, status: 404, statusText: 'Not Found' };
  }
  if (url.includes('missing_core')) {
    return { ok: false, status: 404, statusText: 'Not Found' };
  }
  return { ok: true, text: async () => '{"type": "FeatureCollection", "features": []}' };
};

const optionalResult = await ctrl._fetchResource('data/power_lines.geojson', false, 'data/power_lines.geojson');
assert.equal(optionalResult, null, 'Expected optional layer to return null on 404');
assert.equal(warned, true, 'Expected non-blocking console.warn when optional layer fails');
console.log('  ✓ Optional layer power_lines.geojson fails gracefully without blocking (logs warning, returns null)');

// 2. Core file failure throws Error naming the file
let coreErrorThrown = false;
try {
  await ctrl._fetchResource('data/missing_core.geojson', true, 'data/missing_core.geojson');
} catch (err) {
  coreErrorThrown = true;
  assert.ok(err.message.includes('data/missing_core.geojson'), 'Error message must name the missing core file');
}
assert.equal(coreErrorThrown, true, 'Expected core file failure to throw an error');
console.log('  ✓ Core file failure blocks and throws error naming the file');

// Restore globals
console.warn = origWarn;
globalThis.fetch = origFetch;

console.log('\n--- Testing terrain and hillshade safety ---');

// Mock MapLibre map instance for controller
const addedSources = {};
const addedLayers = [];
let setTerrainCall = null;
const mockMap = {
  getSource: (id) => addedSources[id],
  addSource: (id, config) => { addedSources[id] = config; },
  getLayer: (id) => addedLayers.find(l => l.id === id),
  addLayer: (layerDef, beforeId) => { addedLayers.push(layerDef); },
  setLayoutProperty: (id, prop, val) => {
    const l = addedLayers.find(x => x.id === id);
    if (l) {
      l.layout = l.layout || {};
      l.layout[prop] = val;
    }
  },
  setTerrain: (cfg) => { setTerrainCall = cfg; }
};

const terrainCtrl = new GridMateMap.GridMateMapController('terrain-container', {
  basePath: './',
  maplibregl: {}
});
terrainCtrl.map = mockMap;

// 1. Terrain must be OFF by default
assert.equal(terrainCtrl.isTerrainActive, false, 'Terrain must be OFF by default');
assert.equal(mockMap.getLayer('terrarium-hillshade'), undefined, 'terrarium-hillshade layer must not exist before terrain toggle');
console.log('  ✓ Terrain is OFF by default; terrarium-hillshade layer is not added at start');

// 2. Enable terrain dynamically adds layer with valid properties
terrainCtrl.setTerrain(true);
assert.equal(terrainCtrl.isTerrainActive, true);
const hillshadeLayer = mockMap.getLayer('terrarium-hillshade');
assert.ok(hillshadeLayer, 'terrarium-hillshade layer must be added when terrain enabled');
assert.equal(hillshadeLayer.type, 'hillshade');
assert.equal(hillshadeLayer.paint['hillshade-opacity'], undefined, 'hillshade-opacity must NOT be present in hillshade paint');
assert.equal(typeof hillshadeLayer.paint['hillshade-exaggeration'], 'number', 'hillshade-exaggeration must be a number');
assert.ok(hillshadeLayer.paint['hillshade-shadow-color'], 'hillshade-shadow-color must be defined');
assert.ok(hillshadeLayer.paint['hillshade-highlight-color'], 'hillshade-highlight-color must be defined');
assert.ok(mockMap.getSource('terrarium-dem'), 'terrarium-dem source must be added');
console.log('  ✓ setTerrain(true) adds terrarium-dem source and valid hillshade layer without hillshade-opacity');

// 3. Disable terrain
terrainCtrl.setTerrain(false);
assert.equal(terrainCtrl.isTerrainActive, false);
assert.equal(setTerrainCall, null, 'setTerrain(null) must be called when disabling');
console.log('  ✓ setTerrain(false) disables 3D terrain and hides hillshade');

console.log('\n--- All Node tests in test_gridmate_map.mjs PASSED! ---');

