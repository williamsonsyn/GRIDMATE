# GridMate — Member 4 Task Specification
## Backend, Dashboard & System Integration Engineer

### Project
GridMate — **From Weather to Watts, Intelligently.**  
Prototype deadline: **10 October 2026**  
Testbed: **Lonavala, Maharashtra**

### Your role
You own the **application layer and final integration**.

Your job is to turn the other three modules into one working prototype a judge can open and understand.

Complete pipeline:

```text
Weather + Water + Geography + Demand
                ↓
Member 1 — AI Forecasting
                ↓
Member 2 — PyPSA Optimization
                ↓
Smart Dispatch
                ↓
Member 3 — Lonavala Digital Twin
                ↓
Member 4 — Application
                ↓
Judge-facing UI
```

## 1. Responsibilities

Build:

1. FastAPI backend
2. React + TypeScript frontend
3. API integration
4. Main GridMate dashboard
5. Scenario controls
6. Charts and metrics
7. Lonavala Digital Twin integration
8. End-to-end demo flow

## 2. Technology

### Backend

- Python 3.12
- FastAPI
- Pydantic
- Uvicorn

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS

### Visualization

- MapLibre GL JS
- Plotly or ECharts

Choose one chart library and keep it consistent.

## 3. Development Rule

Do not wait for other members.

Start with:

```text
mock forecast
mock dispatch
mock GIS data
```

Build the complete dashboard against these contracts, then replace mocks with the real modules.

## 4. Backend Structure

```text
backend/
├── main.py
├── api/
│   ├── forecast.py
│   ├── dispatch.py
│   ├── scenarios.py
│   └── metrics.py
├── models/
│   └── schemas.py
├── services/
│   ├── forecasting_service.py
│   ├── optimization_service.py
│   └── scenario_service.py
├── data/
└── tests/
```

Keep routes separate from business logic.

## 5. Required API Concepts

Implement at least:

```text
GET  /api/health
GET  /api/forecast
GET  /api/dispatch
GET  /api/metrics
GET  /api/assets
POST /api/scenario
POST /api/optimize
```

## 6. API Contracts

### Forecast

Return:

```json
{
  "location": "Lonavala",
  "forecast_horizon_hours": 24,
  "forecast": [
    {
      "timestamp": "2026-10-01T12:00:00",
      "solar_kw": 420,
      "wind_kw": 180,
      "hydro_kw": 250,
      "load_kw": 900
    }
  ]
}
```

### Dispatch

Return:

```json
{
  "location": "Lonavala",
  "dispatch": [
    {
      "timestamp": "2026-10-01T12:00:00",
      "solar_kw": 420,
      "wind_kw": 180,
      "hydro_kw": 250,
      "battery_kw": 50,
      "grid_kw": 0,
      "load_kw": 900,
      "curtailment_kw": 0,
      "battery_soc_kwh": 150
    }
  ]
}
```

### Metrics

Return:

```text
renewable penetration
grid dependency
curtailment
battery utilization
estimated CO₂ avoided
```

### Assets

Return Member 3's GeoJSON/geographic asset data.

### Scenario

Input:

```json
{
  "scenario": "heavy_monsoon"
}
```

Supported:

```text
normal
cloudy
heavy_monsoon
high_wind
peak_demand
```

### Optimize

Trigger the scenario → forecast → optimization pipeline.

## 7. Frontend Layout

Recommended:

```text
┌───────────────────────────────────────────────┐
│ GRIDMATE                                      │
│ From Weather to Watts, Intelligently          │
├───────────────────────────────────────────────┤
│ Scenario: [Normal Day ▼]    [Run Simulation]  │
├───────────────────────────────────────────────┤
│          LONAVALA DIGITAL TWIN                │
│                INTERACTIVE MAP                │
├────────────┬────────────┬────────────┬─────────┤
│ Renewable  │ Grid       │ Battery    │ CO₂     │
│ Penetration│ Dependency │ Utilization│ Avoided │
├────────────┴────────────┴────────────┴─────────┤
│       GENERATION vs DEMAND CHART               │
├───────────────────────────────────────────────┤
│       DISPATCH / ENERGY MIX CHART              │
└───────────────────────────────────────────────┘
```

## 8. Components

Create reusable components:

```text
Header
ScenarioSelector
MapPanel
MetricCard
GenerationChart
DemandChart
DispatchChart
EnergyMix
BatteryStatus
SystemStatus
```

Do not put the entire UI in one component.

## 9. Main Metrics

Show prominently:

- Renewable Penetration
- Grid Dependency
- Curtailment
- Battery Utilization
- Estimated CO₂ Avoided

If data is simulated, visibly label it:

```text
Simulation Result
```

or:

```text
Illustrative Prototype Result
```

Never present demo values as measured Lonavala results.

