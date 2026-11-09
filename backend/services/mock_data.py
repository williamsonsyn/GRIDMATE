"""Temporary mock data so the app runs even if a real module is unavailable.

Mock results are illustrative only. They are used when GRIDMATE_MODE=mock, or
as a fallback in GRIDMATE_MODE=auto when a real module fails.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .. import config

JsonDict = dict[str, Any]

_BASE = datetime(2026, 10, 1, 0, 0, 0)

# multiplier per scenario: solar, wind, hydro, load, evening-load boost
_SCENARIO_FACTORS: dict[str, dict[str, float]] = {
    "normal": {"solar": 1.0, "wind": 1.0, "hydro": 1.0, "load": 1.0, "evening": 0.0},
    "cloudy": {"solar": 0.35, "wind": 1.0, "hydro": 1.0, "load": 1.0, "evening": 0.0},
    "heavy_monsoon": {"solar": 0.2, "wind": 1.2, "hydro": 1.7, "load": 1.0, "evening": 0.0},
    "high_wind": {"solar": 1.0, "wind": 2.6, "hydro": 1.0, "load": 1.0, "evening": 0.0},
    "peak_demand": {"solar": 1.0, "wind": 1.0, "hydro": 1.0, "load": 1.15, "evening": 0.35},
}

_DEFAULT_SYSTEM = {
    "battery_capacity_kwh": 500.0,
    "battery_max_charge_kw": 100.0,
    "battery_max_discharge_kw": 100.0,
    "battery_min_soc_kwh": 50.0,
    "battery_initial_soc_kwh": 200.0,
    "battery_charge_eff": 0.95,
    "battery_discharge_eff": 0.95,
    "grid_capacity_kw": 1000.0,
    "grid_emission_factor": 0.7,
}


def get_mock_forecast(scenario: str = "normal") -> JsonDict:
    f = _SCENARIO_FACTORS[scenario]
    rows = []
    for h in range(config.HORIZON_HOURS):
        solar = 420 * max(0.0, math.sin(math.pi * (h - 6) / 12)) * f["solar"]
        wind = (180 + 70 * math.sin(math.pi * (h + 3) / 12)) * f["wind"]
        hydro = 250 * f["hydro"]
        evening = f["evening"] * math.exp(-((h - 19) ** 2) / 8)
        load = (620 + 280 * math.sin(math.pi * (h - 8) / 14) ** 2) * f["load"] * (1 + evening)
        rows.append(
            {
                "timestamp": (_BASE + timedelta(hours=h)).isoformat(),
                "solar_kw": round(solar, 2),
                "wind_kw": round(wind, 2),
                "hydro_kw": round(hydro, 2),
                "load_kw": round(load, 2),
            }
        )
    return {
        "location": config.LOCATION,
        "forecast_horizon_hours": config.HORIZON_HOURS,
        "forecast": rows,
    }


def get_mock_system() -> dict[str, float]:
    return dict(_DEFAULT_SYSTEM)


def get_mock_dispatch(forecast: JsonDict | None = None, scenario: str = "normal") -> JsonDict:
    """Greedy rule-based dispatch (renewables -> battery -> grid). Not PyPSA."""
    forecast = forecast or get_mock_forecast(scenario)
    s = _DEFAULT_SYSTEM
    soc = s["battery_initial_soc_kwh"]
    rows = []
    for p in forecast["forecast"]:
        ren = p["solar_kw"] + p["wind_kw"] + p["hydro_kw"]
        load = p["load_kw"]
        battery = grid = curtail = 0.0
        if ren >= load:
            surplus = ren - load
            room = (s["battery_capacity_kwh"] - soc) / s["battery_charge_eff"]
            charge = min(surplus, s["battery_max_charge_kw"], room)
            soc += charge * s["battery_charge_eff"]
            battery = -charge
            curtail = surplus - charge
        else:
            deficit = load - ren
            avail = (soc - s["battery_min_soc_kwh"]) * s["battery_discharge_eff"]
            discharge = max(0.0, min(deficit, s["battery_max_discharge_kw"], avail))
            soc -= discharge / s["battery_discharge_eff"]
            battery = discharge
            grid = deficit - discharge
        rows.append(
            {
                "timestamp": p["timestamp"],
                "solar_kw": p["solar_kw"],
                "wind_kw": p["wind_kw"],
                "hydro_kw": p["hydro_kw"],
                "battery_kw": round(battery, 2),
                "grid_kw": round(grid, 2),
                "load_kw": load,
                "curtailment_kw": round(curtail, 2),
                "battery_soc_kwh": round(soc, 2),
            }
        )
    return {"location": config.LOCATION, "dispatch": rows}


def get_mock_metrics(dispatch: JsonDict | None = None, scenario: str = "normal") -> JsonDict:
    rows = (dispatch or get_mock_dispatch(scenario=scenario))["dispatch"]
    load = sum(r["load_kw"] for r in rows) or 1.0
    grid = sum(r["grid_kw"] for r in rows)
    curtail = sum(r["curtailment_kw"] for r in rows)
    ren_gen = sum(r["solar_kw"] + r["wind_kw"] + r["hydro_kw"] for r in rows) or 1.0
    thru = sum(abs(r["battery_kw"]) for r in rows)
    ef = _DEFAULT_SYSTEM["grid_emission_factor"]
    return {
        "renewable_penetration_percent": round(max(0.0, (load - grid) / load * 100), 2),
        "grid_dependency_percent": round(grid / load * 100, 2),
        "curtailment_percent": round(curtail / ren_gen * 100, 2),
        "battery_utilization_percent": round(
            thru / (2 * _DEFAULT_SYSTEM["battery_capacity_kwh"]) * 100, 2
        ),
        "estimated_co2_avoided_kg": round((load - grid) * ef, 2),
    }


def _point(coords: list[float], props: JsonDict) -> JsonDict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": coords}, "properties": props}


def get_mock_assets() -> JsonDict:
    """Minimal fallback map data (illustrative coordinates, not real infrastructure)."""
    note = "Mock prototype asset. Coordinates are illustrative."
    base = {"is_synthetic": True, "data_source": "mock", "note": note}
    items = [
        ("solar_mock", "solar", "Mock Solar", 73.40, 18.76, 350),
        ("wind_mock", "wind", "Mock Wind", 73.47, 18.72, 200),
        ("hydro_mock", "hydro", "Mock Hydro", 73.35, 18.78, 250),
        ("battery_mock", "battery", "Mock Battery", 73.41, 18.75, 500),
        ("grid_mock", "grid", "Mock Grid Intertie", 73.43, 18.77, 1000),
        ("demand_mock", "demand", "Mock Demand Hub", 73.41, 18.75, 900),
    ]
    feats = [
        _point([lon, lat], {"id": i, "type": t, "name": n, "capacity_kw": c, "status": "active", **base})
        for i, t, n, lon, lat, c in items
    ]
    empty: JsonDict = {"type": "FeatureCollection", "features": []}
    return {
        "assets": {"type": "FeatureCollection", "features": feats},
        "demand_zones": dict(empty),
        "water_features": dict(empty),
        "power_lines": dict(empty),
        "energy_flow": dict(empty),
        "map_config": {"center": [73.41, 18.75], "zoom": 10},
    }


def get_mock_scenarios_summary() -> list[JsonDict]:
    """Mock summary rows matching run_scenarios.py output."""
    labels = {
        "normal": "Normal Day",
        "cloudy": "Cloudy Day",
        "heavy_monsoon": "Heavy Monsoon",
        "high_wind": "High Wind",
        "peak_demand": "Peak Demand",
    }
    base_metrics = {
        "normal": {"cost": 42009.12, "savings": 93974.88, "battery": 4.17, "ren": 71.63, "grid": 28.37, "co2": 8819.78},
        "cloudy": {"cost": 62293.64, "savings": 73690.36, "battery": 4.17, "ren": 54.28, "grid": 45.72, "co2": 6683.45},
        "heavy_monsoon": {"cost": 56240.24, "savings": 86542.96, "battery": 4.17, "ren": 60.42, "grid": 39.58, "co2": 7811.50},
        "high_wind": {"cost": 26413.44, "savings": 109570.56, "battery": 4.17, "ren": 83.25, "grid": 16.75, "co2": 10250.30},
        "peak_demand": {"cost": 82804.32, "savings": 93974.88, "battery": 4.17, "ren": 55.10, "grid": 44.90, "co2": 8819.78},
    }
    rows = []
    for sc, m in base_metrics.items():
        grid_only = m["cost"] + m["savings"]
        rows.append({
            "scenario": sc,
            "label": labels[sc],
            "renewable_penetration_percent": m["ren"],
            "grid_dependency_percent": m["grid"],
            "curtailment_percent": 0.0,
            "battery_utilization_percent": m["battery"],
            "estimated_co2_avoided_kg": m["co2"],
            "total_grid_cost_rs": m["cost"],
            "grid_only_cost_rs": grid_only,
            "savings_rs": m["savings"],
            "savings_percent": round((m["savings"] / grid_only) * 100, 1),
            "validation": "PASS",
        })
    return rows
