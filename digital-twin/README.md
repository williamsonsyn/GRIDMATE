# GridMate — Member 3: Lonavala Digital Twin & GIS Module

> **"From Weather to Watts, Intelligently."**  
> Testbed: Lonavala & Khandala, Maharashtra, India  
> - Regional Context BBox: `[73.25, 18.62, 73.62, 18.92]` (Water, Roads & Power Lines GIS layers)  
> - Asset Core BBox: `[73.33, 18.70, 73.61, 18.91]` (Energy Assets, Demand Zones & Wind Ridge)  
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
| **Power Transmission Lines** (`power_lines.geojson`) | **Real** | © OpenStreetMap contributors (ODbL 1.0) via manual overpass-turbo export (`raw_power.geojson`) | Regional high-voltage power transmission lines and cables clipped to `context_bbox` (< 1 MB). `is_synthetic: false`. |
| **Energy Assets** (`assets.geojson`) | **Synthetic** | GridMate Prototype Model (`data_source: synthetic_demo`) | Plausibly sited inside `asset_bbox`: solar on sunny elevated plateaus, wind clustered from 28 real OSM wind turbines on the ridge (`location_source: "osm"`), hydro on the real shoreline of Valvan Dam reservoir ($39.1\text{ m}$ from water edge, strictly outside water), grid intertie sited next to nearest real substation (`location_source: "osm_nearest_substation"`), battery adjacent to substation, central municipal demand hub. All features carry `is_synthetic: true` for capacity/output and explicit `location_source` provenance. |
| **Demand Zones** (`demand_zones.geojson`) | **Real Geometries / Synthetic Load** | Real OpenStreetMap landuse polygons (`raw_landuse.geojson`, ODbL 1.0) | Multi-vertex irregular polygons derived directly from real OSM residential/commercial landuse relations and ways (`geometry_source: "osm_landuse"`): Lonavala Town Center & Residential (400 kW), Khandala Tourism Corridor (250 kW), Valvan Industrial Pocket (180 kW), and Bhushi Recreation Sector (70 kW). Total base load: **900.0 kW**. |
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
│   │   ├── raw_landuse.geojson        # Real OSM landuse polygons for Lonavala-Khandala
│   │   ├── raw_wind.geojson           # 28 real OSM wind turbine nodes along the ridge
│   │   ├── raw_power.geojson          # Real OSM transmission lines & substations
│   │   └── metadata.json              # Provenance, bboxes, feature counts, export date
│   ├── assets.geojson                 # 10 clean energy assets (Point features, EPSG:4326)
│   ├── demand_zones.geojson           # 4 demand zones from real OSM landuse (900 kW base load, EPSG:4326)
│   ├── water_features.geojson         # 107 clean water polygons & lines (< 2 MB)
│   ├── roads.geojson                  # 474 filtered road network segments (< 2 MB)
│   ├── power_lines.geojson            # 67 filtered power transmission lines (< 1 MB)
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
- **`context_bbox`**: `[73.25, 18.62, 73.62, 18.92]` — Encloses regional water catchments (Pavana Lake, Shirota Lake, Tata Dam) and regional road networks.
- **`asset_bbox`**: `[73.33, 18.70, 73.61, 18.91]` — Strict boundary for energy assets, demand zones, and wind ridge cluster.

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

### 4.4 Energy Flow Direction Rules
Power transfer vectors dynamically adapt in real time according to generation, demand, and storage state:
1. **Renewable Generation (Solar, Wind, Hydro)**:
   - Always flow from the generation facility toward the central demand hub (`to_demand`).
   - Line width and particle velocity scale directly with `flow_kw`.
2. **Battery Energy Storage System**:
   - **Discharging (`battery_kw > 0`)**: Direction is `to_demand` (from battery to the demand hub).
   - **Charging (`battery_kw < 0`)**: Direction reverses to `to_battery` (from supply/demand hub into the battery).
   - **Idle (`battery_kw == 0`)**: Static thin grey line (width 1.2 px, color `#475569`, 0 kW), no animation particles.
3. **Grid Intertie**:
   - **Importing (`grid_kw > 0`)**: Direction is `to_demand` (from intertie substation to demand hub).
   - **No Import (`grid_kw == 0`)**: Status is `not_supplying`, static thin grey line (0 kW), no animation particles.
4. **Animation Engine**:
   - Built exclusively using browser-native `requestAnimationFrame` (zero third-party animation libraries).
   - Particle flow automatically pauses when the browser tab is hidden (`document.hidden`) and resumes on visibility change.

