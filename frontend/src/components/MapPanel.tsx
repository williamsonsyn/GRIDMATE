import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { AssetProps, AssetsResponse, AssetType, DispatchPoint } from '../types/api';
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
const BASEMAP_IDS = ['streets', 'satellite', 'plain'] as const;
type BasemapId = (typeof BASEMAP_IDS)[number];

const DEFAULT_BASEMAPS: Record<string, { name: string; tiles: string[]; attribution?: string }> = {
  streets: { name: 'Streets', tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'], attribution: '© OpenStreetMap contributors' },
  satellite: {
    name: 'Satellite',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
  },
};

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function popupHtml(p: AssetProps, st: AssetState | undefined, hourText: string): string {
  const out = st ? fmtKw(st.outputKw) : 'n/a';
  const rows: [string, string][] = [
    ['Type', TYPE_LABEL[p.type]],
    ['Installed capacity', fmtKw(p.capacity_kw)],
    [`Output at ${hourText}`, out],
    ['Status', st ? st.status : 'n/a'],
  ];
  if (p.location_source) rows.push(['Location source', p.location_source === 'osm' ? 'Real OSM site' : p.location_source]);
  const note = p.is_synthetic ? 'Simulated prototype asset. Capacity and output are illustrative, not measured.' : p.note ?? '';
  return `<div style="min-width:210px"><strong style="font-size:14px">${esc(p.name)}</strong>
    <table style="margin-top:8px;font-size:12px;width:100%">${rows.map(([k, v]) =>
      `<tr><td style="color:#6B7A85;padding:2px 10px 2px 0">${esc(k)}</td><td style="text-align:right">${esc(v)}</td></tr>`).join('')}</table>
    ${note ? `<p style="margin:8px 0 0;font-size:11px;color:#6B7A85">${esc(note)}</p>` : ''}</div>`;
}

export function MapPanel({ assets, error, dispatch, hour, onHour, busy, scenarioLabel }: Props) {
  const box = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState<BasemapId>('streets');
  const point = dispatch?.[Math.min(hour, (dispatch?.length ?? 1) - 1)] ?? null;
  const hourText = point ? hourLabel(point.timestamp) : '';

  // Derived, per-hour data for the map layers.
  const live = useMemo(() => {
    if (!assets || !point) return null;
    const states = computeAssetStates(assets.assets, point);
    const loads = computeZoneLoads(assets.demand_zones, point);
    const flows = computeFlows(assets.energy_flow.features, states);
    const maxFlow = Math.max(1, ...Object.values(flows).map((f) => f.flowKw));
    const assetsGj = {
      ...assets.assets,
      features: assets.assets.features.map((f) => ({
        ...f, properties: { ...f.properties, output_kw: states[f.properties.id]?.outputKw ?? 0, live_status: states[f.properties.id]?.status ?? 'idle' },
      })),
    } as unknown as GJ;
    const zonesGj = {
      ...assets.demand_zones,
      features: assets.demand_zones.features.map((f) => ({
        ...f, properties: { ...f.properties, current_load_kw: loads[f.properties.id] ?? 0 },
      })),
    } as unknown as GJ;
    const flowGj = {
      ...assets.energy_flow,
      features: assets.energy_flow.features.map((f) => {
        const fl = flows[f.properties.id];
        const kw = fl?.flowKw ?? 0;
        return {
          ...f,
          geometry: fl?.towardsAsset && f.geometry.type === 'LineString'
            ? { ...f.geometry, coordinates: [...(f.geometry.coordinates as number[][])].reverse() } : f.geometry,
          properties: { ...f.properties, flow_kw: kw, width: kw > 0.05 ? 1.5 + (kw / maxFlow) * 7 : 1, active: kw > 0.05 ? 1 : 0 },
        };
      }),
    } as unknown as GJ;
    return { states, assetsGj, zonesGj, flowGj };
  }, [assets, point]);

  const liveRef = useRef(live);
  const hourRef = useRef(hourText);
  liveRef.current = live;
  hourRef.current = hourText;

  // Create the map once the digital-twin data has arrived.
  useEffect(() => {
    if (!assets || !box.current || map.current) return;
    const cfg = assets.map_config;
    const bms = { ...DEFAULT_BASEMAPS, ...(cfg.basemaps ?? {}) };
    const sources: Record<string, maplibregl.RasterSourceSpecification> = {};
    const layers: maplibregl.LayerSpecification[] = [
      { id: 'bg', type: 'background', paint: { 'background-color': '#dfe6e2' } },
    ];
    for (const id of ['streets', 'satellite']) {
      const b = bms[id];
      if (!b?.tiles?.length) continue;
      sources[`bm-${id}`] = { type: 'raster', tiles: b.tiles, tileSize: 256, attribution: b.attribution };
      layers.push({ id: `bm-${id}`, type: 'raster', source: `bm-${id}`, layout: { visibility: id === 'streets' ? 'visible' : 'none' } });
    }
    const m = new maplibregl.Map({
      container: box.current, style: { version: 8, sources, layers },
      center: cfg.center, zoom: cfg.zoom, attributionControl: { compact: true },
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    m.on('load', () => {
      const empty: GJ = { type: 'FeatureCollection', features: [] };
      m.addSource('water', { type: 'geojson', data: assets.water_features as unknown as GJ });
      m.addSource('zones', { type: 'geojson', data: empty });
      m.addSource('lines', { type: 'geojson', data: assets.power_lines as unknown as GJ });
      m.addSource('flow', { type: 'geojson', data: empty });
      m.addSource('assets', { type: 'geojson', data: empty });
      m.addLayer({ id: 'water-fill', type: 'fill', source: 'water', filter: ['==', '$type', 'Polygon'], paint: { 'fill-color': '#3B82F6', 'fill-opacity': 0.35 } });
      m.addLayer({ id: 'water-line', type: 'line', source: 'water', filter: ['==', '$type', 'LineString'], paint: { 'line-color': '#3B82F6', 'line-width': 1.2, 'line-opacity': 0.6 } });
      m.addLayer({
        id: 'zones-fill', type: 'fill', source: 'zones',
        paint: { 'fill-color': COLORS.demand, 'fill-opacity': ['interpolate', ['linear'], ['get', 'current_load_kw'], 0, 0.08, 500, 0.5] },
      });
      m.addLayer({ id: 'zones-line', type: 'line', source: 'zones', paint: { 'line-color': COLORS.demand, 'line-width': 1.2 } });
      m.addLayer({ id: 'power-lines', type: 'line', source: 'lines', paint: { 'line-color': '#64748b', 'line-width': 1, 'line-dasharray': [3, 2], 'line-opacity': 0.7 } });
      m.addLayer({
        id: 'flow', type: 'line', source: 'flow', layout: { 'line-cap': 'round' },
        paint: {
          'line-width': ['get', 'width'],
          'line-opacity': ['case', ['==', ['get', 'active'], 1], 0.9, 0.35],
          'line-color': ['match', ['get', 'source_type'], 'solar', COLORS.solar, 'wind', COLORS.wind, 'hydro', COLORS.hydro, 'battery', COLORS.battery, 'grid', COLORS.grid, '#94a3b8'],
        },
      });
      m.addLayer({
        id: 'assets', type: 'circle', source: 'assets',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['get', 'capacity_kw'], 50, 7, 400, 12, 1500, 16],
          'circle-color': ['match', ['get', 'type'], 'solar', COLORS.solar, 'wind', COLORS.wind, 'hydro', COLORS.hydro, 'battery', COLORS.battery, 'grid', COLORS.grid, COLORS.demand],
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5,
          'circle-opacity': ['case', ['>', ['get', 'output_kw'], 0.05], 1, 0.55],
        },
      });
      m.on('click', 'assets', (e) => {
        const f = e.features?.[0];
        if (!f || f.geometry.type !== 'Point') return;
        const p = f.properties as unknown as AssetProps;
        const st = liveRef.current?.states[p.id];
        new maplibregl.Popup({ offset: 14 }).setLngLat(f.geometry.coordinates as [number, number])
          .setHTML(popupHtml(p, st, hourRef.current)).addTo(m);
      });
      m.on('mouseenter', 'assets', () => { m.getCanvas().style.cursor = 'pointer'; });
      m.on('mouseleave', 'assets', () => { m.getCanvas().style.cursor = ''; });
      setReady(true);
    });
    map.current = m;
    return () => { m.remove(); map.current = null; setReady(false); };
  }, [assets]);

  // Push per-hour data into the map whenever the scenario or hour changes.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !live) return;
    (m.getSource('assets') as maplibregl.GeoJSONSource | undefined)?.setData(live.assetsGj);
    (m.getSource('zones') as maplibregl.GeoJSONSource | undefined)?.setData(live.zonesGj);
    (m.getSource('flow') as maplibregl.GeoJSONSource | undefined)?.setData(live.flowGj);
  }, [live, ready]);

  // Basemap switcher.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    for (const id of ['streets', 'satellite']) {
      if (m.getLayer(`bm-${id}`)) m.setLayoutProperty(`bm-${id}`, 'visibility', basemap === id ? 'visible' : 'none');
    }
  }, [basemap, ready]);

  const types: AssetType[] = ['solar', 'wind', 'hydro', 'battery', 'grid', 'demand'];
  const max = Math.max(0, (dispatch?.length ?? 1) - 1);

  return (
    <section className="panel overflow-hidden" aria-label="Lonavala digital twin map" aria-busy={busy}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Lonavala digital twin</h2>
          <p className="text-xs text-ink-mute">
            {scenarioLabel ? `${scenarioLabel} at ${hourText}` : 'Waiting for simulation'}. Click an asset for details.
          </p>
        </div>
        <div className="flex gap-1" role="group" aria-label="Basemap">
          {BASEMAP_IDS.map((id) => (
            <button key={id} type="button" onClick={() => setBasemap(id)} aria-pressed={basemap === id}
              className={`rounded-md border px-2.5 py-1 text-xs font-medium ${basemap === id ? 'border-ink bg-ink text-white' : 'border-line text-ink-soft hover:bg-paper'}`}>
              {id === 'plain' ? 'Plain' : id === 'streets' ? 'Streets' : 'Satellite'}
            </button>
          ))}
        </div>
      </div>

      <div className="relative">
        <div ref={box} className={`h-[420px] w-full transition-opacity lg:h-[520px] ${busy ? 'opacity-60' : ''}`} />
        {!assets && (
          <div className="absolute inset-0 flex items-center justify-center bg-paper/90 p-6 text-center text-sm text-ink-soft">
            {error ? `Map data unavailable: ${error}` : 'Loading Lonavala map data...'}
          </div>
        )}
        <ul className="absolute bottom-3 left-3 rounded-lg bg-white/95 px-3 py-2 text-xs shadow-sm">
          {types.map((t) => (
            <li key={t} className="flex items-center gap-2 py-0.5">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: COLORS[t] }} />{TYPE_LABEL[t]}
            </li>
          ))}
          <li className="mt-1 border-t border-line pt-1 text-ink-mute">Line width = power flow</li>
        </ul>
      </div>

      <div className="flex items-center gap-4 border-t border-line px-4 py-3">
        <label htmlFor="hour" className="text-sm font-medium">Hour</label>
        <input id="hour" type="range" min={0} max={max} step={1} value={Math.min(hour, max)}
          onChange={(e) => onHour(Number(e.target.value))} disabled={!dispatch} className="h-2 flex-1 accent-teal-700" />
        <span className="num w-14 text-right text-sm font-semibold">{hourText || '--:--'}</span>
      </div>
    </section>
  );
}
