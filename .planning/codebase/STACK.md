---
last_mapped_commit: ""
last_mapped_at: "2026-11-05"
---

# STACK.md — GridMate Technology Stack

**Analysis Date:** 2026-11-05
**Project:** GridMate — AI-powered renewable energy forecasting, optimization, and dispatch prototype

---

## Languages & Runtimes

| Layer | Language | Version |
|---|---|---|
| Data processing, GIS, forecasting, optimization | **Python** | 3.12 (mandated by GRIDMATE_ARCHITECTURE.md) |
| Map client / JS dispatch engine | **JavaScript (ES5+)** | Node 24 (dev), browser CDN (prod) |
| Map HTML demo | **HTML5** | Static, no build step |
| Config & data contracts | **JSON / GeoJSON** | EPSG:4326 |

---

## Dependency Files

| File | Location |
|---|---|
| `requirements.txt` | `digital-twin/requirements.txt` |

**`digital-twin/requirements.txt`:**
```
geopandas>=1.0.0
osmnx>=2.0.0
shapely>=2.0.0
pytest>=8.0.0
requests>=2.31.0
```

**Installed (`.venv`):**
- `geopandas==1.2.0` — geospatial data frame operations, GeoJSON I/O
- `osmnx==2.1.1` — OpenStreetMap download, graph, feature queries
- `shapely==2.2.0` — geometry creation, validation, simplification
- `pandas==3.1.1` — tabular data handling (dependency of geopandas)
- `numpy==2.5.4` — numerical ops (dependency chain)
- `pyproj==3.8.0` — CRS reprojection, EPSG:4326
- `pyogrio==0.13.0` — fast GeoJSON/file I/O backend for geopandas
- `pytest==9.2.0` — test runner
- `requests==2.34.2` — HTTP (Overpass API calls in download_osm.py)
- `networkx==3.7` — graph model (osmnx dependency)

**No package.json** — the project has no frontend build toolchain. The `digital-twin/map/` module is vanilla JS loaded via CDN.

---

## Planned / Architecture-Specified Stack (Modules Not Yet Present in Repo)

Per `docs/GRIDMATE_ARCHITECTURE.md` §4:

| Module | Member | Stack |
|---|---|---|
| AI Forecasting | Member 1 (`forecasting/`) | XGBoost, Scikit-learn, Pandas, NumPy |
| Energy Optimization | Member 2 (`optimization/`) | PyPSA, HiGHS |
| Backend API | Member 4 (`backend/`) | FastAPI, Pydantic, Uvicorn |
| Frontend Dashboard | Member 4 (`frontend/`) | React, TypeScript, Vite, Tailwind CSS |
| Shared visualization | Members 3 & 4 | MapLibre GL JS, Plotly or ECharts |

> ⚠ As of 2026-11-05, only `digital-twin/` exists in the repo. `forecasting/`, `optimization/`, `backend/`, `frontend/` directories are absent — not yet scaffolded by their owners.

---

## Virtual Environment

| Item | Detail |
|---|---|
| Manager | `uv` (C:\Users\LOQ\.local\bin\uv.exe v≈2024) |
| Venv path | `digital-twin/.venv/` |
| Python binary | `digital-twin/.venv/Scripts/python.exe` |
| Python version | 3.12.15 |

Activation: `digital-twin\.venv\Scripts\activate`

---

## Key Configuration

- **Coordinate system:** EPSG:4326 everywhere. Coordinates always `[longitude, latitude]`.
- **Bounding box (Lonavala/Khandala):** `min_lon=73.35, min_lat=18.72, max_lon=73.46, max_lat=18.80`
- **Data contracts:** `forecast.json` (Member 1 → 2) and `dispatch.json` / scenario JSONs (Member 2 → 3 & 4)
- **Scenario IDs (exact):** `normal`, `cloudy`, `heavy_monsoon`, `high_wind`, `peak_demand`

---

## Testing Stack

| Tool | Version | Config |
|---|---|---|
| `pytest` | 9.2.0 | Run via `python -m pytest digital-twin/tests -v` from `C:\GRIDMATE` |
| No `.pytest.ini` or `pyproject.toml` | — | rootdir auto-detected as `C:\GRIDMATE` |

---

## Map / Visualization Stack

| Component | Technology | Source |
|---|---|---|
| Basemap | CartoDB Positron GL style (fallback: OpenStreetMap raster) | CDN — no API key required |
| Map library | **MapLibre GL JS 3.6.2** | `unpkg.com` CDN |
| Map demo | `digital-twin/map/index.html` | Static HTML, `python -m http.server 8000` from `digital-twin/` |
| JS dispatch engine | `digital-twin/map/applyDispatch.js` | Vanilla ES5-compatible UMD module |

<!-- refreshed: 2026-11-05 -->
*Sequential in-context analysis: 2026-11-05*

