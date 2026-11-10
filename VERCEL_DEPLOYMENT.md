# GridMate: Vercel Multi-Service Deployment Guide

This document describes the production architecture, service boundaries, internal service bindings, and deployment procedures for running **GridMate** as a multi-service application on Vercel.

---

## 1. System Architecture Overview

GridMate is deployed on Vercel using the official **Vercel Multi-Service Architecture**.

```
                           Internet / User Browser
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │   Vercel Edge Router      │
                        │   (Shared Domain CDN)     │
                        └──────┬─────────────┬──────┘
                               │             │
                    /(.*)      │             │ /api/(.*)
           (Public Web App)    │             │ (Public API)
                               ▼             ▼
                    ┌──────────────┐   ┌──────────────┐
                    │   frontend   │   │   backend    │
                    │ (Vite+React) │   │  (FastAPI)   │
                    └──────────────┘   └──────┬───────┘
                                              │
                      ┌───────────────────────┼───────────────────────┐
                      │ FORECASTING_          │ OPTIMIZATION_         │ DIGITAL_TWIN_
                      │ SERVICE_URL           │ SERVICE_URL           │ SERVICE_URL
                      ▼                       ▼                       ▼
               ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
               │ forecasting  │        │ optimization │        │ digital-twin │
               │  (Internal)  │        │  (Internal)  │        │  (Internal)  │
               │ XGBoost ML   │        │ PyPSA + HiGHS│        │  GIS Layers  │
               └──────────────┘        └──────────────┘        └──────────────┘
```

### Service Responsibilities:

| Service | Root Directory | Framework / Runtime | Visibility | Description |
|---|---|---|---|---|
| **`frontend`** | `frontend/` | `vite` | **Public** | Vite 5 + React 18 SPA. Renders the interactive dashboard, charts, and digital twin map. |
| **`backend`** | `backend/` | `fastapi` | **Public** | FastAPI API Gateway. Exposes `/api/*` REST endpoints and coordinates downstream services. |
| **`forecasting`** | `forecasting_real_data/` | `python` | **Internal** | Runs XGBoost ML models for 24-hour ahead solar, wind, hydro, and demand forecasts. |
| **`optimization`** | `optimization/` | `python` | **Internal** | Solves the microgrid linear programming dispatch problem using PyPSA and the HiGHS solver. |
| **`digital-twin`** | `digital-twin/` | `python` | **Internal** | Serves static OpenStreetMap-derived GeoJSON layers and MapLibre configurations. |

---

## 2. Public Routing & Rewrite Rules

Vercel rewrites in `vercel.json` direct traffic seamlessly without requiring hardcoded domains:

```json
"rewrites": [
  {
    "source": "/api/(.*)",
    "destination": {
      "service": "backend"
    }
  },
  {
    "source": "/(.*)",
    "destination": {
      "service": "frontend"
    }
  }
]
```

- **Public Frontend:** `https://<domain>/` serves the Single Page Application.
- **Public API:** `https://<domain>/api/<endpoint>` routes directly to the FastAPI backend.
- **Internal Services:** `forecasting`, `optimization`, and `digital-twin` have **no** public rewrite rules. They cannot be reached from the public internet.

---

## 3. Internal Service Bindings

The `backend` communicates with private internal services using Vercel Service Bindings declared in `vercel.json`:

```json
"bindings": [
  {
    "type": "service",
    "service": "forecasting",
    "format": "url",
    "env": "FORECASTING_SERVICE_URL"
  },
  {
    "type": "service",
    "service": "optimization",
    "format": "url",
    "env": "OPTIMIZATION_SERVICE_URL"
  },
  {
    "type": "service",
    "service": "digital-twin",
    "format": "url",
    "env": "DIGITAL_TWIN_SERVICE_URL"
  }
]
```

At runtime, Vercel dynamically injects secure URLs for each service. The backend uses `httpx` to send requests to:
- `POST ${FORECASTING_SERVICE_URL}/predict`
- `POST ${OPTIMIZATION_SERVICE_URL}/optimize`
- `POST ${OPTIMIZATION_SERVICE_URL}/scenarios/all`
- `GET ${OPTIMIZATION_SERVICE_URL}/system-info`
- `GET ${DIGITAL_TWIN_SERVICE_URL}/assets`

---

## 4. Environment Variables Reference