### 4.5 24-Hour Time Slider & Playback Behaviour
- **Bottom-Center Control Bar**: Features a Play/Pause toggle button, a 24-step range slider (`00:00` to `23:00`), and a prominent timestamp readout.
- **Playback Loop**: Clicking Play advances the simulation one step every ~800 ms and loops continuously from `23:00` back to `00:00`.
- **Scrubbing & Interaction**: Scrubbing the slider instantly halts playback and synchronizes the targeted hour.
- **Unified Updates**: Advancing the slider updates all twin layers simultaneously:
  - Asset forecast output kW, utilization percentage, halo rings, and status badges.
  - Energy flow vector directions, line thicknesses, and animated particle speeds.
  - Sidebar energy dispatch metrics (Renewable Penetration %, Grid Dependency %, Battery Mode, Battery SOC, Gen vs Load balance).
  - Demand zone current `load_kw` and 4-tier color shading.
  - Collapsible side-panel asset directory and active map popup readouts.
- **Single-Point Scenarios**: Selecting a 1-hour snapshot scenario automatically disables the slider and play button while displaying that snapshot's exact timestamp.

### 4.6 Demand Zones Proportional Splitting & 4-Step Color Scale
- Current total `load_kw` is distributed across the 4 zones strictly in proportion to their `base_load_kw` (sum = 900 kW):
  $$P_{\text{zone}} = P_{\text{load, total}} \times \left(\frac{P_{\text{base, zone}}}{900\text{ kW}}\right)$$
- Color classification dynamically updates across a 4-step scale:
  - **Low** (`< 120 kW`): `#38bdf8` (Sky blue)
  - **Moderate** (`120 - 250 kW`): `#818cf8` (Indigo)
  - **High** (`250 - 400 kW`): `#f59e0b` (Amber)
  - **Peak** (`≥ 400 kW`): `#ef4444` (Crimson)
- Demand zones are prominently labeled as "illustrative zones (hand-defined polygons)", not OSM-derived, in popups and tooltips.


---

## 5. Integration for Member 4 (FastAPI + React / TypeScript)

This section provides the complete integration specification for Member 4 to embed the Lonavala Digital Twin map and dispatch engine into React / TypeScript frontend applications and FastAPI backends without any Python geospatial dependencies.

### 5.1 File List
Member 4 can import or fetch the following verified deliverables from `digital-twin/`:

| File Path | Description | Integration Use |
|---|---|---|
| `data/assets.geojson` | 10 clean energy assets (Point features, EPSG:4326) | Static layer or loaded via `gridmateMap.init()` |
| `data/demand_zones.geojson` | 4 demand zones from real OSM landuse (EPSG:4326, 900 kW base load) | Static layer or loaded via `gridmateMap.init()` |
| `data/water_features.geojson` | 107 real OSM water polygons & streams | Static GIS background context |
| `data/roads.geojson` | 474 filtered highway & road segments | Static GIS transport network context |
| `data/power_lines.geojson` | 67 real OSM power transmission lines (< 1 MB) | Static GIS power infrastructure context |
| `map/map_config.json` | Center, zoom, bboxes, basemaps, layer orders | Map configuration & styling parameters |
| `map/applyDispatch.js` | Pure UMD/CJS dispatch calculation engine | Headless proportional power distribution & flow |
| `map/gridmateMap.js` | Framework-agnostic ES module map controller | Interactive MapLibre GL JS React integration |

> **Disclaimer**: All energy asset coordinates and demand zone geometries are **synthetic and illustrative** prototype data for research and demonstration (`(Simulated)`), not verified real-world electrical infrastructure. Real features are water bodies, roads, power lines, and landuse polygons from OpenStreetMap.

### 5.2 Bounding Boxes (EPSG:4326 `[min_lon, min_lat, max_lon, max_lat]`)
- **Regional Context BBox (`context_bbox`)**: `[73.25, 18.62, 73.62, 18.92]`
  - Covers regional water catchments (Pavana Lake, Shirota Lake, Tata Dam) and highway corridors.
- **Asset Core BBox (`asset_bbox`)**: `[73.33, 18.70, 73.61, 18.91]`
  - Strictly encloses all 10 synthetic energy assets, 4 demand zones, and wind ridge cluster.

### 5.3 Property Contract & Exact Fields
Dispatch data passed from Member 2 (forecasting/optimization) or Member 4 (FastAPI) must strictly provide the following fields:

```typescript
export interface GridMateDispatchRow {
  timestamp?: string;        // ISO 8601 string, e.g. "2026-11-06T12:00:00"
  solar_kw: number;          // >= 0.0, solar PV generation
  wind_kw: number;           // >= 0.0, wind turbine generation
  hydro_kw: number;          // >= 0.0, hydro powerhouse output
  battery_kw: number;        // signed float (see battery sign convention)
  grid_kw: number;           // >= 0.0, power imported from 110kV grid intertie
  load_kw: number;           // > 0.0, total system demand
  curtailment_kw: number;    // >= 0.0, curtailed surplus renewable generation
  battery_soc_kwh?: number;  // 0.0 to 1000.0 kWh (nameplate capacity)
}

export interface GridMateDispatchContract {
  location: string;          // "Lonavala, Maharashtra, India"
  scenario_id: string;       // e.g. "normal", "cloudy", "heavy_monsoon", etc.
  scenario_name?: string;
  dispatch: GridMateDispatchRow[];
  metrics?: Record<string, any>;
}
```

