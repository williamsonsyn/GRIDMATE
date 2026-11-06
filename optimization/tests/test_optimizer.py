"""
tests/test_optimizer.py — Unit and integration tests for GridMate optimizer.

Run from the optimization/ directory:
    python -m pytest tests/ -v
"""

import json
import sys
import pytest
from pathlib import Path

# Allow importing src modules without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from optimizer import optimize_dispatch, load_config
from battery import validate_battery_config, battery_summary
from metrics import calculate_metrics
from utils import scale_forecast, load_json, save_json


# -------------------------------------------------
# Fixtures
# -------------------------------------------------

MINIMAL_FORECAST = {
    "location": "Lonavala",
    "forecast_horizon_hours": 3,
    "forecast": [
        {
            "timestamp": "2026-10-01T10:00:00",
            "solar_kw": 350.0,
            "wind_kw":  180.0,
            "hydro_kw": 200.0,
            "load_kw":  700.0,
        },
        {
            "timestamp": "2026-10-01T11:00:00",
            "solar_kw": 420.0,
            "wind_kw":  170.0,
            "hydro_kw": 200.0,
            "load_kw":  750.0,
        },
        {
            "timestamp": "2026-10-01T12:00:00",
            "solar_kw": 450.0,
            "wind_kw":  190.0,
            "hydro_kw": 200.0,
            "load_kw":  900.0,
        },
    ],
}

TOL = 0.5  # kW tolerance for floating-point comparisons


# -------------------------------------------------
# 1. Output contract tests
# -------------------------------------------------

class TestOutputContract:
    """The dispatch.json must follow the agreed output contract exactly."""

    def setup_method(self):
        self.result = optimize_dispatch(MINIMAL_FORECAST)

    def test_top_level_keys(self):
        assert "location"  in self.result
        assert "dispatch"  in self.result
        assert "metrics"   in self.result

    def test_location_preserved(self):
        assert self.result["location"] == "Lonavala"

    def test_dispatch_length_matches_forecast(self):
        assert len(self.result["dispatch"]) == len(MINIMAL_FORECAST["forecast"])

    def test_dispatch_row_keys(self):
        required = {
            "timestamp", "solar_kw", "wind_kw", "hydro_kw",
            "battery_kw", "grid_kw", "load_kw",
            "curtailment_kw", "battery_soc_kwh",
        }
        for row in self.result["dispatch"]:
            assert required.issubset(row.keys()), (
                f"Missing keys: {required - row.keys()}"
            )

    def test_metrics_keys(self):
        required = {
            "renewable_penetration_percent",
            "grid_dependency_percent",
            "curtailment_percent",
            "battery_utilization_percent",
            "estimated_co2_avoided_kg",
        }
        assert required.issubset(self.result["metrics"].keys())


# -------------------------------------------------
# 2. Physical constraints tests
# -------------------------------------------------

class TestPhysicalConstraints:
    """Dispatch must respect physical constraints at every timestep."""

    def setup_method(self):
        self.result = optimize_dispatch(MINIMAL_FORECAST)
        self.config = load_config()

    def test_power_balance(self):
        """generation + battery_discharge + grid == load (within tolerance)."""
        for row in self.result["dispatch"]:
            supply = (
                row["solar_kw"]
                + row["wind_kw"]
                + row["hydro_kw"]
                + row["battery_kw"]
                + row["grid_kw"]
            )
            assert abs(supply - row["load_kw"]) < TOL, (
                f"Power balance failed at {row['timestamp']}: "
                f"supply={supply:.2f}, load={row['load_kw']:.2f}"
            )

    def test_battery_soc_within_limits(self):
        bat = self.config["battery"]
        for row in self.result["dispatch"]:
            soc = row["battery_soc_kwh"]
            assert soc >= bat["min_soc_kwh"] - TOL
            assert soc <= bat["max_soc_kwh"] + TOL

    def test_renewable_not_exceed_forecast(self):
        forecast_hours = MINIMAL_FORECAST["forecast"]
        for fh, oh in zip(forecast_hours, self.result["dispatch"]):
            assert oh["solar_kw"] <= fh["solar_kw"] + TOL
            assert oh["wind_kw"]  <= fh["wind_kw"]  + TOL
            assert oh["hydro_kw"] <= fh["hydro_kw"] + TOL

    def test_grid_non_negative(self):
        for row in self.result["dispatch"]:
            assert row["grid_kw"] >= -TOL

    def test_grid_within_capacity(self):
        cap = self.config["grid"]["capacity_kw"]
        for row in self.result["dispatch"]:
            assert row["grid_kw"] <= cap + TOL

    def test_battery_power_within_limits(self):
        bat = self.config["battery"]
        for row in self.result["dispatch"]:
            assert row["battery_kw"] >= -bat["max_charge_kw"] - TOL
            assert row["battery_kw"] <=  bat["max_discharge_kw"] + TOL

    def test_curtailment_non_negative(self):
        for row in self.result["dispatch"]:
            assert row["curtailment_kw"] >= -TOL


