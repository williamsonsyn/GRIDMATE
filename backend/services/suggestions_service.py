"""Suggestions service: calculates resource usage headroom, peak grid analysis,
and evaluates capacity expansion options via PyPSA optimization.
"""
from __future__ import annotations

import logging
from threading import Lock
from typing import Any

try:
    from .. import config
    from ..models.schemas import Scenario
    from . import mock_data, optimization_service
    from .scenario_service import service
except (ImportError, ValueError):
    import config  # type: ignore[no-redef]
    from models.schemas import Scenario  # type: ignore[no-redef]
    from services import mock_data, optimization_service  # type: ignore[no-redef]
    from services.scenario_service import service  # type: ignore[no-redef]

log = logging.getLogger(__name__)
JsonDict = dict[str, Any]
_lock = Lock()
_cache: dict[str, JsonDict] = {}


def _get_installed_capacities() -> dict[str, float]:
    """Get installed capacities in kW (and battery kWh)."""
    return {
        "solar": 600.0,
        "wind": 300.0,
        "hydro": 300.0,
        "battery_power": 100.0,
        "battery_capacity": 500.0,
        "grid": 1000.0,
    }


def _analyze_peak_grid(dispatch_rows: list[JsonDict]) -> tuple[list[str], str]:
    """Identify top peak grid hours and construct dynamic explanation."""
    if not dispatch_rows:
        return [], "No dispatch data available."

    sorted_by_grid = sorted(dispatch_rows, key=lambda r: float(r["grid_kw"]), reverse=True)
    top_hours = sorted_by_grid[:4]
    hour_labels = []
    for r in top_hours:
        ts = str(r["timestamp"])
        time_part = ts.split("T")[1][:5] if "T" in ts else ts[:5]
        hour_labels.append(time_part)

    # Average metrics during these peak grid hours
    avg_grid = sum(float(r["grid_kw"]) for r in top_hours) / len(top_hours)
    avg_solar = sum(float(r["solar_kw"]) for r in top_hours) / len(top_hours)
    avg_wind = sum(float(r["wind_kw"]) for r in top_hours) / len(top_hours)
    avg_bat = sum(float(r["battery_kw"]) for r in top_hours) / len(top_hours)
    avg_load = sum(float(r["load_kw"]) for r in top_hours) / len(top_hours)

    reasons: list[str] = []
    if avg_solar < 5.0:
        reasons.append("zero solar generation at night/evening")
    if avg_wind < 60.0:
        reasons.append(f"low ridge wind generation ({avg_wind:.0f} kW)")
    if avg_bat < 20.0:
        reasons.append("battery storage depleted or unavailable")

    hours_str = ", ".join(hour_labels)
    reason_str = ", and ".join(reasons) if reasons else "high industrial/commercial load demand"
    explanation = (
        f"Peak grid imports (averaging {avg_grid:.0f} kW out of {avg_load:.0f} kW load) "
        f"occur at {hours_str} primarily due to {reason_str}."
    )
    return hour_labels, explanation


def _calculate_resources(dispatch_rows: list[JsonDict]) -> list[JsonDict]:
    """Calculate installed capacity vs average and peak use, plus unused headroom."""
    caps = _get_installed_capacities()
    n = max(1, len(dispatch_rows))

    sources = [
        ("solar", "Solar Power", caps["solar"]),
        ("wind", "Wind Generation", caps["wind"]),
        ("hydro", "Small Hydro", caps["hydro"]),
        ("battery", "Battery Storage", caps["battery_power"]),
        ("grid", "Grid Intertie", caps["grid"]),
    ]

    resources = []
    for src_id, name, installed in sources:
        if src_id == "battery":
            powers = [abs(float(r["battery_kw"])) for r in dispatch_rows]
        else:
            powers = [float(r[f"{src_id}_kw"]) for r in dispatch_rows]

        avg_kw = round(sum(powers) / n, 1)
        peak_kw = round(max(powers) if powers else 0.0, 1)
        headroom_kw = round(max(0.0, installed - peak_kw), 1)
        headroom_pct = round((headroom_kw / installed) * 100.0, 1) if installed > 0 else 0.0

        item: JsonDict = {
            "source": src_id,
            "name": name,
            "installed_kw": installed,
            "avg_use_kw": avg_kw,
            "peak_use_kw": peak_kw,
            "headroom_kw": headroom_kw,
            "headroom_percent": headroom_pct,
        }
        if src_id == "battery":
            item["capacity_kwh"] = caps["battery_capacity"]
        resources.append(item)

    return resources