Asset properties in `assets.geojson` and updated by `gridmateMap.setDispatch()`:
```typescript
export interface GridMateAssetProperties {
  id: string;                 // e.g. "solar_01", "wind_01", "hydro_01", "battery_01", "grid_01", "demand_hub"
  type: "solar" | "wind" | "hydro" | "battery" | "grid" | "demand";
  name: string;               // e.g. "Solar Park 01 - Khandala Plateau (Simulated)"
  capacity_kw: number;        // Nameplate capacity kW
  capacity_kwh?: number;      // 1000.0 kWh on battery asset
  status: "active" | "idle" | "charging" | "discharging" | "not_supplying";
  forecast_output_kw: number; // Dynamically computed >= 0.0
  utilization_percent: number;// (forecast_output_kw / capacity_kw) * 100
  battery_soc_kwh?: number;   // Updated on battery asset
  is_synthetic: true;         // Mandatory synthetic flag
  data_source: "synthetic_demo";
  note: string;
}
```

### 5.4 Battery Sign Convention
```text
battery_kw > 0 : Discharging (supplying power into the demand hub) -> status = 'discharging'
battery_kw < 0 : Charging (absorbing surplus power from generation) -> status = 'charging'
battery_kw = 0 : Idle (neither charging nor discharging)           -> status = 'idle'
```

### 5.5 Canonical Scenario IDs
The twin supports the following standard scenario identifiers:
1. `normal`: Normal Day (100% RE baseline, balanced solar, wind, hydro, battery)
2. `cloudy`: Cloudy Day (diminished solar PV, battery discharge support, grid intertie import)
3. `heavy_monsoon`: Heavy Monsoon (maximum hydro 400 kW, low solar 20 kW, battery charging -60 kW, grid import 330 kW)
4. `high_wind`: High Wind (peak ridge wind generation, surplus charging battery)
5. `peak_demand`: Peak Demand (evening 1.25 MW hub load, full asset dispatch)

### 5.6 React + TypeScript Example
Below is an example React component showing how to initialize `gridmateMap.js`, push live or simulated dispatch updates, and clean up on unmount:

```tsx
import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { init, GridMateMapController, GridMateDispatchRow, GridMateDispatchContract } from './digital-twin/map/gridmateMap.js';

interface DigitalTwinMapProps {
  dispatchData?: GridMateDispatchContract | GridMateDispatchRow;
  selectedScenario?: string;
  basemap?: 'streets' | 'satellite' | 'plain';
  terrain3D?: boolean;
  onAssetClick?: (feature: any) => void;
}

export const GridMateDigitalTwin: React.FC<DigitalTwinMapProps> = ({
  dispatchData,
  selectedScenario = 'normal',
  basemap = 'streets',
  terrain3D = false,
  onAssetClick,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<GridMateMapController | null>(null);

  // 1. Initialize map on mount, destroy on unmount
  useEffect(() => {
    let isCancelled = false;

    if (mapContainerRef.current) {
      init(mapContainerRef.current, {
        basePath: '/digital-twin/', // Path where data/ and map_config.json reside
        maplibregl: maplibregl,     // Injected MapLibre GL JS instance
        basemap: basemap,
        terrain: terrain3D,
        onAssetClick: (feat, coords) => {
          if (onAssetClick) onAssetClick(feat);
        },
        onReady: (controller) => {
          if (!isCancelled) {
            controllerRef.current = controller;
            if (dispatchData) {
              controller.setDispatch(dispatchData, 0);
            } else {
              controller.setScenario(selectedScenario);
            }
          }
        }
      }).catch((err) => console.error("GridMate digital twin init error:", err));
    }

    return () => {
      isCancelled = true;
      if (controllerRef.current) {
        controllerRef.current.destroy();
        controllerRef.current = null;
      }
    };
  }, []);

  // 2. React to dispatch state changes (supports both contract form and flat single-object form)
  useEffect(() => {
    if (controllerRef.current && dispatchData) {
      controllerRef.current.setDispatch(dispatchData, 0);
    }
  }, [dispatchData]);

  // 3. React to scenario selector changes
  useEffect(() => {
    if (controllerRef.current && selectedScenario && !dispatchData) {
      controllerRef.current.setScenario(selectedScenario);
    }
  }, [selectedScenario]);

  // 4. React to basemap changes
  useEffect(() => {
    if (controllerRef.current && basemap) {
      controllerRef.current.setBasemap(basemap);
    }
  }, [basemap]);

  // 5. React to 3D terrain toggle
  useEffect(() => {
    if (controllerRef.current && terrain3D !== undefined) {
      controllerRef.current.setTerrain(terrain3D);
    }
  }, [terrain3D]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: '500px' }}>
      <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
};

export default GridMateDigitalTwin;
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

# Step 2: Generate assets, demand zones (illustrative hand-defined polygons), and energy flow template
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
