"""
map_utils.py
Utilities for integrating energy dispatch data with the Lonavala GIS Digital Twin.

Functions:
- load_dispatch(path_or_dict, timestamp_or_index=0) -> dict
- apply_dispatch(assets_geojson, dispatch_row, scenario_id=None) -> dict (GeoJSON)
- build_energy_flow(dispatch_row, assets_geojson) -> dict (GeoJSON)

Resource names and contracts strictly follow GRIDMATE_ARCHITECTURE.md:
solar_kw, wind_kw, hydro_kw, battery_kw, grid_kw, load_kw, curtailment_kw, battery_soc_kwh

Battery sign convention:
battery_kw > 0 : Discharging (supplying energy to load)
battery_kw < 0 : Charging (absorbing energy from renewables)
battery_kw = 0 : Idle
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


def load_dispatch(
    path_or_dict: Union[str, Path, Dict[str, Any]],
    timestamp_or_index: Union[int, str] = 0
) -> Dict[str, Any]:
    """
    Loads dispatch row from a file path or python dictionary.
    Supports:
    1. Standard architecture contract: {"location": ..., "dispatch": [rows...], "metrics": ...}
    2. Flat single-object dispatch: {"solar_kw": 420, "load_kw": 900, ...}
    """
    if isinstance(path_or_dict, (str, Path)):
        p = Path(path_or_dict)
        if not p.exists():
            raise FileNotFoundError(f"Dispatch file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(path_or_dict, dict):
        data = path_or_dict
    else:
        raise TypeError(f"Expected path or dict, got {type(path_or_dict)}")

    # Check if standard dispatch array format
    if "dispatch" in data and isinstance(data["dispatch"], list) and len(data["dispatch"]) > 0:
        rows = data["dispatch"]
        selected_row = None
        if isinstance(timestamp_or_index, int):
            idx = max(0, min(timestamp_or_index, len(rows) - 1))
            selected_row = copy.deepcopy(rows[idx])
        elif isinstance(timestamp_or_index, str):
            for r in rows:
                if str(r.get("timestamp")) == timestamp_or_index:
                    selected_row = copy.deepcopy(r)
                    break
            if selected_row is None:
                selected_row = copy.deepcopy(rows[0])
        else:
            selected_row = copy.deepcopy(rows[0])

        # Attach top-level metadata if available
        if "scenario_id" in data and "scenario_id" not in selected_row:
            selected_row["scenario_id"] = data["scenario_id"]
        if "metrics" in data and "metrics" not in selected_row:
            selected_row["metrics"] = data["metrics"]
        return selected_row

    # Flat single dispatch row
    required_keys = ["solar_kw", "wind_kw", "hydro_kw", "battery_kw", "grid_kw", "load_kw"]
    if any(k in data for k in required_keys):
        return copy.deepcopy(data)

    raise ValueError("Invalid dispatch structure: does not contain 'dispatch' array or standard dispatch fields.")


def apply_dispatch(
    assets_geojson: Union[str, Path, Dict[str, Any]],
    dispatch_row: Dict[str, Any],
    scenario_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Applies dispatch power flows to asset features:
    - Proportionally distributes type generation across multiple assets of the same type based on capacity_kw.
    - Sets forecast_output_kw, status, utilization_percent, and scenario.
    - Status values: active, idle, charging, discharging, not_supplying.
    - Guarantees forecast_output_kw is never negative.
    """
    if isinstance(assets_geojson, (str, Path)):
        with open(assets_geojson, "r", encoding="utf-8") as f:
            assets_fc = json.load(f)
    else:
        assets_fc = copy.deepcopy(assets_geojson)

    effective_scenario = scenario_id or dispatch_row.get("scenario_id") or "Simulated Scenario"

    # Extract raw generation values (strictly non-negative inputs for solar, wind, hydro, grid, load)
    solar_total = max(0.0, float(dispatch_row.get("solar_kw", 0.0)))
    wind_total = max(0.0, float(dispatch_row.get("wind_kw", 0.0)))
    hydro_total = max(0.0, float(dispatch_row.get("hydro_kw", 0.0)))
    grid_total = max(0.0, float(dispatch_row.get("grid_kw", 0.0)))
    load_total = max(0.0, float(dispatch_row.get("load_kw", 0.0)))
    battery_val = float(dispatch_row.get("battery_kw", 0.0))
    battery_soc = dispatch_row.get("battery_soc_kwh")

    # Group assets by type to calculate capacity sums
    type_capacities: Dict[str, float] = {}
    for feature in assets_fc.get("features", []):
        props = feature.get("properties", {})
        atype = props.get("type")
        cap = float(props.get("capacity_kw", 0.0))
        if atype:
            type_capacities[atype] = type_capacities.get(atype, 0.0) + cap

    updated_features = []
    for feature in assets_fc.get("features", []):
        f = copy.deepcopy(feature)
        props = f.get("properties", {})
        atype = props.get("type")
        cap = float(props.get("capacity_kw", 0.0))
        tot_cap = type_capacities.get(atype, 0.0)

        # Calculate proportional share
        ratio = (cap / tot_cap) if tot_cap > 0 else 0.0

        forecast_output = 0.0
        status = "idle"

        if atype == "solar":
            forecast_output = round(solar_total * ratio, 2)
            status = "active" if forecast_output > 0 else "idle"

        elif atype == "wind":
            forecast_output = round(wind_total * ratio, 2)
            status = "active" if forecast_output > 0 else "idle"

        elif atype == "hydro":
            forecast_output = round(hydro_total * ratio, 2)
            status = "active" if forecast_output > 0 else "idle"

        elif atype == "grid":
            forecast_output = round(grid_total * ratio, 2)
            status = "active" if forecast_output > 0 else "not_supplying"

        elif atype == "battery":
            # Battery convention: >0 discharging, <0 charging, =0 idle
            # Never produce negative output: store magnitude in forecast_output_kw
            forecast_output = round(abs(battery_val) * ratio, 2)
            if battery_val > 0:
                status = "discharging"
            elif battery_val < 0:
                status = "charging"
            else:
                status = "idle"

            if battery_soc is not None:
                props["battery_soc_kwh"] = round(float(battery_soc), 1)

        elif atype == "demand":
            forecast_output = round(load_total * ratio, 2)
            status = "active"

        # Calculate utilization percentage
        if cap > 0:
            utilization = round((forecast_output / cap) * 100.0, 1)
        else:
            utilization = 0.0

        # Safety: never negative
        forecast_output = max(0.0, forecast_output)

        props["forecast_output_kw"] = forecast_output
        props["status"] = status
        props["scenario"] = effective_scenario
        props["utilization_percent"] = utilization

        f["properties"] = props
        updated_features.append(f)

    assets_fc["features"] = updated_features
    return assets_fc


