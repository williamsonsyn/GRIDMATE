"""Optimization internal microservice for GridMate.

PyPSA linear programming optimizer using HiGHS solver to determine the hourly dispatch
of Solar, Wind, Hydro, Battery, and Grid.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
CONFIG_FILE = BASE_DIR / "config" / "system_config.json"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import optimizer  # type: ignore[import-not-found]
import run_scenarios  # type: ignore[import-not-found]

app = FastAPI(
    title="GridMate Optimization Service",
    description="Internal microservice for PyPSA + HiGHS microgrid dispatch optimization",
    version="1.0.0",
)


class OptimizePayload(BaseModel):
    forecast: dict[str, Any]
    config_override: Optional[dict[str, Any]] = None


class ScenariosPayload(BaseModel):
    base_forecast: Optional[dict[str, Any]] = None


@app.get("/health", tags=["health"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "optimization",
        "solver": "highs",
        "config_present": CONFIG_FILE.exists(),
    }


@app.get("/system-info", tags=["optimization"])
def get_system_info() -> dict[str, float]:
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        b, g = cfg["battery"], cfg["grid"]
        return {
            "battery_capacity_kwh": float(b.get("energy_capacity_kwh", b.get("capacity_kwh", 500))),
            "battery_max_charge_kw": float(b.get("maximum_charge_kw", b.get("max_charge_kw", 100))),
            "battery_max_discharge_kw": float(b.get("maximum_discharge_kw", b.get("max_discharge_kw", 100))),
            "battery_min_soc_kwh": float(b.get("minimum_state_of_charge", b.get("min_soc_kwh", 50))),
            "grid_capacity_kw": float(g.get("capacity_kw", g.get("grid_capacity_kw", 1000))),
        }
    except Exception as exc:
        log.exception("Failed to load system config")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/optimize", tags=["optimization"])
def optimize(payload: OptimizePayload) -> dict[str, Any]:
    if not payload.forecast.get("forecast"):
        raise HTTPException(status_code=400, detail="Cannot optimize an empty forecast.")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                result = optimizer.optimize_dispatch(
                    payload.forecast,
                    output_path=Path(tmp) / "dispatch.json",
                    config_override=payload.config_override,
                )
        return {
            "location": result.get("location", "Lonavala"),
            "dispatch": result["dispatch"],
            "metrics": result["metrics"],
            "cost": result.get("extra_metrics"),
        }
    except Exception as exc:
        log.exception("Optimization run failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/scenarios/all", tags=["optimization"])
def run_all(payload: Optional[ScenariosPayload] = None) -> dict[str, Any]:
    try:
        base_forecast = payload.base_forecast if payload else None
        with contextlib.redirect_stdout(io.StringIO()):
            rows = run_scenarios.run_all_scenarios(base_forecast=base_forecast)
        return {"rows": rows}
    except Exception as exc:
        log.exception("Run all scenarios failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

