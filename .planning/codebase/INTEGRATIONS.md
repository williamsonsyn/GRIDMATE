---
last_mapped_commit: ""
last_mapped_at: "2026-11-05"
---

# INTEGRATIONS.md — External Services & APIs

**Analysis Date:** 2026-11-05
**Project:** GridMate — Lonavala Digital Twin module

---

## External Data Sources

### OpenStreetMap / Overpass API

| Item | Detail |
|---|---|
| Purpose | Download real road network, water bodies, landuse for Lonavala testbed |
| Library | `osmnx 2.1.1` |
| Endpoint | `https://overpass-api.de/api/interpreter` (default in osmnx) |
| Called by | `digital-twin/scripts/download_osm.py` |
| Output | `digital-twin/data/raw/raw_water.geojson`, `raw_roads.geojson`, `raw_landuse.geojson` |
| License | OpenStreetMap ODbL 1.0 — attribution required in all outputs |
| Auth | None — public endpoint |
| Offline fallback | Script exits non-zero if download fails; real manual GeoJSON exports may be placed in `data/raw/` |
| Bbox queried | `(73.35, 18.72, 73.46, 18.80)` — left/bottom/right/top (OSMnx 2.x convention) |

### Nominatim Geocoding

| Item | Detail |
|---|---|
| Purpose | Verify Lonavala centre coordinates (`lat=18.7504, lon=73.4069`) |
| Library | `osmnx.geocode()` → Nominatim |
| Called by | `download_osm.py` on startup |
| Auth | None — `osmnx` manages User-Agent automatically |

---

## CDN Dependencies (Runtime, No Auth)

| Library | Version | URL |
|---|---|---|
| MapLibre GL JS | 3.6.2 | `https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js` |
| MapLibre GL CSS | 3.6.2 | `https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css` |
| CartoDB Positron GL style | latest | `https://basemaps.cartocdn.com/gl/positron-gl-style/style.json` |
| OpenStreetMap raster tiles | — | `https://{a,b}.tile.openstreetmap.org/{z}/{x}/{y}.png` (fallback) |

> All CDN resources are free, require no API key, and have ODbL / open licence.

---

## Cross-Module Data Contracts (Internal)

### dispatch.json / scenario JSON (from Member 2 or synthetic)

```json
{
  "location": "Lonavala",
  "dispatch": [
    {
      "timestamp": "2026-10-01T12:00:00",
      "solar_kw": 420.0,
      "wind_kw": 180.0,
      "hydro_kw": 250.0,
      "battery_kw": 50.0,
      "grid_kw": 0.0,
      "load_kw": 900.0,
      "curtailment_kw": 0.0,
      "battery_soc_kwh": 150.0
    }
  ],
  "metrics": {}
}
```

**Battery convention:** `battery_kw > 0` = discharging, `battery_kw < 0` = charging.

### GeoJSON property contract (assets.geojson → Member 4)

Required on every asset feature:
```json
{
  "id": "solar_01",
  "type": "solar",
  "name": "...(Simulated)",
  "capacity_kw": 300.0,
  "status": "active",
  "is_synthetic": true,
  "data_source": "synthetic_demo",
  "note": "..."
}
```
Battery assets additionally carry `capacity_kwh`.
Post-dispatch, each asset also gets: `forecast_output_kw`, `utilization_percent`, `scenario`.

---

## Absent Integrations (Planned, Not Yet Built)

| Integration | Owner | Status |
|---|---|---|
| FastAPI backend | Member 4 | Not yet scaffolded |
| Weather API (solar irradiance, wind speed) | Member 1 | Not present in repo |
| Electricity load data source | Member 1 | Not present in repo |
| PyPSA energy model | Member 2 | Not present in repo |

<!-- refreshed: 2026-11-05 -->
*Sequential in-context analysis: 2026-11-05*