def build_energy_flow(
    dispatch_row: Dict[str, Any],
    assets_geojson: Union[str, Path, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Builds LineString GeoJSON features representing dynamic energy flow lines
    from supply sources into the demand hub (or into battery if charging).
    flow_kw determines visual line thickness, while direction indicates power transfer.
    """
    # First, apply dispatch to assets to obtain proportional output per asset
    applied_assets = apply_dispatch(assets_geojson, dispatch_row)

    demand_hub = None
    supply_assets = []

    for f in applied_assets.get("features", []):
        props = f.get("properties", {})
        if props.get("type") == "demand":
            demand_hub = f
        else:
            supply_assets.append(f)

    if not demand_hub:
        raise ValueError("Cannot build energy flow: missing demand hub asset in GeoJSON.")

    hub_coords = demand_hub["geometry"]["coordinates"]
    flow_features = []

    for src in supply_assets:
        props = src.get("properties", {})
        src_id = props.get("id")
        src_type = props.get("type")
        src_name = props.get("name")
        src_coords = src["geometry"]["coordinates"]
        output_kw = float(props.get("forecast_output_kw", 0.0))
        status = props.get("status", "idle")

        direction = "to_demand"
        line_coords = [src_coords, hub_coords]

        if src_type == "battery":
            if status == "charging":
                # Energy flows from grid/generation hub into battery
                direction = "to_battery"
                line_coords = [hub_coords, src_coords]
            elif status == "idle":
                output_kw = 0.0

        elif src_type == "grid":
            if status == "not_supplying":
                output_kw = 0.0

        flow_active = output_kw > 0

        feature = {
            "type": "Feature",
            "properties": {
                "id": f"flow_{src_id}_to_demand",
                "source_id": src_id,
                "source_type": src_type,
                "source_name": src_name,
                "target_id": demand_hub["properties"]["id"],
                "flow_kw": round(output_kw, 2),
                "status": "active" if flow_active else "idle",
                "direction": direction,
                "line_weight": max(1.5, min(8.0, 1.5 + (output_kw / 100.0))),
                "is_synthetic": True,
                "note": "Simulated dynamic energy flow"
            },
            "geometry": {
                "type": "LineString",
                "coordinates": line_coords
            }
        }
        flow_features.append(feature)

    return {
        "type": "FeatureCollection",
        "name": "GridMate_Dynamic_Energy_Flow",
        "features": flow_features
    }

