"""
run_scenarios.py — Scenario testing harness for GridMate.

Runs all five required scenarios against the sample forecast, validates
each result and prints a summary report.

Usage (from optimization/):
    python src/run_scenarios.py
"""

import json
import sys
from pathlib import Path

# Allow importing sibling modules without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimizer import optimize_dispatch, load_config
from utils import load_json, save_json, scale_forecast, print_metrics_table


# -------------------------------------------------
# Scenario definitions
# Five weather / demand scenarios for Lonavala.
# Each entry is a set of multipliers applied to the base forecast.
# -------------------------------------------------

SCENARIOS = {
    "normal": {
        "solar": 1.0,
        "wind":  1.0,
        "hydro": 1.0,
        "load":  1.0,
    },
    "cloudy": {
        "solar": 0.3,
        "wind":  0.85,
        "hydro": 1.0,
        "load":  1.0,
    },
    "heavy_monsoon": {
        "solar": 0.2,
        "wind":  1.1,
        "hydro": 1.2,
        "load":  1.05,
    },
    "high_wind": {
        "solar": 1.0,
        "wind":  1.6,
        "hydro": 1.0,
        "load":  1.0,
    },
    "peak_demand": {
        "solar": 1.0,
        "wind":  1.0,
        "hydro": 1.0,
        "load":  1.3,
    },
}


# -------------------------------------------------
# Validation
# -------------------------------------------------

def validate_dispatch(forecast: dict, result: dict, config: dict):
    """Validate dispatch result against physical constraints.

    Returns
    -------
    checks : dict[str, bool]
        Per-check pass/fail flags.
    errors : list[str]
        Human-readable descriptions of any failures.
    """
    bat_cfg  = config["battery"]
    grid_cfg = config["grid"]

    checks = {
        "Power balance":        True,
        "Battery SOC limits":   True,
        "Renewable availability": True,
        "Grid capacity":        True,
        "Battery power limits": True,
    }
    errors = []
    tol = 0.5  # kW tolerance for floating-point comparisons

    forecast_hours = forecast["forecast"]
    output_hours   = result["dispatch"]

    for i, (fh, oh) in enumerate(zip(forecast_hours, output_hours)):
        solar      = oh["solar_kw"]
        wind       = oh["wind_kw"]
        hydro      = oh["hydro_kw"]
        battery_kw = oh["battery_kw"]
        grid_kw    = oh["grid_kw"]
        load_kw    = oh["load_kw"]
        soc        = oh["battery_soc_kwh"]

        # 1. Power balance: generation + battery_discharge + grid = load
        total_supply = solar + wind + hydro + grid_kw + battery_kw
        if abs(total_supply - load_kw) > tol:
            checks["Power balance"] = False
            errors.append(
                f"Hour {i+1}: power balance mismatch "
                f"(supply={total_supply:.2f}, load={load_kw:.2f})"
            )

        # 2. Battery SOC within configured limits
        if (
            soc < bat_cfg["min_soc_kwh"] - tol
            or soc > bat_cfg["max_soc_kwh"] + tol
        ):
            checks["Battery SOC limits"] = False
            errors.append(f"Hour {i+1}: battery SOC {soc:.2f} outside limits.")

        # 3. No source dispatched above its forecast/available power
        if solar > fh["solar_kw"] + tol:
            checks["Renewable availability"] = False
            errors.append(f"Hour {i+1}: solar dispatch exceeds forecast.")
        if wind > fh["wind_kw"] + tol:
            checks["Renewable availability"] = False
            errors.append(f"Hour {i+1}: wind dispatch exceeds forecast.")
        if hydro > fh["hydro_kw"] + tol:
            checks["Renewable availability"] = False
            errors.append(f"Hour {i+1}: hydro dispatch exceeds forecast.")

        # 4. Grid import within capacity and non-negative
        if grid_kw < -tol or grid_kw > grid_cfg["capacity_kw"] + tol:
            checks["Grid capacity"] = False
            errors.append(f"Hour {i+1}: grid dispatch {grid_kw:.2f} kW out of range.")

        # 5. Battery power within charge/discharge limits
        if (
            battery_kw < -bat_cfg["max_charge_kw"] - tol
            or battery_kw > bat_cfg["max_discharge_kw"] + tol
        ):
            checks["Battery power limits"] = False
            errors.append(f"Hour {i+1}: battery power {battery_kw:.2f} kW out of range.")

    return checks, errors


# -------------------------------------------------
# Main runner
# -------------------------------------------------

def run_all_scenarios():
    base_dir   = Path(__file__).resolve().parent.parent
    data_file  = base_dir / "data"    / "sample_forecast.json"
    output_dir = base_dir / "outputs" / "scenarios"
    output_dir.mkdir(parents=True, exist_ok=True)

    base_forecast = load_json(data_file)
    config        = load_config()

    summary = []

    print("\n========== GRIDMATE SCENARIO TESTING ==========\n")

    for name, factors in SCENARIOS.items():
        print(f"\n--- Scenario: {name} ---")

        scenario_forecast = scale_forecast(base_forecast, factors)
        result            = optimize_dispatch(scenario_forecast)
        checks, errors    = validate_dispatch(scenario_forecast, result, config)

        result["scenario"]           = name
        result["validation"]         = checks
        result["validation_errors"]  = errors

        save_json(result, output_dir / f"{name}.json")

        print("\nValidation:")
        for check_name, passed in checks.items():
            print(f"  {'PASS' if passed else 'FAIL'}  {check_name}")

        if not all(checks.values()):
            print("\nErrors:")
            for err in errors:
                print(f"  {err}")

        metrics = result["metrics"]
        summary.append({
            "scenario":    name,
            "renewable":   metrics["renewable_penetration_percent"],
            "grid":        metrics["grid_dependency_percent"],
            "curtailment": metrics["curtailment_percent"],
            "battery":     metrics["battery_utilization_percent"],
            "co2_avoided": metrics["estimated_co2_avoided_kg"],
            "validation":  "PASS" if all(checks.values()) else "FAIL",
        })

    # Final comparison table
    print("\n========== FINAL SCENARIO REPORT ==========\n")
    header = (
        f"{'Scenario':<18}"
        f"{'Renew %':<12}"
        f"{'Grid %':<10}"
        f"{'Curtail %':<12}"
        f"{'Battery %':<12}"
        f"{'CO2 Avoided (kg)':<20}"
        f"{'Validation'}"
    )
    print(header)
    print("-" * len(header))
    for row in summary:
        print(
            f"{row['scenario']:<18}"
            f"{row['renewable']:<12.2f}"
            f"{row['grid']:<10.2f}"
            f"{row['curtailment']:<12.2f}"
            f"{row['battery']:<12.2f}"
            f"{row['co2_avoided']:<20.2f}"
            f"{row['validation']}"
        )

    print(f"\nScenario outputs saved in: {output_dir}")
    print("All scenario tests completed!")


if __name__ == "__main__":
    run_all_scenarios()