# -------------------------------------------------
# 3. Demand satisfaction test
# -------------------------------------------------

class TestDemandSatisfaction:
    def test_demand_satisfied_when_feasible(self):
        result = optimize_dispatch(MINIMAL_FORECAST)
        for fh, oh in zip(MINIMAL_FORECAST["forecast"], result["dispatch"]):
            assert abs(oh["load_kw"] - fh["load_kw"]) < TOL


# -------------------------------------------------
# 4. Battery behaviour tests
# -------------------------------------------------

class TestBatteryBehaviour:
    def test_battery_charges_when_generation_abundant(self):
        """Battery should charge when surplus is available and can be used later.

        Profile: hours 0-1 have abundant renewables + low load (surplus),
        hour 2 has zero renewable + high load (needs battery discharge).
        The cyclic SOC constraint is relaxed by using a 4-hour window so the
        battery can legitimately charge in hour 0 and discharge in hour 3.
        """
        charge_then_discharge = {
            "location": "Lonavala",
            "forecast_horizon_hours": 4,
            "forecast": [
                {   # surplus hour — battery should charge
                    "timestamp": "2026-10-01T10:00:00",
                    "solar_kw": 500.0,
                    "wind_kw":  200.0,
                    "hydro_kw": 250.0,
                    "load_kw":  300.0,
                },
                {   # still surplus
                    "timestamp": "2026-10-01T11:00:00",
                    "solar_kw": 500.0,
                    "wind_kw":  200.0,
                    "hydro_kw": 250.0,
                    "load_kw":  300.0,
                },
                {   # zero renewable, high load — battery should discharge
                    "timestamp": "2026-10-01T12:00:00",
                    "solar_kw": 0.0,
                    "wind_kw":  0.0,
                    "hydro_kw": 0.0,
                    "load_kw":  500.0,
                },
                {   # returns to surplus to satisfy cyclic SOC
                    "timestamp": "2026-10-01T13:00:00",
                    "solar_kw": 500.0,
                    "wind_kw":  200.0,
                    "hydro_kw": 250.0,
                    "load_kw":  300.0,
                },
            ],
        }
        result = optimize_dispatch(charge_then_discharge)
        # At least one hour the battery should be charging (negative = charging)
        any_charging = any(
            row["battery_kw"] < -TOL for row in result["dispatch"]
        )
        assert any_charging, "Battery should charge during renewable surplus."


# -------------------------------------------------
# 5. Scenario differentiation test
# -------------------------------------------------

class TestScenarioDifferentiation:
    """Changed forecast inputs should produce changed dispatch outputs."""

    def test_cloudy_uses_more_grid(self):
        normal = optimize_dispatch(MINIMAL_FORECAST)
        cloudy_forecast = scale_forecast(
            MINIMAL_FORECAST,
            {"solar": 0.1, "wind": 0.85, "hydro": 1.0, "load": 1.0}
        )
        cloudy = optimize_dispatch(cloudy_forecast)
        assert (
            cloudy["metrics"]["grid_dependency_percent"]
            > normal["metrics"]["grid_dependency_percent"]
        ), "Cloudy scenario should have higher grid dependency."

    def test_high_wind_has_lower_grid_dependency(self):
        normal = optimize_dispatch(MINIMAL_FORECAST)
        high_wind_forecast = scale_forecast(
            MINIMAL_FORECAST,
            {"solar": 1.0, "wind": 2.0, "hydro": 1.0, "load": 1.0}
        )
        high_wind = optimize_dispatch(high_wind_forecast)
        assert (
            high_wind["metrics"]["grid_dependency_percent"]
            <= normal["metrics"]["grid_dependency_percent"] + 1.0
        ), "High wind scenario should not increase grid dependency."


# -------------------------------------------------
# 6. Metrics module unit tests
# -------------------------------------------------

class TestMetricsModule:
    def test_renewable_penetration_100(self):
        m = calculate_metrics(
            total_load_kwh=1000,
            total_grid_kwh=0,
            total_avail_kwh=1200,
            total_curtailed_kwh=200,
            bat_charging_kwh=0,
            bat_discharging_kwh=0,
            bat_capacity_kwh=500,
            n_hours=24,
            emission_factor=0.7,
        )
        assert m["renewable_penetration_percent"] == 100.0
        assert m["grid_dependency_percent"] == 0.0

    def test_curtailment_percent(self):
        m = calculate_metrics(
            total_load_kwh=800,
            total_grid_kwh=0,
            total_avail_kwh=1000,
            total_curtailed_kwh=200,
            bat_charging_kwh=0,
            bat_discharging_kwh=0,
            bat_capacity_kwh=500,
            n_hours=24,
            emission_factor=0.7,
        )
        assert m["curtailment_percent"] == 20.0

    def test_co2_avoided_estimate(self):
        m = calculate_metrics(
            total_load_kwh=1000,
            total_grid_kwh=0,
            total_avail_kwh=1200,
            total_curtailed_kwh=0,
            bat_charging_kwh=50,
            bat_discharging_kwh=50,
            bat_capacity_kwh=500,
            n_hours=24,
            emission_factor=0.7,
        )
        assert abs(m["estimated_co2_avoided_kg"] - 700.0) < 0.01

    def test_zero_load_no_division_error(self):
        m = calculate_metrics(
            total_load_kwh=0,
            total_grid_kwh=0,
            total_avail_kwh=0,
            total_curtailed_kwh=0,
            bat_charging_kwh=0,
            bat_discharging_kwh=0,
            bat_capacity_kwh=500,
            n_hours=1,
            emission_factor=0.7,
        )
        assert m["renewable_penetration_percent"] == 0.0
        assert m["grid_dependency_percent"] == 0.0