def _evaluate_candidate_options(
    forecast_data: JsonDict, base_grid_kwh: float, base_cost_rs: float
) -> list[JsonDict]:
    """Evaluate candidate capacity expansions with PyPSA optimizer and rank top 3."""
    options = [
        {
            "id": "hydro_100",
            "title": "Add +100 kW Small Hydro Capacity",
            "type": "hydro",
            "capacity_added": "+100 kW",
            "desc": "Provides reliable 24h baseline clean energy that displaces expensive evening and night grid imports.",
            "fc": {
                "location": forecast_data.get("location", "Lonavala"),
                "forecast": [
                    {**r, "hydro_kw": float(r["hydro_kw"]) * 400.0 / 300.0}
                    for r in forecast_data["forecast"]
                ],
            },
            "cfg": None,
        },
        {
            "id": "solar_200",
            "title": "Add +200 kW Solar PV",
            "type": "solar",
            "capacity_added": "+200 kW",
            "desc": "Substantially increases daytime solar generation, charging the battery earlier and eliminating daytime grid imports.",
            "fc": {
                "location": forecast_data.get("location", "Lonavala"),
                "forecast": [
                    {**r, "solar_kw": float(r["solar_kw"]) * 800.0 / 600.0}
                    for r in forecast_data["forecast"]
                ],
            },
            "cfg": None,
        },
        {
            "id": "solar_100",
            "title": "Add +100 kW Solar PV",
            "type": "solar",
            "capacity_added": "+100 kW",
            "desc": "Expands midday clean energy generation to offset peak daytime tariffs.",
            "fc": {
                "location": forecast_data.get("location", "Lonavala"),
                "forecast": [
                    {**r, "solar_kw": float(r["solar_kw"]) * 700.0 / 600.0}
                    for r in forecast_data["forecast"]
                ],
            },
            "cfg": None,
        },
        {
            "id": "wind_100",
            "title": "Add +100 kW Wind Generation",
            "type": "wind",
            "capacity_added": "+100 kW",
            "desc": "Strengthens afternoon and nighttime ridge generation when solar output is unavailable.",
            "fc": {
                "location": forecast_data.get("location", "Lonavala"),
                "forecast": [
                    {**r, "wind_kw": float(r["wind_kw"]) * 400.0 / 300.0}
                    for r in forecast_data["forecast"]
                ],
            },
            "cfg": None,
        },
        {
            "id": "battery_100_200",
            "title": "Add +100 kW / 200 kWh Battery Storage",
            "type": "battery",
            "capacity_added": "+100 kW / +200 kWh",
            "desc": "Expands storage buffer to capture surplus midday solar and discharge during high-tariff evening peak hours.",
            "fc": forecast_data,
            "cfg": {
                "battery": {
                    "capacity_kwh": 700,
                    "energy_capacity_kwh": 700,
                    "max_charge_kw": 200,
                    "maximum_charge_kw": 200,
                    "max_discharge_kw": 200,
                    "maximum_discharge_kw": 200,
                    "max_soc_kwh": 700,
                    "maximum_state_of_charge": 700,
                }
            },
        },
    ]

    evaluated = []
    for opt in options:
        try:
            if config.MODE == "mock":
                # Deterministic simulation estimator for mock mode
                if opt["type"] == "hydro":
                    red_kwh = min(base_grid_kwh * 0.12, 850.0)
                    sav_rs = red_kwh * 8.2
                elif opt["id"] == "solar_200":
                    red_kwh = min(base_grid_kwh * 0.10, 780.0)
                    sav_rs = red_kwh * 6.5
                elif opt["id"] == "solar_100":
                    red_kwh = min(base_grid_kwh * 0.05, 390.0)
                    sav_rs = red_kwh * 6.5
                elif opt["type"] == "wind":
                    red_kwh = min(base_grid_kwh * 0.02, 120.0)
                    sav_rs = red_kwh * 7.5
                else:
                    red_kwh = min(base_grid_kwh * 0.03, 180.0)
                    sav_rs = 600.0
            else:
                res = optimization_service.run_real_optimization(
                    opt["fc"], config_override=opt["cfg"]
                )
                g = sum(float(r["grid_kw"]) for r in res["dispatch"])
                c = float(res.get("cost", {}).get("total_grid_cost_rs", g * 8.0))
                red_kwh = max(0.0, base_grid_kwh - g)
                sav_rs = max(0.0, base_cost_rs - c)

            red_pct = (red_kwh / base_grid_kwh * 100.0) if base_grid_kwh > 0 else 0.0
            evaluated.append({
                "id": opt["id"],
                "title": opt["title"],
                "option_type": opt["type"],
                "capacity_added": opt["capacity_added"],
                "grid_reduction_kwh": round(red_kwh, 1),
                "grid_reduction_percent": round(red_pct, 1),
                "savings_rs": round(sav_rs, 1),
                "description": opt["desc"],
            })
        except Exception:
            log.exception("Failed to evaluate option %s", opt["id"])

    # Rank best first: prioritize cost savings, then grid kWh reduction
    evaluated.sort(key=lambda x: (x["savings_rs"], x["grid_reduction_kwh"]), reverse=True)

    # Return top 3 options ranked
    ranked_top_3 = []
    for rank, item in enumerate(evaluated[:3], start=1):
        ranked_top_3.append({"rank": rank, **item})

    return ranked_top_3