## 10. Scenario Demo

The most important demo interaction:

```text
Select Scenario
      ↓
Run Simulation
      ↓
Forecast updates
      ↓
Optimization runs
      ↓
Dispatch updates
      ↓
Metrics update
      ↓
Map updates
      ↓
Charts update
```

The system should demonstrate adaptation, not static charts.

## 11. Digital Twin

Use Member 3's:

```text
assets.geojson
demand_zones.geojson
water_features.geojson
```

through MapLibre.

Show:

```text
Solar
Wind
Hydro
Battery
Grid
Demand
```

Clicking an asset should expose useful metadata.

## 12. Forecast Chart

Show:

```text
Time
Solar
Wind
Hydro
Demand
```

A multi-line chart is sufficient.

## 13. Dispatch Chart

Show:

```text
Solar
Wind
Hydro
Battery
Grid
Demand
```

A stacked area/bar chart is suitable.

## 14. Backend Integration

Preferred architecture:

```text
React
  ↓ HTTP
FastAPI
  ↓
Service Layer
  ↓
Forecasting / Optimization / GIS
```

Do not make the frontend depend on random local JSON files.

## 15. Mock Services

Create temporary functions such as:

```python
get_mock_forecast()
get_mock_dispatch()
get_mock_metrics()
get_mock_assets()
```

Replace them with real modules after integration.

## 16. TypeScript Interfaces

Define types matching the API.

Example:

```typescript
interface ForecastPoint {
  timestamp: string;
  solar_kw: number;
  wind_kw: number;
  hydro_kw: number;
  load_kw: number;
}

interface DispatchPoint {
  timestamp: string;
  solar_kw: number;
  wind_kw: number;
  hydro_kw: number;
  battery_kw: number;
  grid_kw: number;
  load_kw: number;
  curtailment_kw: number;
  battery_soc_kwh: number;
}
```

Avoid using `any` throughout the application.

## 17. Error and Loading States

Handle:

```text
API unavailable
optimization failure
invalid scenario
missing data
empty forecast
```

When simulation runs, show progress such as:

```text
Forecasting...
Optimizing dispatch...
Updating digital twin...
```

## 18. Folder Structure

```text
backend/
├── main.py
├── api/
├── models/
├── services/
├── data/
├── tests/
└── requirements.txt

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── services/
│   ├── types/
│   ├── hooks/
│   └── utils/
├── public/
└── package.json
```

## 19. Do NOT Build

Do not independently rewrite:

- XGBoost forecasting
- PyPSA optimization
- GIS preprocessing
- utility-scale energy modelling

Integrate the other members' modules.

## 20. Definition of DONE

1. Backend starts.
2. Frontend starts.
3. Dashboard loads.
4. Lonavala map loads.
5. Forecast is displayed.
6. Dispatch is displayed.
7. Metrics update.
8. Scenario selection works.
9. Run Simulation triggers updated results.
10. Charts update.
11. Map/status updates.
12. Loading/error states work.
13. App works from a clean Git clone.
14. No machine-specific hardcoded paths.

## 21. End-to-End Demo

```text
1. Open GridMate.
2. Show Normal Day.
3. Point to renewable penetration, grid dependency,
   battery, map, forecast and dispatch.
4. Change to Heavy Monsoon.
5. Click Run Simulation.
6. Show forecast changed.
7. Show optimized dispatch changed.
8. Show metrics changed.
9. Show map/status changed.
10. Try Peak Demand and show battery/grid response.
```

Core explanation:

> GridMate doesn't only predict renewable energy. It uses those predictions to decide how the energy system should respond.

## 22. Git

```bash
git checkout -b feature/backend-dashboard
git add backend/ frontend/
git commit -m "Build GridMate dashboard and API"
git push origin feature/backend-dashboard
```

Use a Pull Request into `main`.

Integration commits should be explicit:

```text
Integrate forecasting service
Integrate PyPSA dispatch
Integrate Lonavala GeoJSON
Add scenario simulation
```

## 23. AI Handoff Prompt

When giving this file to an AI coding assistant, say:

> Build only the Member 4 Backend, Frontend and Integration module described here. Use FastAPI, React, TypeScript, Vite, Tailwind and MapLibre. Start with mock data so the application runs independently. Follow the API contracts and TypeScript interfaces exactly. Do not duplicate forecasting or PyPSA optimization. The final goal is a polished, responsive, judge-facing GridMate prototype demonstrating scenario → forecast → optimization → dispatch → visualization.

## 24. Final Deliverables

```text
backend/
frontend/
API schemas
mock data
tests
README.md
```

The final application must demonstrate:

```text
Scenario
   ↓
AI Forecast
   ↓
Optimization
   ↓
Smart Dispatch
   ↓
Lonavala Digital Twin
   ↓
Metrics + Charts
```
