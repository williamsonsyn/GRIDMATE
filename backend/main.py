"""GridMate FastAPI application.

Run from the repository root:  uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import os
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from . import config
from .api import dispatch, forecast, metrics, scenarios, suggestions, summary
from .models.schemas import HealthResponse
from .services import assets_service

app = FastAPI(
    title="GridMate API",
    description="From Weather to Watts, Intelligently. Lonavala microgrid prototype (synthetic data).",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


def _probe_service(env_var: str, default_local_file: bool) -> bool:
    url = os.getenv(env_var)
    if not url:
        return default_local_file
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{url.rstrip('/')}/health")
            return resp.status_code == 200
    except Exception:
        return False


@api.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    components = {
        "forecasting": _probe_service(
            "FORECASTING_SERVICE_URL", (config.FORECAST_SRC / "predict.py").exists()
        ),
        "optimization": _probe_service(
            "OPTIMIZATION_SERVICE_URL", (config.OPTIMIZATION_SRC / "optimizer.py").exists()
        ),
        "digital_twin": _probe_service(
            "DIGITAL_TWIN_SERVICE_URL", (config.GIS_DIR / "assets.geojson").exists()
        ),
    }
    detail: dict[str, str] = {}
    if config.MODE != "mock":
        for name, ok in components.items():
            if not ok:
                detail[name] = "service or module files not reachable; mock fallback will be used"
    status = "ok" if config.MODE == "mock" or all(components.values()) else "degraded"
    return HealthResponse(status=status, mode=config.MODE, components=components, detail=detail)


api.include_router(forecast.router)
api.include_router(dispatch.router)
api.include_router(metrics.router)
api.include_router(scenarios.router)
api.include_router(summary.router)
api.include_router(suggestions.router)
app.include_router(api)

_ = assets_service  # imported for side-effect-free availability