def get_suggestions(scenario: Scenario, date: str | None = None) -> JsonDict:
    """Generate resource headroom metrics and PyPSA-derived grid reduction suggestions."""
    key = f"{scenario.value}::{date or 'default'}"
    with _lock:
        if key in _cache:
            return _cache[key]

        # 1. Get forecast and base dispatch
        forecast_data, _, _, _ = service._forecast(scenario, date)
        if config.MODE == "mock":
            base_dispatch = mock_data.get_mock_dispatch(forecast_data, scenario.value)["dispatch"]
            base_grid_kwh = sum(float(r["grid_kw"]) for r in base_dispatch)
            base_cost_rs = base_grid_kwh * 8.0
        else:
            base_res = optimization_service.run_real_optimization(forecast_data)
            base_dispatch = base_res["dispatch"]
            base_grid_kwh = sum(float(r["grid_kw"]) for r in base_dispatch)
            base_cost_rs = float(base_res.get("cost", {}).get("total_grid_cost_rs", base_grid_kwh * 8.0))

        # 2. Resources capacity vs use
        resources = _calculate_resources(base_dispatch)

        # 3. Peak grid hours and root cause
        peak_hours, peak_reason = _analyze_peak_grid(base_dispatch)

        # 4. PyPSA candidate options evaluation
        suggestions = _evaluate_candidate_options(forecast_data, base_grid_kwh, base_cost_rs)

        result: JsonDict = {
            "scenario": scenario.value,
            "date": date,
            "peak_grid_hours": peak_hours,
            "peak_grid_reason": peak_reason,
            "resources": resources,
            "suggestions": suggestions,
            "note": "Estimates from the simulation",
        }
        _cache[key] = result
        return result


def reset_cache() -> None:
    """Clear cached suggestion results."""
    with _lock:
        _cache.clear()

