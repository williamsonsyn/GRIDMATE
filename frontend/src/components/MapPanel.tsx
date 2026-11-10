import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { AssetProps, AssetsResponse, AssetType, DispatchPoint, GeoFeature } from '../types/api';
import { computeAssetStates, computeFlows, computeZoneLoads } from '../utils/assetOutput';
import type { AssetState } from '../utils/assetOutput';
import { fmtKw, hourLabel } from '../utils/format';
import { COLORS, TYPE_LABEL } from '../utils/theme';

interface Props {
  assets: AssetsResponse | null;
  error: string | null;
  dispatch: DispatchPoint[] | null;
  hour: number;
  onHour: (h: number) => void;
  busy: boolean;
  scenarioLabel: string | null;
}

type GJ = GeoJSON.FeatureCollection;
const BASEMAP_IDS = ['satellite', 'streets', 'plain'] as const;
type BasemapId = (typeof BASEMAP_IDS)[number];

const DEFAULT_BASEMAPS: Record<string, { name: string; tiles: string[]; attribution?: string }> = {
  satellite: {
    name: 'Satellite',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics | © OpenStreetMap contributors',
  },
  streets: {
    name: 'Streets',
    tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors',
  },
  plain: {
    name: 'Plain dark',
    tiles: [],
    attribution: '© OpenStreetMap contributors',
  },
};

const DOT_COLORS: Record<string, string> = {
  solar: '#f59e0b',
  wind: '#06b6d4',
  hydro: '#3b82f6',
  battery: '#10b981',
  grid: '#ef4444',
  demand: '#8b5cf6',
};

const esc = (s: string) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export function popupHtml(p: AssetProps, st: AssetState | undefined, hourText: string, scenarioLabel: string | null): string {
  const out = st ? fmtKw(st.outputKw) : 'n/a';
  const status = st?.status ?? 'idle';
  const rows: [string, string][] = [
    ['Scenario', scenarioLabel || 'Simulation'],
    ['Type', TYPE_LABEL[p.type] || p.type],
    ['Installed capacity', fmtKw(p.capacity_kw)],
    [`${p.type === 'demand' ? 'Demand' : 'Output'} at ${hourText}`, out],
    ['Status', status.toUpperCase()],
  ];
  if (p.location_source) {
    rows.push(['Location source', p.location_source === 'osm' ? 'Real OSM site' : p.location_source]);
  }
  const note = p.is_synthetic ? 'Simulated prototype asset. Capacity and output are illustrative, not measured.' : p.note ?? '';

  return `
    <div style="box-sizing:border-box; width:275px; max-width:100%; max-height:230px; overflow-y:auto; overflow-x:hidden; padding-right:4px; font-family:ui-sans-serif, system-ui, sans-serif; color:#f8fafc;">
      <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:8px; border-bottom:1px solid #334155; padding-bottom:6px; margin-bottom:8px; padding-right:12px;">
        <strong style="font-size:13px; font-weight:700; color:#ffffff; flex:1; min-width:0; word-break:break-word; overflow-wrap:break-word; line-height:1.35;">
          ${esc(p.name)}
        </strong>
        <span style="font-size:10px; font-weight:700; text-transform:uppercase; padding:2px 6px; border-radius:4px; background:${DOT_COLORS[p.type] || '#64748b'}; color:#ffffff; flex-shrink:0; white-space:nowrap; margin-top:1px;">
          ${esc(p.type)}
        </span>
      </div>
      <div style="display:flex; flex-direction:column; gap:4px; font-size:11px; line-height:1.5;">
        ${rows
          .map(
            ([k, v]) => `
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px; min-width:0;">
            <span style="color:#94a3b8; flex-shrink:0; max-width:50%;">${esc(k)}</span>
            <span style="font-weight:600; color:#f8fafc; text-align:right; min-width:0; flex:1; word-break:break-word; overflow-wrap:break-word;">${esc(v)}</span>
          </div>`
          )
          .join('')}
      </div>
      ${
        note
          ? `<div style="margin-top:8px; padding:6px 8px; font-size:10px; line-height:1.4; color:#cbd5e1; background:rgba(220, 38, 38, 0.15); border-left:3px solid #ef4444; border-radius:2px; word-break:break-word; overflow-wrap:break-word; box-sizing:border-box;">
              ${esc(note)}
            </div>`
          : ''
      }
    </div>
  `;
}

type TabId = 'metrics' | 'assets' | 'layers' | 'legend';

