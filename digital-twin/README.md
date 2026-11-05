# GridMate — Member 3: Lonavala Digital Twin & GIS Module

> **"From Weather to Watts, Intelligently."**  
> Testbed: Lonavala & Khandala, Maharashtra, India  
> - Regional Context BBox: `[73.25, 18.62, 73.62, 18.90]` (Water & Roads GIS layers)  
> - Asset Core BBox: `[73.33, 18.68, 73.48, 18.81]` (Energy Assets & Demand Zones)  
> Module: `digital-twin/` (Member 3)  
> Stack: Python 3.12, GeoPandas, Shapely, PyProj, MapLibre GL JS, pytest

---

## 1. Overview

The **Lonavala Digital Twin & GIS** module provides the geospatial topology, real OpenStreetMap features, energy asset placement, and interactive visualization layer for GridMate. It models the regional geography of the Lonavala-Khandala ghats and surrounding water catchments, places renewable generation assets plausibly across terrain, shapes realistic demand clusters, and demonstrates dynamic power flows across baseline and stress weather scenarios.

---

## 2. Real OSM vs. Synthetic Data Breakdown

In strict compliance with Section 15 of `GRIDMATE_ARCHITECTURE.md`, real OpenStreetMap geometries and synthetic prototype infrastructure are strictly distinguished:

