"""Digital Twin internal microservice for GridMate.

Serves GIS GeoJSON layers and MapLibre configuration for the Lonavala testbed.
"""
from __future__ import annotations

from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

log = logging.getLogger(__name__)

app = FastAPI(
    title="GridMate Digital Twin Service",
    description="Internal microservice serving GIS layers and digital twin topology",
    version="1.0.0",
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MAP_CONFIG_PATH = BASE_DIR / "map" / "map_config.json"

_LAYERS = {
    "assets": "assets.geojson",
    "demand_zones": "demand_zones.geojson",
    "water_features": "water_features.geojson",
    "power_lines": "power_lines.geojson",
    "energy_flow": "energy_flow_template.geojson",
    "roads": "roads.geojson",
}


@lru_cache(maxsize=1)
def _load_layers() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, fname in _LAYERS.items():
        file_path = DATA_DIR / fname
        if not file_path.exists():
            raise FileNotFoundError(f"Missing GIS layer file: {fname} at {file_path}")
        out[key] = json.loads(file_path.read_text(encoding="utf-8"))

    if not out.get("assets", {}).get("features"):
        raise ValueError("assets.geojson contains no features")

    try:
        out["map_config"] = json.loads(MAP_CONFIG_PATH.read_text(encoding="utf-8"))
    except OSError:
        out["map_config"] = {"center": [73.41, 18.76], "zoom": 10}

    return out


@app.get("/health", tags=["health"])
def health() -> dict[str, Any]:
    all_ok = all((DATA_DIR / f).exists() for f in _LAYERS.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "digital-twin",
        "layers_present": all_ok,
    }


@app.get("/assets", tags=["gis"])
def get_assets() -> dict[str, Any]:
    try:
        return _load_layers()
    except Exception as exc:
        log.exception("Failed to load digital twin GIS layers")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