export function MapPanel({ assets, error, dispatch, hour, onHour, busy, scenarioLabel }: Props) {
  const box = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const activePopupRef = useRef<maplibregl.Popup | null>(null);

  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState<BasemapId>('satellite');
  const [terrain, setTerrain] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>('metrics');
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState<1 | 2>(1);

  // GIS layer visibility controls
  const [layers, setLayers] = useState({
    water: true,
    roads: true,
    power: false,
    demand: true,
    flow: true,
    assets: true,
  });

  const max = Math.max(0, (dispatch?.length ?? 1) - 1);
  const point = dispatch?.[Math.min(hour, max)] ?? null;
  const hourText = point ? hourLabel(point.timestamp) : '';

  // Derived, per-hour data for map layers.
  const live = useMemo(() => {
    if (!assets || !point) return null;
    const states = computeAssetStates(assets.assets, point);
    const loads = computeZoneLoads(assets.demand_zones, point);
    const flows = computeFlows(assets.energy_flow.features, states);
    const maxFlow = Math.max(1, ...Object.values(flows).map((f) => f.flowKw));

    const assetsGj = {
      ...assets.assets,
      features: assets.assets.features.map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          output_kw: states[f.properties.id]?.outputKw ?? 0,
          live_status: states[f.properties.id]?.status ?? 'idle',
        },
      })),
    } as unknown as GJ;

    const zonesGj = {
      ...assets.demand_zones,
      features: assets.demand_zones.features.map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          current_load_kw: loads[f.properties.id] ?? 0,
        },
      })),
    } as unknown as GJ;

    const flowGj = {
      ...assets.energy_flow,
      features: assets.energy_flow.features.map((f) => {
        const fl = flows[f.properties.id];
        const kw = fl?.flowKw ?? 0;
        return {
          ...f,
          geometry:
            fl?.towardsAsset && f.geometry.type === 'LineString'
              ? { ...f.geometry, coordinates: [...(f.geometry.coordinates as number[][])].reverse() }
              : f.geometry,
          properties: {
            ...f.properties,
            flow_kw: kw,
            width: kw > 0.05 ? 1.5 + (kw / maxFlow) * 7 : 1,
            active: kw > 0.05 ? 1 : 0,
          },
        };
      }),
    } as unknown as GJ;

    return { states, assetsGj, zonesGj, flowGj };
  }, [assets, point]);

  const liveRef = useRef(live);
  const hourRef = useRef(hourText);
  const scenarioLabelRef = useRef(scenarioLabel);
  const sidebarOpenRef = useRef(sidebarOpen);
  liveRef.current = live;
  hourRef.current = hourText;
  scenarioLabelRef.current = scenarioLabel;
  sidebarOpenRef.current = sidebarOpen;

  // 1. Initialize MapLibre map with dark theme and default satellite
  useEffect(() => {
    if (!assets || !box.current || map.current) return;
    const cfg = assets.map_config;
    const bms = { ...DEFAULT_BASEMAPS, ...(cfg.basemaps ?? {}) };

    const sources: Record<string, maplibregl.RasterSourceSpecification> = {};
    const baseLayers: maplibregl.LayerSpecification[] = [
      { id: 'bg', type: 'background', paint: { 'background-color': '#0f172a' } },
    ];

    for (const id of ['satellite', 'streets']) {
      const b = bms[id];
      if (!b?.tiles?.length) continue;
      sources[`bm-${id}`] = { type: 'raster', tiles: b.tiles, tileSize: 256, attribution: b.attribution };
      baseLayers.push({
        id: `bm-${id}`,
        type: 'raster',
        source: `bm-${id}`,
        layout: { visibility: id === 'satellite' ? 'visible' : 'none' },
      });
    }

    const m = new maplibregl.Map({
      container: box.current,
      style: { version: 8, sources, layers: baseLayers },
      center: cfg.center || [73.435, 18.76],
      zoom: cfg.zoom || 11.2,
      attributionControl: { compact: true },
    });

    m.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');

    m.on('load', () => {
      const empty: GJ = { type: 'FeatureCollection', features: [] };

      // Water layer
      m.addSource('water', { type: 'geojson', data: assets.water_features as unknown as GJ });
      m.addLayer({
        id: 'water-fill',
        type: 'fill',
        source: 'water',
        filter: ['==', '$type', 'Polygon'],
        paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.45 },
      });
      m.addLayer({
        id: 'water-line',
        type: 'line',
        source: 'water',
        filter: ['==', '$type', 'LineString'],
        paint: { 'line-color': '#60a5fa', 'line-width': 1.5, 'line-opacity': 0.7 },
      });

      // Roads layer (if provided by digital-twin)
      if (assets.roads) {
        m.addSource('roads', { type: 'geojson', data: assets.roads as unknown as GJ });
        m.addLayer({
          id: 'roads-casing',
          type: 'line',
          source: 'roads',
          paint: { 'line-color': '#0f172a', 'line-width': 3.5, 'line-opacity': 0.65 },
        });
        m.addLayer({
          id: 'roads-line',
          type: 'line',
          source: 'roads',
          paint: { 'line-color': '#cbd5e1', 'line-width': 1.6, 'line-opacity': 0.85 },
        });
      }

      // Power lines
      m.addSource('lines', { type: 'geojson', data: assets.power_lines as unknown as GJ });
      m.addLayer({
        id: 'power-lines',
        type: 'line',
        source: 'lines',
        layout: { visibility: 'none' },
        paint: { 'line-color': '#94a3b8', 'line-width': 1.3, 'line-dasharray': [3, 2], 'line-opacity': 0.8 },
      });

      // Demand zones
      m.addSource('zones', { type: 'geojson', data: empty });
      m.addLayer({
        id: 'zones-fill',
        type: 'fill',
        source: 'zones',
        paint: {
          'fill-color': COLORS.demand,
          'fill-opacity': ['interpolate', ['linear'], ['get', 'current_load_kw'], 0, 0.1, 500, 0.55],
        },
      });
      m.addLayer({
        id: 'zones-line',
        type: 'line',
        source: 'zones',
        paint: { 'line-color': '#c084fc', 'line-width': 1.5, 'line-opacity': 0.8 },
      });

      // Energy flow static lines
      m.addSource('flow', { type: 'geojson', data: empty });
      m.addLayer({
        id: 'flow',
        type: 'line',
        source: 'flow',
        layout: { 'line-cap': 'round' },
        paint: {
          'line-width': ['get', 'width'],
          'line-opacity': ['case', ['==', ['get', 'active'], 1], 0.9, 0.25],
          'line-color': [
            'match',
            ['get', 'source_type'],
            'solar',
            DOT_COLORS.solar,
            'wind',
            DOT_COLORS.wind,
            'hydro',
            DOT_COLORS.hydro,
            'battery',
            DOT_COLORS.battery,
            'grid',
            DOT_COLORS.grid,
            '#94a3b8',
          ],
        },
      });

      // Animated energy flow dots source and layer
      m.addSource('flow-dots-src', { type: 'geojson', data: empty });
      m.addLayer({
        id: 'flow-dots-layer',
        type: 'circle',
        source: 'flow-dots-src',
        paint: {
          'circle-radius': ['get', 'radius'],
          'circle-color': ['get', 'color'],
          'circle-opacity': 0.95,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.2,
        },
      });

      // Energy Assets
      m.addSource('assets', { type: 'geojson', data: empty });
      m.addLayer({
        id: 'assets',
        type: 'circle',
        source: 'assets',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['get', 'capacity_kw'], 50, 7, 400, 12, 1500, 16],
          'circle-color': [
            'match',
            ['get', 'type'],
            'solar',
            DOT_COLORS.solar,
            'wind',
            DOT_COLORS.wind,
            'hydro',
            DOT_COLORS.hydro,
            'battery',
            DOT_COLORS.battery,
            'grid',
            DOT_COLORS.grid,
            DOT_COLORS.demand,
          ],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2.5,
          'circle-opacity': ['case', ['>', ['get', 'output_kw'], 0.05], 1, 0.6],
        },
      });

      // Asset click popup
      m.on('click', 'assets', (e) => {
        const f = e.features?.[0];
        if (!f || f.geometry.type !== 'Point') return;
        const p = f.properties as unknown as AssetProps;
        const st = liveRef.current?.states[p.id];
        const coords = f.geometry.coordinates as [number, number];

        if (activePopupRef.current) {
          activePopupRef.current.remove();
        }

        // Keep popup clear of bottom timeline bar, attribution, and side panel
        const canvas = m.getCanvas();
        const clickY = e.point.y;
        const clickX = e.point.x;
        let panX = 0;
        let panY = 0;

        if (clickY > canvas.height - 200) {
          panY = clickY - (canvas.height - 200);
        } else if (clickY < 120) {
          panY = clickY - 120;
        }

        if (sidebarOpenRef.current && clickX < 310) {
          panX = clickX - 310;
        }

        if (panX !== 0 || panY !== 0) {
          m.panBy([panX, panY], { duration: 300 });
        }

        const popup = new maplibregl.Popup({
          offset: 16,
          maxWidth: '310px',
          className: 'gm-dark-popup',
          focusAfterOpen: false,
        })
          .setLngLat(coords)
          .setHTML(popupHtml(p, st, hourRef.current, scenarioLabelRef.current))
          .addTo(m);

        activePopupRef.current = popup;
        popup.on('close', () => {
          activePopupRef.current = null;
        });
      });

      m.on('mouseenter', 'assets', () => {
        m.getCanvas().style.cursor = 'pointer';
      });
      m.on('mouseleave', 'assets', () => {
        m.getCanvas().style.cursor = '';
      });

      setReady(true);
    });

    map.current = m;
    return () => {
      m.remove();
      map.current = null;
      setReady(false);
    };
  }, [assets]);

  // 2. Continuous Flow Particle Animation Loop (requestAnimationFrame)
  useEffect(() => {
    let animId: number | null = null;
    let startTime = performance.now();

    const animateLoop = (now: number) => {
      const m = map.current;
      if (m && ready && liveRef.current?.flowGj) {
        const dotsSrc = m.getSource('flow-dots-src') as maplibregl.GeoJSONSource | undefined;
        if (dotsSrc) {
          const elapsed = (now - startTime) / 1000;
          const dotFeatures: GeoJSON.Feature[] = [];

          liveRef.current.flowGj.features.forEach((f) => {
            const kw = Number(f.properties?.flow_kw) || 0;
            if (kw <= 0.05) return;
            const coords = (f.geometry as GeoJSON.LineString).coordinates;
            if (!coords || coords.length < 2) return;

            const srcType = f.properties?.source_type as string;
            const dotColor = DOT_COLORS[srcType] || '#ffffff';
            const radius = Math.max(3.0, Math.min(6.5, 3.0 + kw / 120));
            const speed = 0.35 + Math.min(1.2, kw / 300);

            [0.0, 0.5].forEach((offset) => {
              const progress = (elapsed * speed + offset) % 1.0;
              const lon = coords[0][0] + (coords[1][0] - coords[0][0]) * progress;
              const lat = coords[0][1] + (coords[1][1] - coords[0][1]) * progress;
              dotFeatures.push({
                type: 'Feature',
                properties: { radius, color: dotColor },
                geometry: { type: 'Point', coordinates: [lon, lat] },
              });
            });
          });

          dotsSrc.setData({ type: 'FeatureCollection', features: dotFeatures });
        }
      }
      animId = requestAnimationFrame(animateLoop);
    };

    animId = requestAnimationFrame(animateLoop);
    return () => {
      if (animId) cancelAnimationFrame(animId);
    };
  }, [ready]);

  // 3. Update GeoJSON sources when hour or scenario changes
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !live) return;
    (m.getSource('assets') as maplibregl.GeoJSONSource | undefined)?.setData(live.assetsGj);
    (m.getSource('zones') as maplibregl.GeoJSONSource | undefined)?.setData(live.zonesGj);
    (m.getSource('flow') as maplibregl.GeoJSONSource | undefined)?.setData(live.flowGj);
  }, [live, ready]);

  // 4. Basemap switcher
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    for (const id of ['satellite', 'streets']) {
      if (m.getLayer(`bm-${id}`)) {
        m.setLayoutProperty(`bm-${id}`, 'visibility', basemap === id ? 'visible' : 'none');
      }
    }
  }, [basemap, ready]);

  // 5. 3D Terrain & Hillshade switcher
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;

    if (terrain) {
      try {
        if (!m.getSource('terrarium-dem')) {
          m.addSource('terrarium-dem', {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            encoding: 'terrarium',
            tileSize: 256,
            maxzoom: 14,
          });
        }
        if (!m.getLayer('terrarium-hillshade')) {
          const beforeId = m.getLayer('water-fill') ? 'water-fill' : undefined;
          m.addLayer(
            {
              id: 'terrarium-hillshade',
              type: 'hillshade',
              source: 'terrarium-dem',
              layout: { visibility: 'visible' },
              paint: {
                'hillshade-exaggeration': 0.25,
                'hillshade-shadow-color': 'rgba(15, 23, 42, 0.45)',
                'hillshade-highlight-color': 'rgba(255, 255, 255, 0.25)',
                'hillshade-accent-color': 'rgba(56, 189, 248, 0.15)',
                'hillshade-illumination-direction': 315,
              },
            },
            beforeId
          );
        } else {
          m.setLayoutProperty('terrarium-hillshade', 'visibility', 'visible');
        }

        if (typeof (m as any).setTerrain === 'function') {
          (m as any).setTerrain({ source: 'terrarium-dem', exaggeration: 1.0 });
        }
        m.easeTo({ pitch: 48, duration: 1000 });
      } catch (err) {
        console.warn('Could not activate 3D terrain:', err);
      }
    } else {
      try {
        if (typeof (m as any).setTerrain === 'function') {
          (m as any).setTerrain(null);
        }
        if (m.getLayer('terrarium-hillshade')) {
          m.setLayoutProperty('terrarium-hillshade', 'visibility', 'none');
        }
        m.easeTo({ pitch: 0, duration: 800 });
      } catch (err) {
        console.warn('Could not deactivate 3D terrain:', err);
      }
    }
  }, [terrain, ready]);

  // 6. GIS Layer visibility toggles
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;

    const setVis = (layerId: string, visible: boolean) => {
      if (m.getLayer(layerId)) {
        m.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
      }
    };

    setVis('water-fill', layers.water);
    setVis('water-line', layers.water);
    setVis('roads-casing', layers.roads);
    setVis('roads-line', layers.roads);
    setVis('power-lines', layers.power);
    setVis('zones-fill', layers.demand);
    setVis('zones-line', layers.demand);
    setVis('flow', layers.flow);
    setVis('flow-dots-layer', layers.flow);
    setVis('assets', layers.assets);
  }, [layers, ready]);

  // 7. Auto-play timeline simulation
  useEffect(() => {
    if (!isPlaying || max <= 0) return;
    const intervalMs = 800 / playSpeed;
    const timer = setInterval(() => {
      onHour((hour + 1) % (max + 1));
    }, intervalMs);
    return () => clearInterval(timer);
  }, [isPlaying, playSpeed, hour, max, onHour]);

  // Camera navigation helpers
  const zoomToAssets = () => {
    if (!map.current) return;
    const bbox = assets?.map_config?.asset_bbox || [73.33, 18.66, 73.66, 18.95];
    map.current.fitBounds(
      [
        [bbox[0], bbox[1]],
        [bbox[2], bbox[3]],
      ],
      { padding: 40, duration: 1200 }
    );
  };

  const zoomToRegion = () => {
    if (!map.current) return;
    const bbox = assets?.map_config?.context_bbox || [73.25, 18.6, 73.68, 18.97];
    map.current.fitBounds(
      [
        [bbox[0], bbox[1]],
        [bbox[2], bbox[3]],
      ],
      { padding: 30, duration: 1200 }
    );
  };

  const flyToAsset = (f: GeoFeature<AssetProps>) => {
    if (!map.current || f.geometry.type !== 'Point') return;
    const coords = f.geometry.coordinates as [number, number];
    const p = f.properties;
    const flyOffset: [number, number] = sidebarOpen ? [70, 30] : [0, 30];
    map.current.flyTo({ center: coords, offset: flyOffset, zoom: 13.8, speed: 1.2 });

    if (activePopupRef.current) activePopupRef.current.remove();
    const st = liveRef.current?.states[p.id];
    const popup = new maplibregl.Popup({
      offset: 16,
      maxWidth: '310px',
      className: 'gm-dark-popup',
      focusAfterOpen: false,
    })
      .setLngLat(coords)
      .setHTML(popupHtml(p, st, hourRef.current, scenarioLabelRef.current))
      .addTo(map.current);
    activePopupRef.current = popup;
  };

  // Metrics summary for the current hour
  const totalGenKw = point ? point.solar_kw + point.wind_kw + point.hydro_kw : 0;
  const rePct = point && point.load_kw > 0 ? Math.min(100, Math.max(0, ((point.load_kw - point.grid_kw) / point.load_kw) * 100)) : 0;
  const gridPct = point && point.load_kw > 0 ? Math.min(100, Math.max(0, (point.grid_kw / point.load_kw) * 100)) : 0;

  return (
    <section
      className="panel relative overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-900 text-slate-100 shadow-xl"
      aria-label="Lonavala digital twin map"
      aria-busy={busy}
    >
      <style>{`
        .gm-dark-popup {
          max-width: 310px !important;
          z-index: 25;
        }
        .gm-dark-popup .maplibregl-popup-content {
          background: rgba(15, 23, 42, 0.96) !important;
          color: #f8fafc !important;
          border: 1px solid #334155 !important;
          border-radius: 10px !important;
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6) !important;
          padding: 10px 12px !important;
          box-sizing: border-box !important;
          max-width: 310px !important;
        }
        .gm-dark-popup .maplibregl-popup-tip {
          border-top-color: rgba(15, 23, 42, 0.96) !important;
          border-bottom-color: rgba(15, 23, 42, 0.96) !important;
        }
        .gm-dark-popup .maplibregl-popup-close-button {
          color: #94a3b8 !important;
          font-size: 16px !important;
          padding: 4px 8px !important;
          top: 4px !important;
          right: 4px !important;
          line-height: 1 !important;
        }
        .gm-dark-popup .maplibregl-popup-close-button:hover {
          color: #ffffff !important;
        }
        .gm-dark-popup ::-webkit-scrollbar,
        aside ::-webkit-scrollbar {
          width: 5px;
          height: 5px;
        }
        .gm-dark-popup ::-webkit-scrollbar-track,
        aside ::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.4);
        }
        .gm-dark-popup ::-webkit-scrollbar-thumb,
        aside ::-webkit-scrollbar-thumb {
          background: #475569;
          border-radius: 3px;
        }
        .gm-dark-popup ::-webkit-scrollbar-thumb:hover,
        aside ::-webkit-scrollbar-thumb:hover {
          background: #64748b;
        }
      `}</style>

      {/* Top Header & Map Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/90 px-4 py-3 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 items-center justify-center">
              <span className="absolute h-2.5 w-2.5 animate-ping rounded-full bg-cyan-400 opacity-75"></span>
              <span className="relative h-2 w-2 rounded-full bg-cyan-500"></span>
            </span>
            <h2 className="font-display text-base font-bold text-white tracking-wide">
              Lonavala Digital Twin <span className="text-xs font-normal text-cyan-400 font-mono">GIS</span>
            </h2>
          </div>
          <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-medium text-slate-300 border border-slate-700">
            {scenarioLabel || 'Simulation'} • {hourText || '00:00'}
          </span>
        </div>

        {/* Action Controls: Views, 3D Terrain, Basemaps, Sidebar Toggle */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-medium">
          {/* Zoom Buttons */}
          <button
            type="button"
            onClick={zoomToAssets}
            title="Fit to Lonavala Energy Assets"
            className="rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-slate-200 transition-colors hover:bg-slate-700 hover:text-white"
          >
            🎯 Assets
          </button>
          <button
            type="button"
            onClick={zoomToRegion}
            title="Fit to Regional Ghats Catchment"
            className="rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-slate-200 transition-colors hover:bg-slate-700 hover:text-white"
          >
            🌐 Region
          </button>

          {/* 3D Terrain Toggle */}
          <button
            type="button"
            onClick={() => setTerrain(!terrain)}
            aria-pressed={terrain}
            className={`rounded-lg border px-2.5 py-1 transition-all ${
              terrain
                ? 'border-cyan-500 bg-cyan-500/20 text-cyan-300 font-semibold shadow-[0_0_12px_rgba(6,182,212,0.3)]'
                : 'border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
          >
            🏔️ 3D Terrain
          </button>

          <span className="mx-1 h-4 w-px bg-slate-700" />

          {/* Basemaps */}
          <div className="flex rounded-lg border border-slate-700 bg-slate-800/90 p-0.5" role="group" aria-label="Basemap selection">
            {BASEMAP_IDS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setBasemap(id)}
                className={`rounded-md px-2 py-0.5 transition-colors ${
                  basemap === id
                    ? 'bg-cyan-600 font-semibold text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {id === 'satellite' ? 'Satellite' : id === 'streets' ? 'Streets' : 'Plain'}
              </button>
            ))}
          </div>

          <span className="mx-1 h-4 w-px bg-slate-700" />

          {/* Side Panel Toggle */}
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 transition-colors ${
              sidebarOpen
                ? 'border-cyan-600 bg-slate-800 text-cyan-300'
                : 'border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
            title="Toggle side panel"
          >
            <span>{sidebarOpen ? '◀ Hide Panel' : '▶ Show Panel'}</span>
          </button>
        </div>
      </div>

      {/* Main Map Box & Overlays */}
      <div className="relative">
        <div ref={box} className={`h-[480px] w-full transition-opacity lg:h-[560px] ${busy ? 'opacity-60' : ''}`} />

        {!assets && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80 p-6 text-center text-sm text-slate-400">
            {error ? `Map data unavailable: ${error}` : 'Loading Lonavala GIS digital twin layers...'}
          </div>
        )}

        {/* Collapsible Side Panel (Original UI parity) */}
        {sidebarOpen && (
          <aside className="absolute left-3 top-3 bottom-3 z-10 flex w-72 flex-col rounded-xl border border-slate-700/80 bg-slate-900/95 p-3 shadow-2xl backdrop-blur-md">
            {/* Tabs */}
            <div className="mb-2.5 flex rounded-lg border border-slate-800 bg-slate-950 p-0.5 text-[11px] font-semibold">
              <button
                type="button"
                onClick={() => setActiveTab('metrics')}
                className={`flex-1 min-w-0 truncate rounded-md py-1 px-1 transition-colors ${
                  activeTab === 'metrics' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Metrics
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('assets')}
                className={`flex-1 min-w-0 truncate rounded-md py-1 px-1 transition-colors ${
                  activeTab === 'assets' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
                title={`Assets (${assets?.assets.features.length || 12})`}
              >
                Assets ({assets?.assets.features.length || 12})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('layers')}
                className={`flex-1 min-w-0 truncate rounded-md py-1 px-1 transition-colors ${
                  activeTab === 'layers' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Layers
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('legend')}
                className={`flex-1 min-w-0 truncate rounded-md py-1 px-1 transition-colors ${
                  activeTab === 'legend' ? 'bg-cyan-600 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Legend
              </button>
            </div>

            {/* Tab 1: Dispatch Metrics */}
            {activeTab === 'metrics' && (
              <div className="flex-1 space-y-3 overflow-y-auto pr-1 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                    <div className="text-[10px] text-slate-400">Renewable Share</div>
                    <div
                      className={`text-lg font-bold font-mono ${
                        rePct >= 80 ? 'text-emerald-400' : rePct >= 50 ? 'text-amber-400' : 'text-rose-400'
                      }`}
                    >
                      {rePct.toFixed(1)}%
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                    <div className="text-[10px] text-slate-400">Grid Import</div>
                    <div className="text-lg font-bold font-mono text-rose-400">{gridPct.toFixed(1)}%</div>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 space-y-2">
                  <div className="flex justify-between items-start gap-2 font-medium text-slate-300 min-w-0">
                    <span className="shrink-0">Total Generation:</span>
                    <span className="font-mono text-cyan-300 text-right min-w-0 break-words">{fmtKw(totalGenKw)}</span>
                  </div>
                  <div className="flex justify-between items-start gap-2 font-medium text-slate-300 min-w-0">
                    <span className="shrink-0">Demand Load:</span>
                    <span className="font-mono text-purple-300 text-right min-w-0 break-words">{point ? fmtKw(point.load_kw) : '--'}</span>
                  </div>
                  <div className="flex justify-between items-start gap-2 font-medium text-slate-300 min-w-0">
                    <span className="shrink-0">Battery Status:</span>
                    <span
                      className={`font-mono font-semibold text-right min-w-0 break-words ${
                        point && point.battery_kw > 0.05
                          ? 'text-emerald-400'
                          : point && point.battery_kw < -0.05
                          ? 'text-sky-400'
                          : 'text-slate-400'
                      }`}
                    >
                      {point
                        ? point.battery_kw > 0.05
                          ? `Discharging (${fmtKw(point.battery_kw)})`
                          : point.battery_kw < -0.05
                          ? `Charging (${fmtKw(Math.abs(point.battery_kw))})`
                          : 'Idle'
                        : '--'}
                    </span>
                  </div>
                </div>

                {/* Generation breakdown list */}
                {point && (
                  <div className="space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
                    <div className="text-[11px] font-semibold text-slate-300">Generation Sources</div>
                    <div className="flex justify-between items-center gap-2 text-slate-300 min-w-0">
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className="h-2 w-2 rounded-full" style={{ background: DOT_COLORS.solar }} /> Solar
                      </span>
                      <span className="font-mono text-right min-w-0 truncate">{fmtKw(point.solar_kw)}</span>
                    </div>
                    <div className="flex justify-between items-center gap-2 text-slate-300 min-w-0">
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className="h-2 w-2 rounded-full" style={{ background: DOT_COLORS.wind }} /> Wind
                      </span>
                      <span className="font-mono text-right min-w-0 truncate">{fmtKw(point.wind_kw)}</span>
                    </div>
                    <div className="flex justify-between items-center gap-2 text-slate-300 min-w-0">
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className="h-2 w-2 rounded-full" style={{ background: DOT_COLORS.hydro }} /> Hydro
                      </span>
                      <span className="font-mono text-right min-w-0 truncate">{fmtKw(point.hydro_kw)}</span>
                    </div>
                    <div className="flex justify-between items-center gap-2 text-slate-300 min-w-0">
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className="h-2 w-2 rounded-full" style={{ background: DOT_COLORS.grid }} /> Grid Intertie
                      </span>
                      <span className="font-mono text-right min-w-0 truncate">{fmtKw(point.grid_kw)}</span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tab 2: Assets Directory */}
            {activeTab === 'assets' && (
              <div className="flex-1 space-y-1.5 overflow-y-auto pr-1 text-xs">
                {assets?.assets.features.map((f) => {
                  const p = f.properties;
                  const st = live?.states[p.id];
                  const kw = st ? st.outputKw : 0;
                  const status = st?.status || 'idle';
                  return (
                    <div
                      key={p.id}
                      onClick={() => flyToAsset(f)}
                      className="group flex cursor-pointer items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 transition-all hover:border-cyan-500 hover:bg-slate-800 min-w-0"
                    >
                      <div className="flex flex-1 min-w-0 items-center gap-2 overflow-hidden">
                        <span
                          className="h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ background: DOT_COLORS[p.type] || '#94a3b8' }}
                        />
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <div className="truncate text-xs font-semibold text-slate-200 group-hover:text-cyan-300" title={p.name}>
                            {p.name.replace('(Simulated)', '').trim()}
                          </div>
                          <div className="truncate text-[10px] text-slate-400">
                            {p.type} • {fmtKw(p.capacity_kw)}
                          </div>
                        </div>
                      </div>
                      <div className="text-right shrink-0 min-w-[65px]">
                        <div className="font-mono text-xs font-semibold text-slate-100">{fmtKw(kw)}</div>
                        <span
                          className={`inline-block rounded px-1.5 py-0.2 text-[9px] font-bold uppercase ${
                            status === 'generating' || status === 'discharging' || (status as string) === 'active'
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                              : status === 'charging'
                              ? 'bg-sky-950 text-sky-400 border border-sky-800/60'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {status}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Tab 3: GIS Layer Toggles */}
            {activeTab === 'layers' && (
              <div className="flex-1 space-y-2 overflow-y-auto pr-1 text-xs">
                <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                  Layer Visibility
                </div>
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-slate-200 min-w-0 cursor-pointer hover:border-slate-700">
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="h-2 w-2 rounded-full shrink-0 bg-blue-500" />
                    <span className="truncate">Water Bodies (OSM)</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={layers.water}
                    onChange={(e) => setLayers({ ...layers, water: e.target.checked })}
                    className="accent-cyan-500 shrink-0"
                  />
                </label>
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-slate-200 min-w-0 cursor-pointer hover:border-slate-700">
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="h-2 w-2 rounded-full shrink-0 bg-slate-300" />
                    <span className="truncate">Road Network (OSM)</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={layers.roads}
                    onChange={(e) => setLayers({ ...layers, roads: e.target.checked })}
                    className="accent-cyan-500 shrink-0"
                  />
                </label>
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-slate-200 min-w-0 cursor-pointer hover:border-slate-700">
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="h-2 w-2 rounded-full shrink-0 bg-slate-500" />
                    <span className="truncate">Power Lines (OSM)</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={layers.power}
                    onChange={(e) => setLayers({ ...layers, power: e.target.checked })}
                    className="accent-cyan-500 shrink-0"
                  />
                </label>
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-slate-200 min-w-0 cursor-pointer hover:border-slate-700">
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="h-2 w-2 rounded-full shrink-0 bg-purple-500" />
                    <span className="truncate">Demand Zones</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={layers.demand}
                    onChange={(e) => setLayers({ ...layers, demand: e.target.checked })}
                    className="accent-cyan-500 shrink-0"
                  />
                </label>
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-slate-200 min-w-0 cursor-pointer hover:border-slate-700">
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="h-2 w-2 rounded-full shrink-0 bg-cyan-400" />
                    <span className="truncate">Dynamic Energy Flow</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={layers.flow}
                    onChange={(e) => setLayers({ ...layers, flow: e.target.checked })}
                    className="accent-cyan-500 shrink-0"
                  />
                </label>
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-slate-200 min-w-0 cursor-pointer hover:border-slate-700">
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="h-2 w-2 rounded-full shrink-0 bg-amber-400" />
                    <span className="truncate">Energy Assets</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={layers.assets}
                    onChange={(e) => setLayers({ ...layers, assets: e.target.checked })}
                    className="accent-cyan-500 shrink-0"
                  />
                </label>
              </div>
            )}

            {/* Tab 4: Legend */}
            {activeTab === 'legend' && (
              <div className="flex-1 space-y-2 overflow-y-auto pr-1 text-xs">
                <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                  Asset Types
                </div>
                {(['solar', 'wind', 'hydro', 'battery', 'grid', 'demand'] as AssetType[]).map((t) => (
                  <div key={t} className="flex items-center justify-between gap-2 py-1 text-slate-300 min-w-0">
                    <span className="flex items-center gap-2 min-w-0 truncate">
                      <span className="h-3 w-3 rounded-full shrink-0" style={{ background: DOT_COLORS[t] }} />
                      <span className="truncate">{TYPE_LABEL[t]}</span>
                    </span>
                    <span className="text-[11px] font-mono text-slate-400 shrink-0">
                      {t === 'demand' ? 'Load' : t === 'battery' ? 'Storage' : 'Generation'}
                    </span>
                  </div>
                ))}
                <div className="mt-3 border-t border-slate-800 pt-2 text-[11px] text-slate-400 space-y-1 break-words">
                  <div>• Flow line width indicates transmitted power (kW).</div>
                  <div>• Animated dots show active dynamic power flow direction.</div>
                </div>
              </div>
            )}
          </aside>
        )}
      </div>

      {/* 24-Hour Play/Pause Timeline & Interactive Playback Bar */}
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-800 bg-slate-900 px-4 py-3 text-xs">
        {/* Play/Pause Button */}
        <button
          type="button"
          onClick={() => setIsPlaying(!isPlaying)}
          disabled={!dispatch || max <= 0}
          className={`flex h-8 w-8 items-center justify-center rounded-lg border text-sm font-bold transition-colors ${
            isPlaying
              ? 'border-cyan-500 bg-cyan-600 text-white shadow-[0_0_10px_rgba(6,182,212,0.4)]'
              : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 hover:text-white'
          }`}
          title={isPlaying ? 'Pause simulation (Space)' : 'Play 24-hour simulation (Space)'}
        >
          {isPlaying ? '❚❚' : '▶'}
        </button>

        {/* Step Backward */}
        <button
          type="button"
          onClick={() => onHour((hour - 1 + (max + 1)) % (max + 1))}
          disabled={!dispatch}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700 hover:text-white"
          title="Previous hour"
        >
          ⏮
        </button>

        {/* Step Forward */}
        <button
          type="button"
          onClick={() => onHour((hour + 1) % (max + 1))}
          disabled={!dispatch}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700 hover:text-white"
          title="Next hour"
        >
          ⏭
        </button>

        {/* Speed Toggle */}
        <button
          type="button"
          onClick={() => setPlaySpeed(playSpeed === 1 ? 2 : 1)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 font-mono font-semibold text-slate-300 hover:bg-slate-700 hover:text-white"
          title="Playback speed"
        >
          {playSpeed}x
        </button>

        {/* Hour Timeline Slider */}
        <div className="flex flex-1 items-center gap-3">
          <label htmlFor="hour-slider" className="sr-only">
            Simulation hour
          </label>
          <input
            id="hour-slider"
            type="range"
            min={0}
            max={max}
            step={1}
            value={Math.min(hour, max)}
            onChange={(e) => onHour(Number(e.target.value))}
            disabled={!dispatch}
            className="h-2 flex-1 cursor-pointer accent-cyan-500"
          />
        </div>

        {/* Live Hour Timestamp Badge */}
        <span className="font-mono text-sm font-bold text-cyan-400 min-w-[50px] text-right">
          {hourText || '--:--'}
        </span>
      </div>
    </section>
  );
}