| Layer / Feature | Nature | Source / Attribution | Details & Verification |
|---|---|---|---|
| **Water Bodies & Reservoirs** (`water_features.geojson`) | **Real** | © OpenStreetMap contributors (ODbL 1.0) via manual overpass-turbo export | Regional water bodies clipped to `context_bbox`: Valvan Lake / Dam, Bhushi Dam Reservoir, Tungarli Lake, Khandala Lake, Tata Dam, Pavana Lake, Shirota Lake, and headwater river/stream networks. Verified high-vertex polygon geometries. `is_synthetic: false`. |
| **Road Network** (`roads.geojson`) | **Real** | © OpenStreetMap contributors (ODbL 1.0) via manual overpass-turbo export | Regional corridors clipped to `context_bbox`: Mumbai-Pune Expressway, NH48 trunk highway corridors, Khandala connectors, secondary roads. `is_synthetic: false`. |
| **Energy Assets** (`assets.geojson`) | **Synthetic** | GridMate Prototype Model (`data_source: synthetic_demo`) | Plausibly sited inside `asset_bbox`: solar on sunny elevated plateaus away from roads/water, wind on elevated ridges (Khandala Ridge & Duke's Nose Ridge), hydro on the real shoreline of Valvan Dam reservoir ($39.1\text{ m}$ from water edge, strictly outside water), battery near 110kV substation intertie, central municipal demand hub. All features carry `is_synthetic: true`. |
| **Demand Zones** (`demand_zones.geojson`) | **Synthetic** | GridMate Prototype Model shaped by real OSM landuse | Shaped using real landuse boundaries inside `asset_bbox`: Lonavala Town Center & Residential (400 kW), Khandala Tourism Corridor (250 kW), Valvan Industrial Pocket (180 kW), and Bhushi Recreation Sector (70 kW). Total base load: **900.0 kW**. |
| **Energy Flow Topology** (`energy_flow_template.geojson`) | **Synthetic** | GridMate Dynamic Flow Topology | Radial distribution topology from generation sources to the central demand hub and battery node inside `asset_bbox`. |
| **Scenarios & Dispatch** (`data/scenarios/*.json`) | **Synthetic** | GridMate Dispatch Optimization Simulation | Validated dispatch schedules for 5 canonical weather/load scenarios. |

All synthetic features include the mandatory disclaimer contract:
```json
{
  "is_synthetic": true,
  "data_source": "synthetic_demo",
  "note": "Simulated prototype asset. Coordinates are illustrative, not verified real infrastructure."
}
```

---

## 3. Directory Structure

```text
digital-twin/
├── data/
│   ├── raw/                           # Real OpenStreetMap GeoJSON exports (gitignored)
│   │   ├── raw_water.geojson          # 198 features across regional context
│   │   ├── raw_roads.geojson          # 477 highway features across regional context
│   │   ├── raw_landuse.geojson        # 4 zonal polygons for Lonavala-Khandala
│   │   └── metadata.json              # Provenance, bboxes, feature counts, export date
│   ├── assets.geojson                 # 8 clean energy assets (Point features, EPSG:4326)
│   ├── demand_zones.geojson           # 4 demand zones (total base load 900 kW, EPSG:4326)
│   ├── water_features.geojson         # 107 clean water polygons & lines (< 2 MB)
│   ├── roads.geojson                  # 474 filtered road network segments (< 2 MB)
│   ├── energy_flow_template.geojson   # Topology lines from supply assets to demand hub
│   ├── sample_dispatch.json           # 24-hour reference dispatch profile
│   └── scenarios/                     # 5 canonical scenarios
│       ├── normal.json                # Normal Day (100% RE baseline)
│       ├── cloudy.json                # Cloudy Day (low solar, battery discharge + grid)
│       ├── heavy_monsoon.json         # Heavy Monsoon (max 400 kW hydro, battery charging, low solar)
│       ├── high_wind.json             # High Wind (peak ridge wind, battery charging)
│       └── peak_demand.json           # Peak Demand (evening 1.25 MW load)
├── scripts/
│   ├── process_data.py                # Cleans raw OSM GeoJSON, clips to context_bbox, outputs clean layers
│   ├── generate_assets.py             # Siting algorithm for assets, demand zones, and flow lines
│   └── create_sample_scenarios.py     # Generates scenario JSONs with physical conservation
├── src/
│   ├── __init__.py
│   └── map_utils.py                   # Python engine: load_dispatch, apply_dispatch, build_energy_flow
├── map/
│   ├── index.html                     # Standalone MapLibre GL JS interactive demo with Satellite switcher
│   ├── map_config.json                # Dual bboxes, center, zoom, basemaps, layer definitions
│   ├── applyDispatch.js               # Zero-dependency JS dispatch engine for Member 4 (React)
│   └── styles/                        # MapLibre styling definitions
├── tests/
│   ├── __init__.py
│   └── test_digital_twin.py           # 22 automated pytest tests (dual bbox, spatial, conservation, JS parity)
├── logs/                              # Execution and test logs (gitignored)
├── requirements.txt                   # Python dependencies
└── README.md                          # This specification document
```

---

## 4. Key Contracts & Conventions

### 4.1 Dual Bounding Boxes
All coordinates are strictly **EPSG:4326** in `[longitude, latitude]` format:
- **`context_bbox`**: `[73.25, 18.62, 73.62, 18.90]` — Encloses regional water catchments (Pavana Lake, Shirota Lake, Tata Dam) and regional road networks.
- **`asset_bbox`**: `[73.33, 18.68, 73.48, 18.81]` — Strict boundary for synthetic energy assets, demand zones, and local distribution lines.

### 4.2 Exact Property Names (Architecture Contract)
```text
solar_kw           : float >= 0.0
wind_kw            : float >= 0.0
hydro_kw           : float >= 0.0
battery_kw         : float (signed, see convention below)
grid_kw            : float >= 0.0
load_kw            : float > 0.0
curtailment_kw     : float >= 0.0
battery_soc_kwh    : float, between 0.0 and capacity_kwh (1000.0)
```

### 4.3 Battery Sign Convention
```text
battery_kw > 0 : Discharging (supplying power to load)
battery_kw < 0 : Charging (absorbing surplus power from generation)
battery_kw = 0 : Idle (neither charging nor discharging)
```
Physical energy conservation equation enforced across all scenarios:
$$(P_{\text{solar}} + P_{\text{wind}} + P_{\text{hydro}} + P_{\text{battery}} + P_{\text{grid}}) = (P_{\text{load}} + P_{\text{curtailment}}) \pm 0.01\text{ kW}$$

---

## 5. GeoJSON Property Contract for Member 4 (FastAPI + React)

Member 4 can consume the GeoJSON files directly from `digital-twin/data/` or via FastAPI endpoints without client-side Python:

### 5.1 Assets Layer (`assets.geojson`)
Each feature in `assets.geojson` contains:
```typescript
interface AssetProperties {
  id: string;               // e.g. "solar_01", "hydro_01", "battery_01"
  type: "solar" | "wind" | "hydro" | "battery" | "grid" | "demand";
  name: string;             // Must contain "(Simulated)", e.g. "Hydro Plant 01 - Valvan Shore Powerhouse (Simulated)"
  capacity_kw: number;      // Nameplate capacity
  capacity_kwh?: number;    // Present on battery (1000.0 kWh)
  status: "active" | "idle" | "charging" | "discharging" | "not_supplying";
  is_synthetic: true;
  data_source: "synthetic_demo";
  note: string;
}
```

### 5.2 Dynamic Client-Side Dispatch Binding (`applyDispatch.js`)
Member 4's React frontend can import `digital-twin/map/applyDispatch.js` (vanilla ES5/ES6 / UMD, zero runtime dependencies) to update asset statuses and dynamic flow lines when the optimizer dispatches new schedules:

```javascript
import GridMateDispatch from './applyDispatch.js';

// 1. Parse dispatch row from optimizer scenario
const row = GridMateDispatch.parseDispatchRow(scenarioData, 0);

// 2. Proportionally allocate power to assets
const updatedAssets = GridMateDispatch.applyDispatch(rawAssetsGeoJSON, row, "normal");

// 3. Generate dynamic line-weighted flow lines into demand hub
const dynamicFlows = GridMateDispatch.buildEnergyFlow(row, rawAssetsGeoJSON);

// 4. Update MapLibre / Leaflet data sources
map.getSource('assets-src').setData(updatedAssets);
map.getSource('flow-src').setData(dynamicFlows);
```

---

## 6. How to Run the Interactive Map Demo

The map demo is a standalone HTML5 + MapLibre GL JS client that requires no build step and no API key.

```bash
# 1. From the repository root, enter digital-twin:
cd digital-twin

# 2. Start a local HTTP server:
python -m http.server 8000

# 3. Open in your browser:
# http://localhost:8000/map/
```

### Key UI Features in the Demo:
1. **Basemap Switcher**: Toggle between:
   - **Streets**: OpenStreetMap raster tiles (default).
   - **Satellite**: High-resolution Esri World Imagery (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`).
   - **Plain Dark**: Offline fallback background (`#0f172a`).
   Vector layers (water with bright cyan outline, roads with high-contrast dark casing, asset halos) remain layered on top seamlessly.
2. **Dual-View Navigation**:
   - Initial load bounds to the entire `context_bbox` region so all major lakes and highway corridors are visible.
   - **📍 Zoom to Assets** button: Smoothly flies to the Lonavala-Khandala energy cluster.
   - **🗺️ Regional View** button: Smoothly zooms back out to the full context area.
3. **Collapsible Right Panel**: Click the `◀` / `▶` toggle button to slide the control panel off-screen for an unobstructed full-screen map view.
4. **Decluttered Zoom Labels**: Asset labels only become visible at zoom $\ge 13$ (`minzoom: 13`), preventing text collisions when zoomed out.
5. **Interactive Scenario Dropdown**: Seamlessly switches between `Normal Day`, `Cloudy Day`, `Heavy Monsoon`, `High Wind`, and `Peak Demand`.
6. **Distinct Heavy Monsoon Mode**:
   - Hydro generation surges to 100% capacity (**400 kW**), showing maximum blue flow line width.
   - Solar drops to near-zero (**20 kW**).
   - Battery switches to charging mode (**-60 kW**, cyan reverse flow line).
   - Grid intertie activates (**330 kW**, red supply line).
7. **Compliance Badge & Attribution**: Prominently displays the red `"Simulated prototype assets"` badge, dynamic Esri attribution when Satellite is active, and `© OpenStreetMap contributors`.

---

## 7. How to Regenerate Data from Raw OSM Exports

To regenerate all processed GIS layers, assets, demand zones, flow templates, and scenario schedules from the real raw OpenStreetMap exports:

```bash
# Step 1: Process and clean real OSM data (clip to context_bbox, simplify, validate)
python scripts/process_data.py

# Step 2: Generate assets, demand zones (from raw landuse), and energy flow template
python scripts/generate_assets.py

# Step 3: Generate validated 5-scenario dispatch files and 24h sample dispatch
python scripts/create_sample_scenarios.py
```

*(Note: Do NOT execute `download_osm.py`; the raw exports in `digital-twin/data/raw/` serve as the verified ground truth).*

---

## 8. Automated Testing & Verification

Run the test suite using pytest:

```bash
python -m pytest digital-twin/tests/ -v
```

The test suite validates:
1. **Dual BBox standards**:
   - Context layers (`water_features.geojson`, `roads.geojson`) strictly inside `context_bbox` (`[73.25, 18.62, 73.62, 18.90]`).
   - Assets and demand zones strictly inside `asset_bbox` (`[73.33, 18.68, 73.48, 18.81]`).
2. **Real OSM verification**: Metadata provenance is manual OSM export; water polygons have verified vertex counts ($\ge 5$ vertices) and include all key named lakes (Valvan, Bhushi, Tungarli, Khandala, Pavana, Tata).
3. **Spatial asset rules**:
   - No asset intersects or falls inside any water polygon.
   - Hydro asset sits on the real shoreline of Valvan Dam reservoir ($\le 100\text{ m}$ from the water polygon boundary).
   - Wind assets are located on high ground in the Lonavala-Khandala ridge.
4. **Energy conservation**: Supply + battery discharge + grid import equals load + curtailment within $0.5\text{ kW}$ across all scenarios. Battery SOC remains bounded in $[0, 1000\text{ kWh}]$.
5. **Python vs. JavaScript parity**: Cross-validates `src/map_utils.py` and `map/applyDispatch.js` outputs across all 5 scenarios using Node.js to ensure $100\%$ consistency.
6. **Coordinate standards**: All coordinates are in valid `[longitude, latitude]` order.
