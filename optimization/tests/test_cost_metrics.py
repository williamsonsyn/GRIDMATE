"""
tests/test_cost_metrics.py — Tests for cost and savings metrics.

Covers:
1. Tiny 3-hour hand-calculated case where every number is checkable
2. Baseline equals load * price when prices are flat
3. Savings_rs is never negative for the sample forecast
4. Savings_percent is 0.0 when load is zero (no division error)
5. The required contract fields in dispatch.json are unchanged
6. summary.csv has five scenario rows and the expected columns
7. peak_demand has a higher total_grid_cost_rs than normal
"""

import csv
import json
import sys
import pytest
import pandas as pd
from pathlib import Path

# Allow importing src modules
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR / "src"))

from metrics import calculate_cost_metrics
from optimizer import optimize_dispatch
from run_scenarios import run_all_scenarios


# ---------------------------------------------------------------------------
# 1. Tiny 3-hour hand-calculated test case
# ---------------------------------------------------------------------------

def test_hand_calculated_3hour_case():
    """
    Hour 1: load = 100 kW, grid = 20 kW, price = 10.0 Rs/kWh
    Hour 2: load = 200 kW, grid = 50 kW, price = 8.0 Rs/kWh
    Hour 3: load = 300 kW, grid = 100 kW, price = 12.0 Rs/kWh

    Calculations (1-hour timestep, kW = kWh):
    - total_grid_cost_rs = 20*10 + 50*8 + 100*12 = 200 + 400 + 1200 = 1800.00
    - grid_only_cost_rs  = 100*10 + 200*8 + 300*12 = 1000 + 1600 + 3600 = 6200.00
    - savings_rs         = 6200.00 - 1800.00 = 4400.00
    - savings_percent    = (4400.00 / 6200.00) * 100 = 70.9677... -> 71.0
    - total_load_kwh     = 100 + 200 + 300 = 600.0
    - average_cost_rs_per_kwh_served   = 1800.00 / 600.0 = 3.00
    - grid_only_average_cost_rs_per_kwh = 6200.00 / 600.0 = 10.3333... -> 10.33
    """
    dispatch_rows = [
        {"load_kw": 100.0, "grid_kw": 20.0},
        {"load_kw": 200.0, "grid_kw": 50.0},
        {"load_kw": 300.0, "grid_kw": 100.0},
    ]
    prices = [10.0, 8.0, 12.0]

    result = calculate_cost_metrics(dispatch_rows, prices)

    assert result["total_grid_cost_rs"] == 1800.00
    assert result["grid_only_cost_rs"] == 6200.00
    assert result["savings_rs"] == 4400.00
    assert result["savings_percent"] == 71.0
    assert result["average_cost_rs_per_kwh_served"] == 3.00
    assert result["grid_only_average_cost_rs_per_kwh"] == 10.33
    assert result["label"] == (
        "Cost figures are prototype estimates based on assumed tariffs, "
        "not billing-grade values."
    )


# ---------------------------------------------------------------------------
# 2. Baseline equals load * price when prices are flat
# ---------------------------------------------------------------------------

def test_baseline_equals_load_times_price_flat():
    dispatch_rows = [
        {"load_kw": 150.0, "grid_kw": 50.0},
        {"load_kw": 250.0, "grid_kw": 70.0},
        {"load_kw": 400.0, "grid_kw": 120.0},
    ]
    flat_price = 8.5
    prices = [flat_price, flat_price, flat_price]

    total_load = 150.0 + 250.0 + 400.0  # 800.0 kWh
    expected_baseline = total_load * flat_price  # 6800.00 Rs

    result = calculate_cost_metrics(dispatch_rows, prices)
    assert abs(result["grid_only_cost_rs"] - expected_baseline) < 0.01
    assert abs(result["grid_only_average_cost_rs_per_kwh"] - flat_price) < 0.01


# ---------------------------------------------------------------------------
# 3. Savings_rs is never negative for the sample forecast
# ---------------------------------------------------------------------------

def test_savings_rs_never_negative_sample_forecast(tmp_path):
    sample_file = BASE_DIR / "data" / "sample_forecast.json"
    out_file = tmp_path / "dispatch.json"

    result = optimize_dispatch(sample_file, output_path=out_file)
    assert "extra_metrics" in result
    savings = result["extra_metrics"]["savings_rs"]
    assert savings >= 0.0, f"Expected non-negative savings, got {savings}"


