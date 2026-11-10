"""Optimization service: wraps Member 2's optimize_dispatch() (PyPSA + HiGHS).

Supports both Vercel internal service binding (via OPTIMIZATION_SERVICE_URL)
and local in-process execution with mock fallback.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from threading import Lock
from typing import Any

import httpx

from .. import config
from . import mock_data

log = logging.getLogger(__name__)
JsonDict = dict[str, Any]
_lock = Lock()

_DISPATCH_KEYS = (
    "solar_kw", "wind_kw", "hydro_kw", "battery_kw", "grid_kw",
    "load_kw", "curtailment_kw", "battery_soc_kwh",
)
_NON_NEGATIVE = {"solar_kw", "wind_kw", "hydro_kw", "grid_kw", "curtailment_kw"}


class OptimizationError(RuntimeError):
    """Raised when the dispatch cannot be optimized."""


def _get_service_url() -> str | None:
    url = os.getenv("OPTIMIZATION_SERVICE_URL")
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url.rstrip("/")


def _load_optimizer() -> Any:
    src = str(config.OPTIMIZATION_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    import optimizer  # type: ignore[import-not-found]  # Member 2 module

    return optimizer


def _clean_dispatch(rows: list[JsonDict]) -> list[JsonDict]:
    """Round, and remove tiny negative / '-0.0' solver noise on non-negative fields."""
    out = []
    for r in rows:
        row: JsonDict = {"timestamp": str(r["timestamp"])}
        for k in _DISPATCH_KEYS:
            v = round(float(r[k]), 2) + 0.0
            if k in _NON_NEGATIVE and v < 0:
                v = 0.0
            row[k] = v
        out.append(row)
    return out


def get_system_info() -> dict[str, float]:
    """Battery/grid parameters actually used by the optimizer."""
    service_url = _get_service_url()
    if service_url:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{service_url}/system-info")
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("Could not fetch system-info from remote service (%s); reading config", exc)

    try:
        cfg = json.loads(Path(config.OPTIMIZATION_CONFIG).read_text())
        b, g = cfg["battery"], cfg["grid"]
        return {
            "battery_capacity_kwh": float(b["energy_capacity_kwh"]),
            "battery_max_charge_kw": float(b["maximum_charge_kw"]),
            "battery_max_discharge_kw": float(b["maximum_discharge_kw"]),
            "battery_min_soc_kwh": float(b["minimum_state_of_charge"]),
            "grid_capacity_kw": float(g["capacity_kw"]),
        }
    except (OSError, KeyError, ValueError):
        d = mock_data.get_mock_system()
        return {k: d[k] for k in (
            "battery_capacity_kwh", "battery_max_charge_kw", "battery_max_discharge_kw",
            "battery_min_soc_kwh", "grid_capacity_kw")}


def run_real_optimization(forecast: JsonDict, config_override: dict | None = None) -> JsonDict:
    service_url = _get_service_url()
    if service_url:
        payload = {"forecast": forecast, "config_override": config_override}
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(f"{service_url}/optimize", json=payload)
                resp.raise_for_status()
                result = resp.json()
            return {
                "location": result.get("location", config.LOCATION),
                "dispatch": _clean_dispatch(result["dispatch"]),
                "metrics": result["metrics"],
                "cost": result.get("cost"),
            }
        except Exception as exc:
            log.exception("Remote optimization service request failed: %s", exc)
            raise OptimizationError(f"Optimization service error: {exc}") from exc

    with _lock:
        optimizer = _load_optimizer()
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                result = optimizer.optimize_dispatch(
                    forecast, output_path=Path(tmp) / "dispatch.json", config_override=config_override
                )
    return {
        "location": result.get("location", config.LOCATION),
        "dispatch": _clean_dispatch(result["dispatch"]),
        "metrics": result["metrics"],
        "cost": result.get("extra_metrics"),
    }


def optimize(forecast: JsonDict, scenario: str) -> tuple[JsonDict, str, list[str]]:
    """Return (result, source, warnings). Source is 'pypsa' or 'mock'."""
    if not forecast.get("forecast"):
        raise OptimizationError("Cannot optimize an empty forecast.")

    def _mock() -> JsonDict:
        d = mock_data.get_mock_dispatch(forecast, scenario)
        return {**d, "metrics": mock_data.get_mock_metrics(d), "cost": None}

    if config.MODE == "mock":
        return _mock(), "mock", []
    try:
        return run_real_optimization(forecast), "pypsa", []
    except Exception as exc:  # noqa: BLE001
        log.exception("Real optimization failed for scenario %s", scenario)
        if config.MODE == "real":
            raise OptimizationError(f"Optimization failed: {exc}") from exc
        return _mock(), "mock", [
            f"PyPSA optimizer could not produce a dispatch ({str(exc)[:160]}); "
            "showing rule-based mock dispatch instead."
        ]


def run_all_scenarios(base_forecast: JsonDict | None = None) -> list[JsonDict]:
    """Run all 5 scenarios and return their summary together."""
    if config.MODE == "mock":
        return mock_data.get_mock_scenarios_summary()

    service_url = _get_service_url()
    if service_url:
        payload = {"base_forecast": base_forecast}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{service_url}/scenarios/all", json=payload)
                resp.raise_for_status()
                rows = resp.json().get("rows", [])
                return rows or mock_data.get_mock_scenarios_summary()
        except Exception as exc:
            log.exception("Remote optimization run_all_scenarios failed: %s", exc)
            if config.MODE == "real":
                raise OptimizationError(f"Running all scenarios failed: {exc}") from exc
            return mock_data.get_mock_scenarios_summary()

    with _lock:
        src = str(config.OPTIMIZATION_SRC)
        if src not in sys.path:
            sys.path.insert(0, src)
        import run_scenarios  # type: ignore[import-not-found]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rows = run_scenarios.run_all_scenarios(base_forecast=base_forecast)
                return rows or mock_data.get_mock_scenarios_summary()
        except Exception as exc:  # noqa: BLE001
            log.exception("run_all_scenarios failed: %s", exc)
            if config.MODE == "real":
                raise OptimizationError(f"Running all scenarios failed: {exc}") from exc
            return mock_data.get_mock_scenarios_summary()
