"""Assets service: serves Member 3's Lonavala Digital Twin GeoJSON.

Supports both Vercel internal service binding (via DIGITAL_TWIN_SERVICE_URL)
and local in-process execution with mock fallback.
"""
from __future__ import annotations

from functools import lru_cache
import json
import logging
import os
from typing import Any

import httpx

from .. import config
from . import mock_data

log = logging.getLogger(__name__)
JsonDict = dict[str, Any]

_LAYERS = {
    "assets": "assets.geojson",
    "demand_zones": "demand_zones.geojson",
    "water_features": "water_features.geojson",
    "power_lines": "power_lines.geojson",
    "energy_flow": "energy_flow_template.geojson",
    "roads": "roads.geojson",
}


def _get_service_url() -> str | None:
    url = os.getenv("DIGITAL_TWIN_SERVICE_URL")
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url.rstrip("/")


@lru_cache(maxsize=1)
def _load_real() -> JsonDict:
    out: JsonDict = {}
    for key, fname in _LAYERS.items():
        out[key] = json.loads((config.GIS_DIR / fname).read_text(encoding="utf-8"))
    if not out["assets"].get("features"):
        raise ValueError("assets.geojson has no features")
    try:
        out["map_config"] = json.loads(config.MAP_CONFIG.read_text(encoding="utf-8"))
    except OSError:
        out["map_config"] = {"center": [73.41, 18.76], "zoom": 10}
    return out


def get_assets() -> tuple[JsonDict, str]:
    """Return (layers, source) where source is 'digital_twin' or 'mock'."""
    service_url = _get_service_url()
    if service_url:
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{service_url}/assets")
                resp.raise_for_status()
                return resp.json(), "digital_twin"
        except Exception as exc:
            log.exception("Remote digital twin service failed: %s", exc)
            if config.MODE == "real":
                raise RuntimeError(f"Digital twin service error: {exc}") from exc
            return mock_data.get_mock_assets(), "mock"

    if config.MODE != "mock":
        try:
            return _load_real(), "digital_twin"
        except Exception:  # noqa: BLE001
            log.exception("Could not load digital twin GeoJSON")
            if config.MODE == "real":
                raise
    return mock_data.get_mock_assets(), "mock"
