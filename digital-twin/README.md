# GridMate — Member 3: Lonavala Digital Twin & GIS Module

> **"From Weather to Watts, Intelligently."**  
> Testbed: Lonavala & Khandala, Maharashtra, India (Bbox: `[73.33, 18.68, 73.48, 18.81]`, Center: `[73.4070, 18.7520]`)  
> Module: `digital-twin/` (Member 3)  
> Stack: Python 3.12, GeoPandas, Shapely, PyProj, MapLibre GL JS, pytest

---

## 1. Overview

The **Lonavala Digital Twin & GIS** module provides the geospatial topology, real OpenStreetMap features, energy asset placement, and interactive visualization layer for GridMate. It models the actual geography of Lonavala and Khandala, places renewable generation assets plausibly across terrain, shapes realistic demand clusters, and demonstrates dynamic power flows across baseline and stress weather scenarios.

---

## 2. Real OSM vs. Synthetic Data Breakdown

In strict compliance with Section 15 of `GRIDMATE_ARCHITECTURE.md`, real OpenStreetMap geometries and synthetic prototype infrastructure are strictly distinguished:

| Layer / Feature | Nature | Source / Attribution | Details & Verification |
|---|---|---|---|
| **Water Bodies & Reservoirs** (`water_features.geojson`) | **Real** | © OpenStreetMap contributors (ODbL 1.0) via manual overpass-turbo export | Real lakes and reservoirs: Valvan Lake / Dam, Bhushi Dam Reservoir, Tungarli Lake, Khandala Lake, Tata Dam, Pavana Lake, plus headwater streams (Ulhas, Amba). Verified high-vertex polygon geometries. `is_synthetic: false`. |
| **Road Network** (`roads.geojson`) | **Real** | © OpenStreetMap contributors (ODbL 1.0) via manual overpass-turbo export | Mumbai-Pune Expressway, NH48 trunk highway corridors, Khandala connectors, secondary roads. `is_synthetic: false`. |
| **Energy Assets** (`assets.geojson`) | **Synthetic** | GridMate Prototype Model (`data_source: synthetic_demo`) | Plausibly sited: solar on sunny elevated plateaus away from roads/water, wind on elevated ridges (Khandala Ridge & Duke's Nose Ridge), hydro on the real shoreline of Valvan Dam reservoir (< 100m, strictly outside water), battery near 110kV substation intertie, central municipal demand hub. All features carry `is_synthetic: true`. |
| **Demand Zones** (`demand_zones.geojson`) | **Synthetic** | GridMate Prototype Model shaped by real OSM landuse | Shaped using real landuse boundaries from `raw_landuse.geojson`: Lonavala Town Center & Residential (400 kW), Khandala Tourism Corridor (250 kW), Valvan Industrial Pocket (180 kW), and Bhushi Recreation Sector (70 kW). Total base load: **900.0 kW**. |
| **Energy Flow Topology** (`energy_flow_template.geojson`) | **Synthetic** | GridMate Dynamic Flow Topology | Radial distribution topology from generation sources to the central demand hub and battery node. |
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
│   │   ├── raw_water.geojson          # 117 features (44 water polygons + 73 water lines)
│   │   ├── raw_roads.geojson          # 196 highway features (motorway, trunk, secondary)
│   │   ├── raw_landuse.geojson        # 4 zonal polygons for Lonavala-Khandala
│   │   └── metadata.json              # Provenance: manual overpass-turbo export, OSM ODbL
│   ├── assets.geojson                 # 8 clean energy assets (Point features, EPSG:4326)
│   ├── demand_zones.geojson           # 4 demand zones (total base load 900 kW, EPSG:4326)
│   ├── water_features.geojson         # Cleaned water polygons & lines (< 2 MB)
│   ├── roads.geojson                  # Filtered major road network (< 2 MB)
│   ├── energy_flow_template.geojson   # Topology lines from supply assets to demand hub
│   ├── sample_dispatch.json           # 24-hour reference dispatch profile
│   └── scenarios/                     # 5 canonical scenarios
│       ├── normal.json                # Normal Day (100% RE baseline)
│       ├── cloudy.json                # Cloudy Day (low solar, battery discharge + grid)
│       ├── heavy_monsoon.json         # Heavy Monsoon (max 400 kW hydro, battery charging, low solar)
│       ├── high_wind.json             # High Wind (peak ridge wind, battery charging)
│       └── peak_demand.json           # Peak Demand (evening 1.25 MW load)
├── scripts/
│   ├── process_data.py                # Cleans raw OSM GeoJSON, clips to bbox, outputs clean layers
│   ├── generate_assets.py             # Siting algorithm for assets, demand zones, and flow lines
│   └── create_sample_scenarios.py     # Generates scenario JSONs with physical conservation
├── src/
│   ├── __init__.py
│   └── map_utils.py                   # Python engine: load_dispatch, apply_dispatch, build_energy_flow
├── map/
│   ├── index.html                     # Standalone MapLibre GL JS interactive demo
│   ├── map_config.json                # Map configuration, bbox, colors, layer definitions
│   ├── applyDispatch.js               # Zero-dependency JS dispatch engine for Member 4 (React)
│   └── styles/                        # MapLibre styling definitions
├── tests/
│   ├── __init__.py
│   └── test_digital_twin.py           # 22 automated pytest tests (spatial, conservation, JS parity)
├── logs/                              # Execution and test logs (gitignored)
├── requirements.txt                   # Python dependencies
└── README.md                          # This specification document
```

---

## 4. Key Contracts & Conventions

### 4.1 Coordinate Format
All coordinates are strictly **EPSG:4326** in `[longitude, latitude]` format:
- Bounding Box: `[73.33, 18.68, 73.48, 18.81]`
- Geographic Center: `[73.4070, 18.7520]` (Lonavala Core)

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
1. **Cluster Fit on Load**: Automatically bounds and fits to the asset cluster coordinates without manual panning.
2. **Decluttered Zoom Labels**: Asset labels only become visible at zoom $\ge 13$ (`minzoom: 13`), preventing text collisions when zoomed out.
3. **Interactive Scenario Dropdown**: Seamlessly switches between `Normal Day`, `Cloudy Day`, `Heavy Monsoon`, `High Wind`, and `Peak Demand`.
4. **Distinct Heavy Monsoon Mode**:
   - Hydro generation surges to 100% capacity (**400 kW**), showing maximum blue flow line width.
   - Solar drops to near-zero (**20 kW**).
   - Battery switches to charging mode (**-60 kW**, cyan reverse flow line).
   - Grid intertie activates (**330 kW**, red supply line).
5. **Tile Fallback Background**: Plain `#0f172a` slate background ensures water, roads, demand zones, and energy assets remain fully visible even if external tile servers are unreachable.
6. **Layer Visibility Toggles**: Granular toggles for Assets, Flow Lines, Demand Zones, Water Bodies, and Roads.
7. **Asset Legend**: Color-coded indicator matching all 6 asset types and flow lines.
8. **Compliance Badge**: Prominently displays the red `"Simulated prototype assets"` badge and `© OpenStreetMap contributors` attribution.

---

## 7. How to Regenerate Data from Raw OSM Exports

To regenerate all processed GIS layers, assets, demand zones, flow templates, and scenario schedules from the real raw OpenStreetMap exports:

```bash
# Ensure virtual environment is active or use digital-twin/.venv/Scripts/python

# Step 1: Process and clean real OSM data (clip, simplify, validate)
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
1. **Real OSM verification**: Metadata provenance is manual OSM export; `water_features.geojson` and `roads.geojson` have `is_synthetic: false`, no fallback flags, and water polygons possess verified vertex counts ($\ge 5$ vertices).
2. **Spatial asset rules**:
   - No asset intersects or falls inside any water polygon.
   - Hydro asset sits on the real shoreline of Valvan Dam reservoir ($\le 100\text{ m}$ from the water polygon boundary).
   - Wind assets are located on high ground in the Lonavala-Khandala ridge ($73.34 \le \text{lon} \le 73.39$, $18.70 \le \text{lat} \le 18.80$).
   - All assets fall strictly within the testbed bounding box `[73.33, 18.68, 73.48, 18.81]`.
3. **Energy conservation**: Supply + battery discharge + grid import equals load + curtailment within $0.5\text{ kW}$ across all scenarios. Battery SOC remains bounded in $[0, 1000\text{ kWh}]$.
4. **Python vs. JavaScript parity**: Cross-validates `src/map_utils.py` and `map/applyDispatch.js` outputs across all 5 scenarios using Node.js to ensure $100\%$ consistency.
5. **Coordinate standards**: All coordinates are in valid `[longitude, latitude]` order.
