# GridMate — Master Architecture & Development Contract

## From Weather to Watts, Intelligently.

**Project:** GridMate  
**Prototype deadline:** 10 October 2026  
**Testbed:** Lonavala, Maharashtra  
**Team size:** 4 developers  
**Repository:** One shared GitHub repository

---

# 1. Purpose of This File

This is the **master technical contract** for the entire GridMate project.

The four member-specific task files explain what each individual member must build.

This file defines the things that **everyone must agree on and must not independently change**:

- overall architecture
- technology stack
- repository structure
- module ownership
- data contracts
- API contracts
- scenario names
- common metrics
- integration rules
- Git workflow
- prototype scope

If a member's implementation conflicts with this document, discuss the change with the team before changing the shared contract.

---

# 2. What GridMate Is

GridMate is an AI-powered renewable-energy forecasting, optimization and intelligent-dispatch prototype.

It combines:

```text
Weather
Water
Geography
Electricity Demand
        ↓
AI Forecasting
        ↓
Energy Optimization
        ↓
Smart Dispatch
        ↓
Lonavala Digital Twin
        ↓
Interactive Dashboard
```

The system predicts renewable availability and electricity demand, optimizes the available energy resources, and visualizes the resulting dispatch for the Lonavala testbed.

---

# 3. Core System Architecture

```text
┌──────────────────────────────────────────────────────────┐
│                    INPUT DATA                            │
│                                                          │
│ Weather │ Water/Rainfall │ Geography │ Electricity Load │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ MEMBER 1 — AI FORECASTING                                │
│                                                          │
│ XGBoost                                                   │
│                                                          │
│ Solar Forecast │ Wind Forecast │ Hydro Forecast │ Load   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           │ forecast.json
                           ▼
┌──────────────────────────────────────────────────────────┐
│ MEMBER 2 — ENERGY OPTIMIZATION                           │
│                                                          │
│ PyPSA + HiGHS                                             │
│                                                          │
│ Solar │ Wind │ Hydro │ Battery │ Grid │ Load             │
└──────────────────────────┬───────────────────────────────┘
                           │
                           │ dispatch.json
                           ▼
┌──────────────────────────────────────────────────────────┐
│ MEMBER 4 — BACKEND + APPLICATION                         │
│                                                          │
│ FastAPI → React + TypeScript                             │
└──────────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┴─────────────┐
              │                          │
              ▼                          ▼
┌─────────────────────────┐   ┌───────────────────────────┐
│ MEMBER 3 — DIGITAL TWIN │   │ DASHBOARD                 │
│                         │   │                           │
│ OSM / GeoJSON /         │   │ Charts / Metrics /        │
│ MapLibre                │   │ Scenario Controls         │
└─────────────────────────┘   └───────────────────────────┘
```

---

# 4. Final Technology Stack

## 4.1 Core Development

```text
Python 3.12
```

Python is the primary language for forecasting, optimization, data processing and backend services.

---

## 4.2 Data Processing

```text
Pandas
NumPy
```

Used for:

- data loading
- cleaning
- transformation
- feature engineering
- numerical operations

---

## 4.3 AI / Forecasting

```text
XGBoost
Scikit-learn
```

Primary forecasting model:

```text
XGBoost
```

Forecast:

```text
Solar generation
Wind generation
Hydro generation
Electricity demand
```

---

## 4.4 Energy Optimization

```text
PyPSA
HiGHS
```

PyPSA is the primary energy-system optimization framework.

HiGHS is the default open-source solver.

Model:

```text
Solar
Wind
Hydro
Battery
Grid
Load
```

---

## 4.5 GIS / Digital Twin

```text
OpenStreetMap
OSMnx
GeoPandas
GeoJSON
QGIS
MapLibre GL JS
```

Use:

- OpenStreetMap for geographic context
- OSMnx for geographic data processing
- GeoPandas for geospatial processing
- GeoJSON as the integration format
- QGIS for GIS inspection/editing
- MapLibre for the interactive application map

---

