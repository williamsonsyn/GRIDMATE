"""GridMate FastAPI application.

Run from the repository root:  uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import dispatch, forecast, metrics, scenarios, summary
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


@api.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    components = {
        "forecasting": (config.FORECAST_SRC / "predict.py").exists(),
        "optimization": (config.OPTIMIZATION_SRC / "optimizer.py").exists(),
        "digital_twin": (config.GIS_DIR / "assets.geojson").exists(),
    }
    detail: dict[str, str] = {}
    if config.MODE != "mock":
        for name, ok in components.items():
            if not ok:
                detail[name] = "module files not found; mock fallback will be used"
    status = "ok" if config.MODE == "mock" or all(components.values()) else "degraded"
    return HealthResponse(status=status, mode=config.MODE, components=components, detail=detail)


api.include_router(forecast.router)
api.include_router(dispatch.router)
api.include_router(metrics.router)
api.include_router(scenarios.router)
api.include_router(summary.router)
app.include_router(api)

_ = assets_service  # imported for side-effect-free availability