# -------------------------------------------------
# 7. Battery module unit tests
# -------------------------------------------------

class TestBatteryModule:
    def test_valid_config_does_not_raise(self):
        cfg = {
            "capacity_kwh": 500,
            "max_charge_kw": 100,
            "max_discharge_kw": 100,
            "initial_soc_kwh": 200,
            "min_soc_kwh": 50,
            "max_soc_kwh": 500,
            "charge_efficiency": 0.95,
            "discharge_efficiency": 0.95,
        }
        validate_battery_config(cfg)  # should not raise

    def test_invalid_soc_order_raises(self):
        cfg = {
            "capacity_kwh": 500,
            "max_charge_kw": 100,
            "max_discharge_kw": 100,
            "initial_soc_kwh": 10,   # below min
            "min_soc_kwh": 50,
            "max_soc_kwh": 500,
            "charge_efficiency": 0.95,
            "discharge_efficiency": 0.95,
        }
        with pytest.raises(ValueError):
            validate_battery_config(cfg)

    def test_invalid_efficiency_raises(self):
        cfg = {
            "capacity_kwh": 500,
            "max_charge_kw": 100,
            "max_discharge_kw": 100,
            "initial_soc_kwh": 200,
            "min_soc_kwh": 50,
            "max_soc_kwh": 500,
            "charge_efficiency": 1.5,  # > 1
            "discharge_efficiency": 0.95,
        }
        with pytest.raises(ValueError):
            validate_battery_config(cfg)

    def test_summary_string(self):
        cfg = {
            "capacity_kwh": 500,
            "max_charge_kw": 100,
            "max_discharge_kw": 100,
            "initial_soc_kwh": 200,
            "min_soc_kwh": 50,
            "max_soc_kwh": 500,
            "charge_efficiency": 0.95,
            "discharge_efficiency": 0.95,
        }
        summary = battery_summary(cfg)
        assert "500" in summary
        assert "95%" in summary


# -------------------------------------------------
# 8. Utils module unit tests
# -------------------------------------------------

class TestUtils:
    def test_scale_forecast_solar(self):
        scaled = scale_forecast(MINIMAL_FORECAST, {"solar": 0.5})
        for orig, sc in zip(
            MINIMAL_FORECAST["forecast"], scaled["forecast"]
        ):
            assert abs(sc["solar_kw"] - orig["solar_kw"] * 0.5) < 1e-9

    def test_scale_forecast_load(self):
        scaled = scale_forecast(MINIMAL_FORECAST, {"load": 1.3})
        for orig, sc in zip(
            MINIMAL_FORECAST["forecast"], scaled["forecast"]
        ):
            assert abs(sc["load_kw"] - orig["load_kw"] * 1.3) < 1e-9

    def test_original_not_mutated(self):
        orig_solar = MINIMAL_FORECAST["forecast"][0]["solar_kw"]
        scale_forecast(MINIMAL_FORECAST, {"solar": 0.1})
        assert MINIMAL_FORECAST["forecast"][0]["solar_kw"] == orig_solar

    def test_save_and_load_json(self, tmp_path):
        data = {"key": "value", "number": 42}
        path = tmp_path / "test.json"
        save_json(data, path)
        loaded = load_json(path)
        assert loaded == data

    def test_load_json_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_json("/nonexistent/path/file.json")


# -------------------------------------------------
# 9. Input validation tests
# -------------------------------------------------

class TestInputValidation:
    def test_missing_forecast_key_raises(self):
        bad = {"location": "X", "forecast_horizon_hours": 1}
        with pytest.raises(ValueError, match="'forecast'"):
            optimize_dispatch(bad)

    def test_negative_solar_raises(self):
        bad = {
            "location": "Lonavala",
            "forecast_horizon_hours": 1,
            "forecast": [{
                "timestamp": "2026-10-01T10:00:00",
                "solar_kw": -10.0,
                "wind_kw":   100.0,
                "hydro_kw":  100.0,
                "load_kw":   200.0,
            }],
        }
        with pytest.raises(ValueError, match="negative"):
            optimize_dispatch(bad)
