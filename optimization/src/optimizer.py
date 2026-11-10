"""
optimizer.py — Energy Optimization and Smart Dispatch engine for GridMate.

PyPSA-based linear programming optimizer using HiGHS solver to determine the
hourly dispatch of Solar, Wind, Hydro, Battery, and Grid.
"""

import argparse
import json
import logging
import warnings
from pathlib import Path
from typing import Union

import pandas as pd
import pypsa

# Suppress PyPSA / linopy FutureWarnings that are version-upgrade noise.
warnings.filterwarnings("ignore", category=FutureWarning, module="pypsa")
warnings.filterwarnings("ignore", category=FutureWarning, module="linopy")

# Keep solver INFO logs quiet during normal use; raise to logging.INFO for debug.
logging.getLogger("linopy").setLevel(logging.WARNING)
logging.getLogger("pypsa").setLevel(logging.WARNING)
logging.getLogger("pypsa.consistency").setLevel(logging.ERROR)

try:
    from .network import build_network
    from .battery import validate_battery_config, normalize_battery_config
    from .metrics import calculate_metrics, calculate_cost_metrics
    from .utils import load_json, save_json, build_grid_price_series
except ImportError:
    from network import build_network
    from battery import validate_battery_config, normalize_battery_config
    from metrics import calculate_metrics, calculate_cost_metrics
    from utils import load_json, save_json, build_grid_price_series


# -------------------------------------------------
# 1. PROJECT PATHS
# -------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[1]

DATA_FILE          = BASE_DIR / "data"    / "sample_forecast.json"
CONFIG_FILE        = BASE_DIR / "config"  / "system_config.json"
OUTPUT_FILE        = BASE_DIR / "outputs" / "dispatch.json"
MEMBER1_FORECAST   = BASE_DIR.parent / "forecasting" / "outputs" / "forecast.json"


# -------------------------------------------------
# 2. DEFAULT SYSTEM SETTINGS
# -------------------------------------------------

DEFAULT_CONFIG = {
    "battery": {
        "capacity_kwh":            500,
        "max_charge_kw":           100,
        "max_discharge_kw":        100,
        "initial_soc_kwh":         200,
        "min_soc_kwh":              50,
        "max_soc_kwh":             500,
        "charge_efficiency":       0.95,
        "discharge_efficiency":    0.95,
        # Full spec aliases
        "energy_capacity_kwh":     500,
        "maximum_charge_kw":       100,
        "maximum_discharge_kw":    100,
        "initial_state_of_charge": 200,
        "minimum_state_of_charge":  50,
        "maximum_state_of_charge": 500,
    },
    "grid": {
        "capacity_kw":          1000,
        "cost_per_kwh":            8,
        "emission_factor":         0.7,
        # Full spec aliases
        "grid_capacity_kw":     1000,
        "grid_cost_per_kwh":       8,
        "grid_emission_factor":    0.7,
    },
}


# -------------------------------------------------
# 3. LOAD CONFIGURATION
# -------------------------------------------------

def load_config() -> dict:
    """Load system_config.json and merge with defaults.

    Supports both full spec parameter names (e.g. energy_capacity_kwh)
    and shorthand names (e.g. capacity_kwh).
    """
    if not CONFIG_FILE.exists():
        cfg = {
            "battery": dict(DEFAULT_CONFIG["battery"]),
            "grid":    dict(DEFAULT_CONFIG["grid"]),
        }
    else:
        with open(CONFIG_FILE, "r") as fh:
            user_cfg = json.load(fh)

        cfg = {
            "battery": dict(DEFAULT_CONFIG["battery"]),
            "grid":    dict(DEFAULT_CONFIG["grid"]),
        }

        for section in ("battery", "grid"):
            if section in user_cfg:
                cfg[section].update(user_cfg[section])

    # Normalize battery parameters
    cfg["battery"] = normalize_battery_config(cfg["battery"])

    # Normalize grid parameters
    g = cfg["grid"]
    grid_cap = g.get("capacity_kw") or g.get("grid_capacity_kw", 1000)
    # Resolve base price — support several legacy key names
    grid_cost = (
        g.get("base_energy_charge_rs_per_kwh")
        or g.get("cost_per_kwh")
        or g.get("grid_cost_per_kwh")
        or 8
    )
    grid_emiss = g.get("emission_factor") if "emission_factor" in g else g.get("grid_emission_factor", 0.7)

    cfg["grid"] = {
        "capacity_kw": grid_cap,
        "cost_per_kwh": grid_cost,              # backward-compat alias
        "emission_factor": grid_emiss,
        "base_energy_charge_rs_per_kwh": grid_cost,
        "tod": g.get("tod"),                    # None when "tod" key is absent
        # Full-spec aliases kept for downstream callers
        "grid_capacity_kw": grid_cap,
        "grid_cost_per_kwh": grid_cost,
        "grid_emission_factor": grid_emiss,
    }

    return cfg


