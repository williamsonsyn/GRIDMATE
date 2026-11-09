/**
 * applyDispatch.js
 * Browser & Node.js compatible module mirroring src/map_utils.py.
 * Can be reused by Member 4 in React/TypeScript without any Python dependency.
 *
 * Rules:
 * - Proportional allocation of solar, wind, hydro across assets by capacity_kw
 * - battery_kw > 0 : status = 'discharging'
 * - battery_kw < 0 : status = 'charging'
 * - battery_kw == 0: status = 'idle'
 * - grid_kw == 0   : status = 'not_supplying', else 'active'
 * - solar/wind/hydro: active if output > 0, else 'idle'
 * - forecast_output_kw is always >= 0
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.GridMateDispatch = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {

  function parseDispatchRow(dispatchInput, timestampOrIndex) {
    if (!dispatchInput) return {};
    if (Array.isArray(dispatchInput.dispatch) && dispatchInput.dispatch.length > 0) {
      if (typeof timestampOrIndex === 'string') {
        var found = dispatchInput.dispatch.find(function (r) {
          return String(r.timestamp) === timestampOrIndex;
        });
        if (found) return Object.assign({}, found, { scenario_id: dispatchInput.scenario_id });
      }
      var idx = (typeof timestampOrIndex === 'number') ? timestampOrIndex : 0;
      idx = Math.max(0, Math.min(idx, dispatchInput.dispatch.length - 1));
      return Object.assign({}, dispatchInput.dispatch[idx], { scenario_id: dispatchInput.scenario_id });
    }
    return Object.assign({}, dispatchInput);
  }

  function applyDispatch(assetsGeoJSON, dispatchRow, scenarioId) {
    var assetsFc = JSON.parse(JSON.stringify(assetsGeoJSON));
    var row = dispatchRow || {};
    var effectiveScenario = scenarioId || row.scenario_id || 'Simulated Scenario';

    var solarTotal = Math.max(0, Number(row.solar_kw) || 0);
    var windTotal = Math.max(0, Number(row.wind_kw) || 0);
    var hydroTotal = Math.max(0, Number(row.hydro_kw) || 0);
    var gridTotal = Math.max(0, Number(row.grid_kw) || 0);
    var loadTotal = Math.max(0, Number(row.load_kw) || 0);
    var batteryVal = Number(row.battery_kw) || 0;
    var batterySoc = row.battery_soc_kwh;

    // Calculate sum of capacity_kw per type
    var typeCapacities = {};
    (assetsFc.features || []).forEach(function (f) {
      var p = f.properties || {};
      var t = p.type;
      var cap = Number(p.capacity_kw) || 0;
      if (t) {
        typeCapacities[t] = (typeCapacities[t] || 0) + cap;
      }
    });

    assetsFc.features = (assetsFc.features || []).map(function (feature) {
      var f = JSON.parse(JSON.stringify(feature));
      var p = f.properties || {};
      var t = p.type;
      var cap = Number(p.capacity_kw) || 0;
      var totCap = typeCapacities[t] || 0;
      var ratio = totCap > 0 ? (cap / totCap) : 0;

      var forecastOutput = 0;
      var status = 'idle';

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
        if (batteryVal > 0) {
          status = 'discharging';
        } else if (batteryVal < 0) {
          status = 'charging';
        } else {
          status = 'idle';
        }
        if (batterySoc !== undefined && batterySoc !== null) {
          p.battery_soc_kwh = Number(batterySoc);
        }
      } else if (t === 'demand') {
        forecastOutput = +(loadTotal * ratio).toFixed(2);
        status = 'active';
      }

      var utilization = cap > 0 ? +((forecastOutput / cap) * 100).toFixed(1) : 0;
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

  function buildEnergyFlow(dispatchRow, assetsGeoJSON) {
    var appliedAssets = applyDispatch(assetsGeoJSON, dispatchRow);
    var demandHub = null;
    var supplyAssets = [];

    (appliedAssets.features || []).forEach(function (f) {
      if ((f.properties || {}).type === 'demand') {
        demandHub = f;
      } else {
        supplyAssets.append ? supplyAssets.append(f) : supplyAssets.push(f);
      }
    });

    if (!demandHub) {
      console.warn('buildEnergyFlow: No demand hub feature found.');
      return { type: 'FeatureCollection', features: [] };
    }

    var hubCoords = demandHub.geometry.coordinates;
    var flowFeatures = [];

    supplyAssets.forEach(function (src) {
      var p = src.properties || {};
      var srcCoords = src.geometry.coordinates;
      var outputKw = Number(p.forecast_output_kw) || 0;
      var status = p.status || 'idle';

      var direction = 'to_demand';
      var coords = [srcCoords, hubCoords];

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

      var flowActive = outputKw > 0;
      var lineWeight = Math.max(1.5, Math.min(8.0, 1.5 + (outputKw / 100.0)));

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

  function distributeDemandLoad(demandZonesGeoJSON, totalLoadKw) {
    var zonesFc = JSON.parse(JSON.stringify(demandZonesGeoJSON));
    var loadVal = Math.max(0, Number(totalLoadKw) || 0);

    var totalBaseLoad = 0;
    (zonesFc.features || []).forEach(function (f) {
      totalBaseLoad += Number((f.properties || {}).base_load_kw) || 0;
    });

    zonesFc.features = (zonesFc.features || []).map(function (feature) {
      var f = JSON.parse(JSON.stringify(feature));
      var p = f.properties || {};
      var baseLoad = Number(p.base_load_kw) || 0;
      var ratio = totalBaseLoad > 0 ? (baseLoad / totalBaseLoad) : 0;
      var zoneLoad = +(loadVal * ratio).toFixed(2);
      var sharePct = +(ratio * 100).toFixed(1);

      p.load_kw = Math.max(0, zoneLoad);
      p.load_share_pct = sharePct;
      p.label = 'illustrative zone';
      f.properties = p;
      return f;
    });

    return zonesFc;
  }

  return {
    parseDispatchRow: parseDispatchRow,
    applyDispatch: applyDispatch,
    buildEnergyFlow: buildEnergyFlow,
    distributeDemandLoad: distributeDemandLoad
  };
}));