## 4.6 Backend

```text
FastAPI
Pydantic
Uvicorn
```

FastAPI provides the API layer between the frontend and the underlying modules.

Pydantic defines/validates data structures.

---

## 4.7 Frontend

```text
React
TypeScript
Vite
Tailwind CSS
```

The frontend is the judge-facing application.

---

## 4.8 Visualization

```text
MapLibre GL JS
Plotly OR ECharts
```

Use MapLibre for the map.

Choose **one** of Plotly/ECharts for the primary charting layer and keep it consistent.

---

## 4.9 Testing

Use:

```text
pytest
```

for Python modules.

Frontend testing can be added if time permits, but full test coverage is not required for the prototype.

---

## 4.10 Deployment / Environment

Docker may be added for packaging if time permits.

Do not allow deployment work to delay the core prototype.

---

# 5. What We Are NOT Using

Do not introduce these into GridMate unless the team explicitly changes the architecture:

```text
SUMO
TraCI
traffic simulation
traffic-specific libraries
```

Those belong to the separate FlowCity traffic project, not GridMate.

Similarly, do not add unnecessary:

```text
deep-learning frameworks
microservices
Kubernetes
complex cloud infrastructure
commercial optimization solvers
```

The October 10 objective is a working prototype.

---

# 6. Module Ownership

## Member 1

```text
forecasting/
```

Owns:

```text
AI forecasting
data preprocessing
feature engineering
XGBoost models
forecast evaluation
forecast.json
```

Question answered:

> What energy will be available?

---

## Member 2

```text
optimization/
```

Owns:

```text
PyPSA model
HiGHS optimization
battery
grid
dispatch
curtailment
optimization metrics
dispatch.json
```

Question answered:

> How should available energy be used?

---

## Member 3

```text
digital-twin/
```

Owns:

```text
GIS
GeoJSON
Lonavala geographic context
energy assets
demand zones
map data
digital-twin visualization support
```

Question answered:

> Where is the energy system located?

---

## Member 4

```text
backend/
frontend/
```

Owns:

```text
FastAPI
React
TypeScript
dashboard
API integration
scenario controls
charts
metrics display
MapLibre integration
```

Question answered:

> How does the user see and interact with the system?

---

# 7. Repository Structure

The shared repository should look approximately like:

```text
GridMate/
│
├── GRIDMATE_ARCHITECTURE.md
├── README.md
├── .gitignore
│
├── forecasting/
│   ├── data/
│   ├── models/
│   ├── notebooks/
│   ├── src/
│   ├── outputs/
│   ├── tests/
│   ├── requirements.txt
│   └── README.md
│
├── optimization/
│   ├── data/
│   ├── src/
│   ├── outputs/
│   ├── config/
│   ├── tests/
│   ├── requirements.txt
│   └── README.md
│
├── digital-twin/
│   ├── data/
│   ├── scripts/
│   ├── map/
│   ├── qgis/
│   ├── src/
│   ├── tests/
│   └── README.md
│
├── backend/
│   ├── main.py
│   ├── api/
│   ├── models/
│   ├── services/
│   ├── data/
│   ├── tests/
│   ├── requirements.txt
│   └── README.md
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── README.md
│
├── data/
│
└── tests/
```

Members should primarily modify their own folders.

---

# 8. The Most Important Integration Rule

The system is built around two major data contracts:

```text
forecast.json
```

and:

```text
dispatch.json
```

Do not casually change these schemas.

If a schema change is necessary, tell all members first.

---

# 9. Forecast Contract

Member 1 produces:

```json
{
  "location": "Lonavala",
  "forecast_horizon_hours": 24,
  "forecast": [
    {
      "timestamp": "2026-10-01T12:00:00",
      "solar_kw": 420.0,
      "wind_kw": 180.0,
      "hydro_kw": 250.0,
      "load_kw": 900.0
    }
  ]
}
```

Required fields:

```text
location
forecast_horizon_hours
forecast[]
```

Each forecast point:

```text
timestamp
solar_kw
wind_kw
hydro_kw
load_kw
```

Units:

```text
generation → kW
load → kW
```

---

# 10. Dispatch Contract

Member 2 produces:

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
  "metrics": {
    "renewable_penetration_percent": 94.4,
    "grid_dependency_percent": 0.0,
    "curtailment_percent": 0.0,
    "battery_utilization_percent": 16.7,
    "estimated_co2_avoided_kg": 0.0
  }
}
```

Required dispatch fields:

```text
timestamp
solar_kw
wind_kw
hydro_kw
battery_kw
grid_kw
load_kw
curtailment_kw
battery_soc_kwh
```

---

# 11. GeoJSON Contract

Member 3 provides geographic data as GeoJSON.

Example:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "id": "solar_01",
        "type": "solar",
        "name": "Solar Site 01",
        "capacity_kw": 500
      },
      "geometry": {
        "type": "Point",
        "coordinates": [73.40, 18.75]
      }
    }
  ]
}
```

Important:

```text
GeoJSON = [longitude, latitude]
```

Synthetic/demo assets must be clearly labelled.

---

# 12. Common Energy Resources

Use these exact resource names across modules:

```text
solar
wind
hydro
battery
grid
load
```

Use consistent field naming:

```text
solar_kw
wind_kw
hydro_kw
battery_kw
grid_kw
load_kw
```

Do not alternate between:

```text
solarPower
solar_generation
solarOutput
solarKW
```

unless an explicit API transformation requires it.

---

# 13. Common Scenarios

The complete application must recognize these scenario identifiers:

```text
normal
cloudy
heavy_monsoon
high_wind
peak_demand
```

Human-readable labels:

```text
Normal Day
Cloudy Day
Heavy Monsoon
High Wind
Peak Demand
```

### Scenario meaning

#### normal

Baseline conditions.

#### cloudy

Lower solar irradiance/cloudier conditions.

Expected effect:

```text
solar ↓
```

#### heavy_monsoon

High rainfall and reduced solar availability.

Expected prototype effect may include:

```text
rainfall ↑
solar ↓
hydro availability ↑
```

Only apply relationships that are represented in the model.

#### high_wind

Higher wind availability.

Expected effect:

```text
wind ↑
```

#### peak_demand

Higher electricity demand.

Expected effect:

```text
load ↑
```

These are scenario assumptions for the prototype, not claims about actual future weather.

---

# 14. Common Metrics

The dashboard should use the same definitions everywhere.

## Renewable Penetration

```text
renewable energy supplied to load
--------------------------------- × 100
total load
```

## Grid Dependency

```text
grid energy supplied
-------------------- × 100
total load
```

## Curtailment

```text
curtailed renewable energy
-------------------------- × 100
available renewable energy
```

## Battery Utilization

Use the definition implemented by Member 2 and document it.

All dashboard labels must match that definition.

## Estimated CO₂ Avoided

Based on:

```text
renewable energy replacing grid energy
× assumed grid emission factor
```

Always call this an **estimate**.

---

# 15. Simulation vs Real Data

This is a strict presentation rule.

If data is:

```text
synthetic
simulated
assumed
illustrative
prototype-generated
```

do not present it as actual measured Lonavala data.

Use labels such as:

```text
Simulation Result
Illustrative Prototype Result
Synthetic Demo Data
Assumed Prototype Parameters
```

This applies especially to:

- energy-generation values
- battery specifications
- asset locations
- CO₂ results
- forecast accuracy
- performance metrics

---

# 16. Forecast → Optimization → Visualization Flow

The intended runtime flow is:

```text
Scenario Selection
       ↓
Input Conditions
       ↓
Member 1 Forecasting
       ↓
forecast.json
       ↓
Member 2 Optimization
       ↓
dispatch.json
       ↓
Member 4 Backend
       ↓
Member 4 Frontend
       ↓
Charts + Metrics + Digital Twin
```

Member 3's GeoJSON is loaded alongside this pipeline:

```text
GeoJSON
   ↓
FastAPI / Frontend
   ↓
MapLibre
```

---

# 17. Backend API Contract

Member 4 should expose at least:

```text
GET  /api/health
GET  /api/forecast
GET  /api/dispatch
GET  /api/metrics
GET  /api/assets
POST /api/scenario
POST /api/optimize
```

The frontend communicates with FastAPI.

The frontend should not directly depend on Python module internals.

---

# 18. Recommended Runtime Architecture

```text
                ┌───────────────────┐
                │      React        │
                │   TypeScript UI   │
                └─────────┬─────────┘
                          │ HTTP
                          ▼
                ┌───────────────────┐
                │      FastAPI      │
                └─────────┬─────────┘
                          │
             ┌────────────┼─────────────┐
             ▼            ▼             ▼
       Forecasting   Optimization   GIS/Assets
          Module         Module         Data
             │            │             │
             ▼            ▼             ▼
       forecast.json  dispatch.json   GeoJSON
```

---

# 19. Scenario Execution

When the user clicks:

```text
Run Simulation
```

the intended flow is:

```text
1. Read selected scenario.
2. Generate/apply scenario input.
3. Run forecasting.
4. Generate forecast.json.
5. Run optimization.
6. Generate dispatch.json.
7. Calculate metrics.
8. Update dashboard.
9. Update charts.
10. Update digital twin state.
```

For the prototype, this can be implemented synchronously if execution is fast enough.

---

# 20. Mock-First Development

Every member must be able to work independently.

### Member 1

Uses synthetic/sample input data.

### Member 2

Uses `sample_forecast.json`.

### Member 3

Uses `sample_dispatch.json`.

### Member 4

Uses mock forecast, dispatch and GeoJSON.

This prevents:

```text
Member 1 waiting for Member 2
Member 2 waiting for Member 1
Member 3 waiting for Member 4
Member 4 waiting for everyone
```

---

# 21. Git Strategy

Use one branch per feature/member.

Example:

```text
main
│
├── feature/ai-forecasting
├── feature/energy-optimization
├── feature/lonavala-digital-twin
└── feature/backend-dashboard
```

Workflow:

```bash
git checkout -b feature/your-feature
```

Then:

```bash
git add .
git commit -m "Clear description"
git push origin feature/your-feature
```

Create a Pull Request.

Do not directly push experimental work to `main`.

---

# 22. Commit Naming

Prefer:

```text
Add XGBoost forecasting pipeline
Add PyPSA dispatch model
Add Lonavala GeoJSON assets
Build FastAPI forecast endpoint
Build GridMate dashboard
Integrate forecasting service
Integrate optimization service
Integrate Lonavala digital twin
Add scenario simulation
Fix battery dispatch constraint
```

Avoid:

```text
update
changes
final
final2
new
test
```

---

# 23. Integration Order

Merge in this order:

### Stage 1

Member 1 + Member 2:

```text
forecast.json
     ↓
dispatch.json
```

### Stage 2

Member 3:

```text
GeoJSON
```

### Stage 3

Member 4:

```text
FastAPI
+
React
+
Forecast
+
Dispatch
+
GeoJSON
```

### Stage 4

Full scenario loop:

```text
Scenario
   ↓
Forecast
   ↓
Optimization
   ↓
Dispatch
   ↓
Dashboard
```

---

# 24. Testing Requirements

Before merging:

### Member 1

Verify:

```text
forecast generated
correct JSON
non-negative values
metrics generated
```

### Member 2

Verify:

```text
optimization solves
energy balance holds
battery constraints hold
dispatch JSON valid
```

### Member 3

Verify:

```text
GeoJSON valid
coordinates correct
assets render
```

### Member 4

Verify:

```text
API starts
frontend starts
API data renders
scenario works
charts update
map loads
```

---

# 25. End-to-End Acceptance Test

The entire team must eventually be able to perform:

```text
START APPLICATION
      ↓
Select "Normal Day"
      ↓
Run Simulation
      ↓
Forecast generated
      ↓
Optimization solved
      ↓
Dispatch generated
      ↓
Dashboard updates
      ↓
Map updates
      ↓
Metrics update
```

Then:

```text
Select "Heavy Monsoon"
      ↓
Run Simulation
      ↓
Forecast changes
      ↓
Dispatch changes
      ↓
Metrics change
      ↓
Map/status changes
```

Then:

```text
Select "Peak Demand"
      ↓
Run Simulation
      ↓
Demand increases
      ↓
Battery/Grid response changes
      ↓
Dashboard updates
```

If this works reliably, the core prototype is working.

---

# 26. What NOT to Do Before October 10

Do not spend significant time on:

```text
complex cloud architecture
Kubernetes
authentication
mobile application
real-time IoT hardware
massive datasets
deep neural networks
utility-grade power-flow modelling
perfect geographic accuracy
advanced user accounts
```

First make the core loop work.

---

# 27. Prototype Priority

If time becomes limited, prioritize in this order:

```text
1. End-to-end working pipeline
2. Forecasting
3. Optimization
4. Scenario changes
5. Dashboard
6. Digital Twin
7. Metrics
8. Visual polish
9. Additional features
```

A smaller system that works end-to-end is preferable to many disconnected features.

---

# 28. Final Product Story

The final GridMate demonstration should communicate one simple idea:

> **GridMate predicts what renewable energy will be available, optimizes how that energy should be used, and visualizes the resulting energy decisions for Lonavala.**

The demo should visibly demonstrate:

```text
WEATHER / DEMAND
       ↓
PREDICT
       ↓
OPTIMIZE
       ↓
DISPATCH
       ↓
VISUALIZE
       ↓
ADAPT TO SCENARIOS
```

---

# 29. Final Technology Stack — One-Page Reference

```text
┌────────────────────────────────────────────┐
│ GRIDMATE STACK                              │
├────────────────────────────────────────────┤
│ Language       │ Python 3.12               │
│ Data           │ Pandas + NumPy             │
│ AI             │ XGBoost + Scikit-learn     │
│ Optimization   │ PyPSA + HiGHS              │
│ GIS            │ OSM + OSMnx + GeoPandas    │
│ GIS Format     │ GeoJSON                     │
│ Map            │ MapLibre GL JS              │
│ Backend        │ FastAPI + Pydantic          │
│ Frontend       │ React + TypeScript + Vite   │
│ Styling        │ Tailwind CSS                │
│ Charts         │ Plotly OR ECharts           │
│ Testing        │ pytest                       │
│ Packaging      │ Docker (optional)           │
│ Version Control│ Git + GitHub                │
└────────────────────────────────────────────┘
```

---

# 30. Final Ownership Reference

```text
MEMBER 1
AI FORECASTING
Python + XGBoost
        │
        │ forecast.json
        ▼
MEMBER 2
ENERGY OPTIMIZATION
PyPSA + HiGHS
        │
        │ dispatch.json
        ▼
MEMBER 4
BACKEND + FRONTEND
FastAPI + React + TypeScript
        ▲
        │ GeoJSON
        │
MEMBER 3
DIGITAL TWIN
OSM + OSMnx + GeoPandas + MapLibre
```

---

# 31. Non-Negotiable Shared Contracts

Before October 10, all members must agree on these exact shared items:

```text
✓ Python 3.12
✓ forecast.json schema
✓ dispatch.json schema
✓ GeoJSON format
✓ scenario identifiers
✓ metric names
✓ kW/kWh units
✓ folder ownership
✓ Git branch strategy
✓ simulated-data labelling
```

Individual implementation details can change.

These shared interfaces should remain stable.

---

# 32. Final Rule

Every member should be able to explain:

```text
What am I building?
What technology am I using?
What does my module receive?
What does my module produce?
Who consumes my output?
Where does my code live?
How do I test it?
When is my module considered complete?
```

If those questions can be answered from this document and the member-specific specification, the team is ready to develop GridMate in parallel.