# -------------------------------------------------
# 4. OPTIMIZATION FUNCTION
# -------------------------------------------------

def optimize_dispatch(
    forecast_input: Union[dict, str, Path],
    output_path: Union[str, Path, None] = None,
    config_override: Union[dict, None] = None,
) -> dict:
    """Run the PyPSA / HiGHS dispatch optimisation.

    Parameters
    ----------
    forecast_input : dict, str, or Path
        Either a dictionary following the forecast contract, or a file path
        (str / Path) pointing to a forecast JSON file.
    output_path : str or Path, optional
        Destination path for dispatch.json. Defaults to outputs/dispatch.json.

    Returns
    -------
    dict
        Dispatch results following the output contract.
        Also written to output_path.
    """
    # Accept dict or file path directly
    if isinstance(forecast_input, (str, Path)):
        p = Path(forecast_input)
        if not p.exists():
            raise FileNotFoundError(f"Forecast file not found: {p}")
        forecast_data = load_json(p)
    elif isinstance(forecast_input, dict):
        forecast_data = forecast_input
    else:
        raise TypeError(
            f"forecast_input must be a dict or file path, got {type(forecast_input).__name__}"
        )

    out_file = Path(output_path) if output_path else OUTPUT_FILE

    cfg     = load_config()
    if config_override:
        if "battery" in config_override:
            cfg["battery"].update(config_override["battery"])
        if "grid" in config_override:
            cfg["grid"].update(config_override["grid"])
    battery = cfg["battery"]
    grid    = cfg["grid"]

    # Validate battery configuration
    validate_battery_config(battery)

    # ------------------------------------------------------------------
    # 4a. Parse and validate forecast
    # ------------------------------------------------------------------

    rows = forecast_data.get("forecast")
    if not rows:
        raise ValueError(
            "forecast_data must contain a non-empty 'forecast' list."
        )

    df = pd.DataFrame(rows)

    required = ["timestamp", "solar_kw", "wind_kw", "hydro_kw", "load_kw"]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing forecast columns: {missing}")

    if df.empty:
        raise ValueError("Forecast data is empty.")

    energy_cols = ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]
    for col in energy_cols:
        df[col] = pd.to_numeric(df[col], errors="raise")
        if (df[col] < 0).any():
            raise ValueError(f"{col} cannot contain negative values.")

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")

    # Convert kW → MW (PyPSA native unit)
    for col in energy_cols:
        df[col] = df[col] / 1000.0

    # ------------------------------------------------------------------
    # 4b. Build PyPSA network
    # ------------------------------------------------------------------

    # Build hourly grid price series (Rs/kWh) using ToD tariff if configured.
    # Falls back to flat price when "tod" is absent (backward-compatible).
    price_series = build_grid_price_series(df.index, grid)

    net = build_network(df, battery, grid, price_series_rs_per_kwh=price_series)

    # ------------------------------------------------------------------
    # 4c. Solve with HiGHS
    # ------------------------------------------------------------------

    print("\nStarting GridMate optimisation...")

    status, condition = net.optimize(
        solver_name="highs",
        include_objective_constant=False,
    )

    print("Optimisation status   :", status)
    print("Termination condition :", condition)

    if status != "ok" or condition != "optimal":
        raise RuntimeError(
            "Optimisation failed. "
            "Check forecast values, battery settings and grid capacity."
        )

    # ------------------------------------------------------------------
    # 4d. Extract results (convert MW → kW for output)
    # ------------------------------------------------------------------

    gen = net.generators_t.p

    solar_out  = gen["solar"] * 1000.0
    wind_out   = gen["wind"]  * 1000.0
    hydro_out  = gen["hydro"] * 1000.0
    grid_out   = gen["Grid"]  * 1000.0

    bat_out    = net.storage_units_t.p["Battery"]   * 1000.0
    # Clip SOC to [min_soc, max_soc] to remove LP numerical noise.
    # The solver may return values like -0.00 or marginally out-of-range values
    # (e.g. 49.99 when min=50) that are physically on the boundary — clipping
    # these is safe and keeps the validation clean.
    bat_soc    = (
        net.storage_units_t.state_of_charge["Battery"] * 1000.0
    ).clip(
        lower=float(battery["min_soc_kwh"]),
        upper=float(battery["max_soc_kwh"]),
    )

    # ------------------------------------------------------------------
    # 4e. Curtailment = available renewable - dispatched renewable
    #     (clipped to 0 to remove LP numerical noise)
    # ------------------------------------------------------------------

    solar_avail = df["solar_kw"] * 1000.0
    wind_avail  = df["wind_kw"]  * 1000.0
    hydro_avail = df["hydro_kw"] * 1000.0
    total_avail = solar_avail + wind_avail + hydro_avail

    total_renewable_used = solar_out + wind_out + hydro_out
    curtailment = (total_avail - total_renewable_used).clip(lower=0)

    # ------------------------------------------------------------------
    # 4f. Build hourly dispatch list
    # ------------------------------------------------------------------

    dispatch = []
    for ts in df.index:
        dispatch.append({
            "timestamp":        ts.isoformat(),
            "solar_kw":         round(float(solar_out.loc[ts]),  2),
            "wind_kw":          round(float(wind_out.loc[ts]),   2),
            "hydro_kw":         round(float(hydro_out.loc[ts]),  2),
            "battery_kw":       round(float(bat_out.loc[ts]),    2),
            "grid_kw":          round(float(grid_out.loc[ts]),   2),
            "load_kw":          round(float(df.loc[ts, "load_kw"] * 1000.0), 2),
            "curtailment_kw":   round(float(curtailment.loc[ts]), 2),
            "battery_soc_kwh":  round(float(bat_soc.loc[ts]),    2),
        })

    # ------------------------------------------------------------------
    # 4g. Calculate performance metrics via metrics module
    # ------------------------------------------------------------------

    total_load_kwh          = float((df["load_kw"] * 1000.0).sum())
    total_grid_kwh          = float(grid_out.sum())
    total_avail_energy_kwh  = float(total_avail.sum())
    total_curtailed_kwh     = float(curtailment.sum())
    bat_charging_kwh        = float((-bat_out).clip(lower=0).sum())
    bat_discharging_kwh     = float(bat_out.clip(lower=0).sum())

    metrics = calculate_metrics(
        total_load_kwh=total_load_kwh,
        total_grid_kwh=total_grid_kwh,
        total_avail_kwh=total_avail_energy_kwh,
        total_curtailed_kwh=total_curtailed_kwh,
        bat_charging_kwh=bat_charging_kwh,
        bat_discharging_kwh=bat_discharging_kwh,
        bat_capacity_kwh=battery["capacity_kwh"],
        n_hours=len(df),
        emission_factor=grid["emission_factor"],
    )

    # ------------------------------------------------------------------
    # 4h. Compute cost metrics (extra_metrics / extra_hourly)
    #     These go in a separate top-level block so the required "metrics"
    #     block stays exactly as specified in the output contract.
    # ------------------------------------------------------------------

    extra_metrics = calculate_cost_metrics(
        dispatch_rows=dispatch,
        prices=price_series,
    )

    extra_hourly = [
        {
            "timestamp": ts.isoformat(),
            "grid_price_rs_per_kwh": round(float(price_series.loc[ts]), 4),
        }
        for ts in df.index
    ]

    # ------------------------------------------------------------------
    # 4i. Assemble result
    # ------------------------------------------------------------------

    result = {
        "location": forecast_data.get("location", "Unknown"),
        "dispatch": dispatch,
        "metrics":  metrics,
        "extra_metrics": extra_metrics,
        "extra_hourly":  extra_hourly,
    }

    # ------------------------------------------------------------------
    # 4i. Write dispatch.json
    # ------------------------------------------------------------------

    save_json(result, out_file)

    print("\nDispatch successfully generated!")
    print("Output saved at:", out_file)
    print("\nPerformance Metrics:")
    for name, value in metrics.items():
        print(f"  {name}: {value}")

    return result


# -------------------------------------------------
# 5. MAIN ENTRY POINT & CLI
# -------------------------------------------------

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="GridMate Energy Optimization & Smart Dispatch Engine"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=None,
        help="Path to forecast JSON file. Defaults to sample forecast or Member 1 forecast."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path to write dispatch JSON output (default: outputs/dispatch.json)"
    )
    parser.add_argument(
        "-f", "--forecasting",
        action="store_true",
        help="Take input directly from Member 1's forecasting/outputs/forecast.json"
    )

    args = parser.parse_args()

    # Determine which forecast to load
    if args.input:
        target_input = Path(args.input)
    elif args.forecasting:
        target_input = MEMBER1_FORECAST
    elif DATA_FILE.exists():
        target_input = DATA_FILE
    elif MEMBER1_FORECAST.exists():
        target_input = MEMBER1_FORECAST
    else:
        raise FileNotFoundError("No forecast file found. Provide path via --input.")

    print(f"Reading forecast from: {target_input}")
    optimize_dispatch(target_input, output_path=args.output)
