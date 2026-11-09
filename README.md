# GridMate

**From Weather to Watts, Intelligently.** A Lonavala microgrid prototype: pick a weather or demand scenario, and GridMate forecasts renewable generation and demand, optimizes how solar, wind, hydro, battery and grid power should respond, and shows the result on a digital-twin map.

> **All data is synthetic.** Forecasts, asset capacities and demand are illustrative prototype values, not measured Lonavala data. The UI labels every result as a simulation.

```
Scenario -> AI Forecast -> PyPSA Optimization -> Smart Dispatch -> Digital Twin -> Metrics + Charts
```

## Repository layout

| Folder | Owner | What it is |
|---|---|---|
| `forecasting_real_data/` | Member 1 | XGBoost forecasting (`generate_forecast`) |
| `optimization/` | Member 2 | PyPSA + HiGHS dispatch (`optimize_dispatch`) |
| `digital-twin/` | Member 3 | Lonavala GeoJSON assets, demand zones, water, power lines |
| `backend/` | Member 4 | FastAPI app that chains the three modules |
| `frontend/` | Member 4 | React + TypeScript + Tailwind + MapLibre + ECharts dashboard |

## Prerequisites

- Python 3.12 or newer
- Node.js 18 or newer (https://nodejs.org, LTS)
- Git

## Quick start

Windows PowerShell: `.\start.ps1`   macOS/Linux: `./start.sh`

These create the virtual environment, install dependencies, start the backend on port 8000 and the frontend on port 5173. The manual steps are below.

## Run it (two terminals, from the repository root)

**Terminal 1: backend**

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1      macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --port 8000
```

API docs: http://localhost:8000/docs

**Terminal 2: frontend**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to the backend on port 8000. If the backend runs elsewhere, set `VITE_API_PROXY` (for example `VITE_API_PROXY=http://127.0.0.1:9000 npm run dev`).

## Demo flow

1. Open GridMate. The Normal Day simulation loads automatically.
2. Point to the metrics, the map, the AI forecast and the optimized dispatch.
3. Choose **Heavy Monsoon** and click **Run Simulation**. Progress shows *Forecasting*, *Optimizing dispatch*, *Updating digital twin*.
4. The forecast, dispatch, metrics, map flows and battery status all change. Each metric card shows its change against the previous run.
5. Try **Peak Demand** and watch the battery and grid respond in the evening hours. Drag the Hour slider to move through the day.
6. Click any asset on the map for its capacity, current output and status.

> GridMate doesn't only predict renewable energy. It uses those predictions to decide how the energy system should respond.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Module availability and mode |
| GET | `/api/scenarios` | The five supported scenarios |
| GET | `/api/forecast?scenario=` | 24-hour forecast |
| GET | `/api/dispatch?scenario=` | Optimized dispatch |
| GET | `/api/metrics?scenario=` | Metrics, energy totals, system limits, cost estimate |
| GET | `/api/assets` | Digital-twin GeoJSON layers and map config |
| POST | `/api/scenario` | Select a scenario, returns its forecast |
| POST | `/api/optimize` | Run the full pipeline for a scenario |

Scenarios: `normal`, `cloudy`, `heavy_monsoon`, `high_wind`, `peak_demand`. Every response includes a `meta` block with the data label, the source of each stage (`model`/`pypsa` or `mock`) and any warnings.

### Modes

Set `GRIDMATE_MODE` before starting the backend:

- `auto` (default): use the real modules, fall back to mock data with a visible warning if one fails.
- `real`: real modules only; failures return HTTP 503.
- `mock`: built-in mock data only (useful when developing without the ML or solver dependencies).

## Tests

```bash
python -m pytest                      # backend: 22 tests, includes real PyPSA runs
cd frontend && npm test               # frontend: utility tests
cd frontend && npm run build          # type-check and production build
```

## Assumptions and known limits

- **Synthetic data.** The forecasting training data is AI-generated (see `forecasting_real_data/README.md`). CO2 avoided uses an assumed grid emission factor and is an estimate. Cost figures use assumed tariffs.
- **Grid capacity is 1500 kW** in `optimization/config/system_config.json`, matching the grid intertie in the digital twin. At 1000 kW the Peak Demand scenario (1.25 MW evening peak) is infeasible.
- **Battery size.** The dashboard uses the optimizer's battery (500 kWh) because that is what was actually solved. The digital-twin README describes 1000 kWh.
- **Wind calibration.** The synthetic wind forecast averages only about 14 kW against 400 kW of installed wind in the digital twin, so renewable penetration in the Normal scenario is about 31%. This is a data-calibration question for the forecasting and digital-twin modules and has not been altered.
- **Per-asset output on the map** is the dispatched total for each source type, split by installed capacity.
- Forecast timestamps come from the forecasting module and are shown as time of day only.
- The Streets and Satellite basemaps load from public tile servers and need internet access. The Plain basemap works offline.

## Git workflow

```bash
git checkout -b feature/backend-dashboard
git add backend/ frontend/ README.md
git commit -m "Build GridMate dashboard and API"
git push origin feature/backend-dashboard   # then open a Pull Request into main
```