| Variable | Target Service | Default (Local) | Production Value | Purpose |
|---|---|---|---|---|
| `GRIDMATE_MODE` | `backend` | `auto` | `auto` | `auto` uses real services with mock fallback; `real` enforces strict execution; `mock` forces demo data. |
| `GRIDMATE_CORS_ORIGINS` | `backend` | `http://localhost:5173,...` | `*` or domain | Configures FastAPI CORSMiddleware origins. |
| `FORECASTING_SERVICE_URL` | `backend` | *(unset)* | *(auto-injected)* | Vercel service binding to the internal forecasting service. |
| `OPTIMIZATION_SERVICE_URL` | `backend` | *(unset)* | *(auto-injected)* | Vercel service binding to the internal optimization service. |
| `DIGITAL_TWIN_SERVICE_URL` | `backend` | *(unset)* | *(auto-injected)* | Vercel service binding to the internal digital-twin service. |
| `VITE_API_BASE` | `frontend` | `""` | `""` | API prefix for frontend requests. Keep empty to use relative `/api` paths. |
| `VITE_API_PROXY` | `frontend` | `http://127.0.0.1:8000` | *(unused in prod)* | Vite dev-server proxy target for local development. |

---

## 5. Deployment Instructions

### Prerequisites:
1. Install [Vercel CLI](https://vercel.com/docs/cli):
   ```bash
   npm install -g vercel
   ```
2. Authenticate with your Vercel account:
   ```bash
   vercel login
   ```

### Step 1: Link Project
In the repository root directory (`c:\GRIDMATE`):
```bash
vercel link
```

### Step 2: Validate Multi-Service Routing Locally
To run and test the complete multi-service stack with Vercel's emulation:
```bash
vercel dev
```

### Step 3: Deploy Preview / Staging
Deploy a preview deployment to verify build logs, service definitions, and bindings:
```bash
vercel
```

### Step 4: Deploy to Production
Once verified, deploy to production:
```bash
vercel --prod
```

---

## 6. Local Development (Preserved Workflow)

The multi-service architecture is designed with **dual-mode backward compatibility**. You do **not** need to run 5 separate services locally:

- **Windows PowerShell:**
  ```powershell
  .\start.ps1
  ```
- **Linux / macOS:**
  ```bash
  ./start.sh
  ```

When `*_SERVICE_URL` environment variables are absent, `backend` automatically imports and executes the local Python modules directly in-process.

---

## 7. Packaging Exclusions & Deployment Sizing

To prevent massive local development virtual environments (`.venv`), cache artifacts, and raw node_modules from being uploaded to Vercel, a root [`.vercelignore`](file:///C:/GRIDMATE/.vercelignore) and service-level `.vercelignore` files are enforced.

### Payload Measurements (Before vs. After Packaging Corrections):

| Service | Raw Local Size (with .venv / node_modules) | Clean Deployment Upload Size | Files Uploaded | Reduction |
|---|---|---|---|---|
| **`digital-twin`** | 1,032.97 MB (includes 1.001 GB `.venv`) | **5.98 MB** (source & GeoJSON) | 47 files | **99.4%** |
| **`frontend`** | 198.90 MB (includes 196.9 MB `node_modules`) | **1.96 MB** (source files) | 46 files | **99.0%** |
| **`forecasting`** | 5.49 MB | **5.44 MB** (source & trained models) | 30 files | Excludes cache |
| **`backend`** | 0.26 MB | **0.08 MB** (API source files) | 25 files | Excludes cache |
| **`optimization`** | 0.22 MB | **0.17 MB** (solver scripts & config) | 21 files | Excludes cache |
| **TOTAL** | **1,237.84 MB** | **13.63 MB** | **169 files** | **98.9% reduction** |

### Verified Inclusions:
- All required GeoJSON datasets (`assets.geojson`, `demand_zones.geojson`, `water_features.geojson`, `roads.geojson`, `power_lines.geojson`, `energy_flow_template.geojson`).
- All 4 trained XGBoost `.joblib` models (`solar_model.joblib`, `wind_model.joblib`, `hydro_model.joblib`, `load_model.joblib`) and weather datasets in `forecasting_real_data/`.
- All PyPSA configuration and solver scripts in `optimization/`.
- All FastAPI source code and TypeScript frontend source code.

### Verified Exclusions:
- Virtual environments (`.venv/`, `venv/`, `env/`, `ENV/`) across all root and nested service folders.
- Python bytecode and compiler caches (`__pycache__/`, `*.pyc`, `*.pyo`).
- Test and linter caches (`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`).
- Development and diagnostic logs (`logs/`, `*.log`).
- Node package installations (`node_modules/` — installed dynamically by Vercel during build).