# ---------------------------------------------------------------------------
# 4. Savings_percent is 0.0 when load is zero (no division error)
# ---------------------------------------------------------------------------

def test_savings_percent_zero_when_load_zero():
    dispatch_rows = [
        {"load_kw": 0.0, "grid_kw": 0.0},
        {"load_kw": 0.0, "grid_kw": 0.0},
    ]
    prices = [8.0, 9.6]

    result = calculate_cost_metrics(dispatch_rows, prices)
    assert result["total_grid_cost_rs"] == 0.0
    assert result["grid_only_cost_rs"] == 0.0
    assert result["savings_rs"] == 0.0
    assert result["savings_percent"] == 0.0
    assert result["average_cost_rs_per_kwh_served"] == 0.0
    assert result["grid_only_average_cost_rs_per_kwh"] == 0.0


# ---------------------------------------------------------------------------
# 5. Required contract fields in dispatch.json are unchanged
# ---------------------------------------------------------------------------

def test_required_contract_fields_unchanged(tmp_path):
    sample_file = BASE_DIR / "data" / "sample_forecast.json"
    out_file = tmp_path / "dispatch.json"

    result = optimize_dispatch(sample_file, output_path=out_file)

    # 1. Top-level contract
    assert "location" in result
    assert "dispatch" in result
    assert "metrics" in result
    assert "extra_metrics" in result

    # 2. Required dispatch row keys must remain exactly as originally specified
    expected_row_keys = {
        "timestamp", "solar_kw", "wind_kw", "hydro_kw",
        "battery_kw", "grid_kw", "load_kw",
        "curtailment_kw", "battery_soc_kwh",
    }
    for row in result["dispatch"]:
        assert set(row.keys()) == expected_row_keys

    # 3. Required metrics keys must remain exactly the 5 fields
    expected_metrics_keys = {
        "renewable_penetration_percent",
        "grid_dependency_percent",
        "curtailment_percent",
        "battery_utilization_percent",
        "estimated_co2_avoided_kg",
    }
    assert set(result["metrics"].keys()) == expected_metrics_keys

    # 4. Cost metrics are strictly in extra_metrics
    em = result["extra_metrics"]
    for k in (
        "total_grid_cost_rs", "grid_only_cost_rs", "savings_rs",
        "savings_percent", "average_cost_rs_per_kwh_served",
        "grid_only_average_cost_rs_per_kwh", "label"
    ):
        assert k in em


# ---------------------------------------------------------------------------
# 6. summary.csv has five scenario rows and the expected columns
# ---------------------------------------------------------------------------

def test_summary_csv_has_five_rows_and_expected_columns():
    run_all_scenarios()
    csv_file = BASE_DIR / "outputs" / "scenarios" / "summary.csv"
    assert csv_file.exists(), f"Missing {csv_file}"

    expected_columns = [
        "scenario",
        "renewable_penetration_percent",
        "grid_dependency_percent",
        "curtailment_percent",
        "battery_utilization_percent",
        "estimated_co2_avoided_kg",
        "total_grid_cost_rs",
        "grid_only_cost_rs",
        "savings_rs",
        "savings_percent",
    ]

    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == expected_columns, (
            f"Columns mismatch: expected {expected_columns}, got {reader.fieldnames}"
        )
        rows = list(reader)
        assert len(rows) == 5, f"Expected 5 scenario rows, got {len(rows)}"
        scenario_names = [r["scenario"] for r in rows]
        assert set(scenario_names) == {
            "normal", "cloudy", "heavy_monsoon", "high_wind", "peak_demand"
        }


# ---------------------------------------------------------------------------
# 7. peak_demand has a higher total_grid_cost_rs than normal
# ---------------------------------------------------------------------------

def test_peak_demand_higher_cost_than_normal():
    scenarios_dir = BASE_DIR / "outputs" / "scenarios"
    normal_file = scenarios_dir / "normal.json"
    peak_file = scenarios_dir / "peak_demand.json"

    with open(normal_file, "r") as f:
        normal = json.load(f)
    with open(peak_file, "r") as f:
        peak = json.load(f)

    normal_cost = normal["extra_metrics"]["total_grid_cost_rs"]
    peak_cost = peak["extra_metrics"]["total_grid_cost_rs"]

    assert peak_cost > normal_cost, (
        f"Expected peak_demand grid cost ({peak_cost}) > normal grid cost ({normal_cost})"
    )
