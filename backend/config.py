"""Central configuration. All paths are relative to the repository root."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.getenv("GRIDMATE_REPO_ROOT", Path(__file__).resolve().parents[1]))

FORECAST_SRC = REPO_ROOT / "forecasting_real_data" / "src"
OPTIMIZATION_DIR = REPO_ROOT / "optimization"
OPTIMIZATION_SRC = OPTIMIZATION_DIR / "src"
OPTIMIZATION_CONFIG = OPTIMIZATION_DIR / "config" / "system_config.json"
GIS_DIR = Path(os.getenv("GRIDMATE_GIS_DIR", REPO_ROOT / "digital-twin" / "data"))
MAP_CONFIG = REPO_ROOT / "digital-twin" / "map" / "map_config.json"

# real  -> only use Member 1/2/3 modules (errors surface as HTTP 503)
# mock  -> only use built-in mock data
# auto  -> use real modules, fall back to mock data if one fails
MODE = os.getenv("GRIDMATE_MODE", "auto").lower()

LOCATION = "Lonavala"
HORIZON_HOURS = 24
DATA_LABEL = (
    "Simulation Result - synthetic prototype data, "
    "not measured Lonavala data"
)
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "GRIDMATE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
