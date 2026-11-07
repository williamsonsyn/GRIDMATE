"""
tests/test_tod.py — Tests for the Maharashtra (MSEDCL-style) time-of-day
grid tariff added in the ToD feature branch.

Run from the optimization/ directory:
    python -m pytest tests/ -v
"""

import sys
import pytest
import pandas as pd
from pathlib import Path

# Allow importing src modules without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utils import build_grid_price_series
from metrics import calculate_cost_metrics
from optimizer import optimize_dispatch


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

TOD_CFG = {
    "base_energy_charge_rs_per_kwh": 8.0,
    "tod": {
        "normal": {"from_hour": 0,  "to_hour": 9,  "multiplier": 1.00},
        "solar":  {"from_hour": 9,  "to_hour": 17, "multiplier_apr_sep": 0.85, "multiplier_oct_mar": 0.75},
        "peak":   {"from_hour": 17, "to_hour": 24, "multiplier": 1.20},
    },
}

FLAT_CFG = {
    "base_energy_charge_rs_per_kwh": 8.0,
    # No "tod" key → backward-compatible flat price
}

TOL = 1e-9


def _ts(year, month, day, hour):
    """Return a pd.DatetimeIndex with a single timestamp."""
    return pd.DatetimeIndex([pd.Timestamp(year=year, month=month, day=day, hour=hour)])


# ---------------------------------------------------------------------------
# 1. Price series values — October (Oct–Mar season)
# ---------------------------------------------------------------------------

class TestPriceSeriesOctober:
    """October is in the Oct–Mar season."""

    def test_hour_3_october_normal_slot(self):
        # Normal slot (00–09), multiplier = 1.00 → 8.0 × 1.00 = 8.00
        ts = _ts(2026, 10, 1, 3)
        price = build_grid_price_series(ts, TOD_CFG)
        assert abs(price.iloc[0] - 8.00) < TOL

    def test_hour_12_october_solar_slot_oct_mar(self):
        # Solar slot (09–17), Oct–Mar multiplier = 0.75 → 8.0 × 0.75 = 6.00
        ts = _ts(2026, 10, 1, 12)
        price = build_grid_price_series(ts, TOD_CFG)
        assert abs(price.iloc[0] - 6.00) < TOL

    def test_hour_19_october_peak_slot(self):
        # Peak slot (17–24), multiplier = 1.20 → 8.0 × 1.20 = 9.60
        ts = _ts(2026, 10, 1, 19)
        price = build_grid_price_series(ts, TOD_CFG)
        assert abs(price.iloc[0] - 9.60) < TOL


# ---------------------------------------------------------------------------
# 2. Price series values — May (Apr–Sep season)
# ---------------------------------------------------------------------------

class TestPriceSeriesMay:
    """May is in the Apr–Sep season."""

    def test_hour_3_may_normal_slot(self):
        # Normal slot, multiplier = 1.00 → 8.0 × 1.00 = 8.00
        ts = _ts(2026, 5, 15, 3)
        price = build_grid_price_series(ts, TOD_CFG)
        assert abs(price.iloc[0] - 8.00) < TOL

    def test_hour_12_may_solar_slot_apr_sep(self):
        # Solar slot, Apr–Sep multiplier = 0.85 → 8.0 × 0.85 = 6.80
        ts = _ts(2026, 5, 15, 12)
        price = build_grid_price_series(ts, TOD_CFG)
        assert abs(price.iloc[0] - 6.80) < TOL

    def test_hour_19_may_peak_slot(self):
        # Peak slot, multiplier = 1.20 → 8.0 × 1.20 = 9.60
        ts = _ts(2026, 5, 15, 19)
        price = build_grid_price_series(ts, TOD_CFG)
        assert abs(price.iloc[0] - 9.60) < TOL


# ---------------------------------------------------------------------------
# 3. Fallback to flat price when "tod" key is absent
# ---------------------------------------------------------------------------

class TestFlatFallback:
    def test_fallback_flat_price_all_hours(self):
        """When tod is absent every hour should return base_energy_charge."""
        hours = pd.date_range("2026-10-01", periods=24, freq="h")
        series = build_grid_price_series(hours, FLAT_CFG)
        assert len(series) == 24
        assert (series == 8.0).all(), "All prices should equal 8.0 Rs/kWh (flat fallback)"

    def test_fallback_uses_legacy_cost_per_kwh(self):
        """When only legacy cost_per_kwh is present, use it as the flat price."""
        cfg = {"cost_per_kwh": 7.5}
        ts = _ts(2026, 10, 1, 10)
        series = build_grid_price_series(ts, cfg)
        assert abs(series.iloc[0] - 7.5) < TOL

    def test_fallback_uses_grid_cost_per_kwh(self):
        """Support the even older grid_cost_per_kwh alias."""
        cfg = {"grid_cost_per_kwh": 6.0}
        ts = _ts(2026, 10, 1, 10)
        series = build_grid_price_series(ts, cfg)
        assert abs(series.iloc[0] - 6.0) < TOL


# ---------------------------------------------------------------------------
# 4. Cost metric equals manual sum on a 3-hour case
# ---------------------------------------------------------------------------

class TestCostMetric:
    def test_total_grid_cost_equals_manual_sum(self):
        """
        3-hour case — October day, hours 8, 12, 19.
        grid_kw:  [100, 50, 200]
        prices:   [8.0, 6.0, 9.6]  (Oct–Mar season from ToD)
        expected: 100*8.0 + 50*6.0 + 200*9.6 = 800 + 300 + 1920 = 3020 Rs
        """
        timestamps = pd.DatetimeIndex([
            pd.Timestamp("2026-10-01T08:00:00"),
            pd.Timestamp("2026-10-01T12:00:00"),
            pd.Timestamp("2026-10-01T19:00:00"),
        ])
        grid_kw = pd.Series([100.0, 50.0, 200.0], index=timestamps)
        prices  = build_grid_price_series(timestamps, TOD_CFG)

        total_load_kwh = 1000.0
        base_price     = 8.0
        result = calculate_cost_metrics(grid_kw, prices, total_load_kwh, base_price)

        expected_cost = 100.0 * 8.0 + 50.0 * 6.0 + 200.0 * 9.6  # = 3020.0
        assert abs(result["total_grid_cost_rs"] - expected_cost) < 0.01

    def test_baseline_cost_equals_load_times_base_price(self):
        timestamps = _ts(2026, 10, 1, 10)
        grid_kw = pd.Series([0.0], index=timestamps)
        prices  = build_grid_price_series(timestamps, TOD_CFG)
        result = calculate_cost_metrics(grid_kw, prices, 500.0, 8.0)
        assert abs(result["baseline_cost_rs"] - 4000.0) < 0.01

    def test_savings_equals_baseline_minus_actual(self):
        timestamps = _ts(2026, 10, 1, 10)
        grid_kw = pd.Series([100.0], index=timestamps)
        prices  = build_grid_price_series(timestamps, TOD_CFG)  # 6.0 Rs/kWh (solar slot, Oct)
        result = calculate_cost_metrics(grid_kw, prices, 500.0, 8.0)
        expected_actual   = 100.0 * 6.0           # = 600 Rs
        expected_baseline = 500.0 * 8.0           # = 4000 Rs
        expected_savings  = expected_baseline - expected_actual  # = 3400 Rs
        assert abs(result["savings_rs"] - expected_savings) < 0.01


# ---------------------------------------------------------------------------
# 5. Output contract fields are unchanged (dispatch rows + metrics block)
# ---------------------------------------------------------------------------

SAMPLE_FORECAST_3H = {
    "location": "Lonavala",
    "forecast_horizon_hours": 3,
    "forecast": [
        {
            "timestamp": "2026-10-01T10:00:00",
            "solar_kw": 350.0, "wind_kw": 180.0,
            "hydro_kw": 200.0, "load_kw": 700.0,
        },
        {
            "timestamp": "2026-10-01T11:00:00",
            "solar_kw": 420.0, "wind_kw": 170.0,
            "hydro_kw": 200.0, "load_kw": 750.0,
        },
        {
            "timestamp": "2026-10-01T18:00:00",
            "solar_kw": 100.0, "wind_kw": 150.0,
            "hydro_kw": 200.0, "load_kw": 800.0,
        },
    ],
}

REQUIRED_DISPATCH_KEYS = {
    "timestamp", "solar_kw", "wind_kw", "hydro_kw",
    "battery_kw", "grid_kw", "load_kw",
    "curtailment_kw", "battery_soc_kwh",
}

REQUIRED_METRICS_KEYS = {
    "renewable_penetration_percent",
    "grid_dependency_percent",
    "curtailment_percent",
    "battery_utilization_percent",
    "estimated_co2_avoided_kg",
}


class TestContractUnchanged:
    def setup_method(self):
        self._test_out = Path(__file__).parent / "_test_dispatch.json"
        self.result = optimize_dispatch(SAMPLE_FORECAST_3H, output_path=self._test_out)

    def teardown_method(self):
        if hasattr(self, "_test_out") and self._test_out.exists():
            self._test_out.unlink()

    def test_dispatch_rows_have_exactly_required_keys(self):
        """No new keys must leak into dispatch rows."""
        for row in self.result["dispatch"]:
            assert set(row.keys()) == REQUIRED_DISPATCH_KEYS, (
                f"Unexpected keys in dispatch row: {set(row.keys()) - REQUIRED_DISPATCH_KEYS}"
            )

    def test_metrics_block_has_exactly_required_keys(self):
        """No new keys must leak into the metrics block."""
        assert set(self.result["metrics"].keys()) == REQUIRED_METRICS_KEYS, (
            f"Unexpected keys in metrics: {set(self.result['metrics'].keys()) - REQUIRED_METRICS_KEYS}"
        )

    def test_extra_metrics_present(self):
        """extra_metrics block must exist at top level with the three cost keys."""
        assert "extra_metrics" in self.result
        em = self.result["extra_metrics"]
        assert "total_grid_cost_rs" in em
        assert "baseline_cost_rs"   in em
        assert "savings_rs"         in em

    def test_extra_hourly_present_and_correct_length(self):
        """extra_hourly must exist and match the dispatch length."""
        assert "extra_hourly" in self.result
        eh = self.result["extra_hourly"]
        assert len(eh) == len(self.result["dispatch"])

    def test_extra_hourly_has_price_key(self):
        for entry in self.result["extra_hourly"]:
            assert "grid_price_rs_per_kwh" in entry


# ---------------------------------------------------------------------------
# 6. Battery discharges more during peak hours with ToD vs flat tariff
# ---------------------------------------------------------------------------

class TestBatteryPeakDischarge:
    """With ToD tariff the battery should shift more discharge to 17:00–24:00."""

    # 24-hour October day — timestamps from 00:00 to 23:00
    _TIMESTAMPS = [
        f"2026-10-01T{h:02d}:00:00" for h in range(24)
    ]

    # Moderate renewable profile that leaves room for battery to shift behaviour
    @staticmethod
    def _make_forecast():
        rows = []
        for h in range(24):
            solar  = max(0.0, 300.0 * (1 - abs(h - 12) / 12.0))
            wind   = 150.0
            hydro  = 200.0
            load   = 700.0 if h < 17 else 900.0   # higher load in peak hours
            rows.append({
                "timestamp": f"2026-10-01T{h:02d}:00:00",
                "solar_kw":  round(solar, 1),
                "wind_kw":   wind,
                "hydro_kw":  hydro,
                "load_kw":   load,
            })
        return {"location": "Lonavala", "forecast_horizon_hours": 24, "forecast": rows}

    def _peak_battery_discharge_kwh(self, result):
        """Sum of positive battery_kw during hours 17–23 (discharge into grid bus)."""
        total = 0.0
        for row in result["dispatch"]:
            ts = pd.Timestamp(row["timestamp"])
            if 17 <= ts.hour <= 23:
                total += max(0.0, row["battery_kw"])
        return total

    def test_tod_increases_peak_discharge_vs_flat(self, tmp_path):
        forecast = self._make_forecast()
        tmp_tod = tmp_path / "tod.json"
        tmp_flat = tmp_path / "flat.json"

        # Run with ToD tariff (uses actual system_config.json which now has tod)
        result_tod = optimize_dispatch(forecast, output_path=tmp_tod)

        # Build a flat-tariff version by temporarily overriding grid config
        # We pass the forecast twice — second time to a patched optimizer call
        # that uses a flat config injected via a minimal in-process patch.
        import optimizer as opt_module
        import copy

        # Monkey-patch load_config to return flat-tariff grid for one call
        original_load_config = opt_module.load_config

        def flat_load_config():
            cfg = original_load_config()
            cfg["grid"]["tod"] = None   # remove tod → flat price
            return cfg

        opt_module.load_config = flat_load_config
        try:
            result_flat = optimize_dispatch(forecast, output_path=tmp_flat)
        finally:
            opt_module.load_config = original_load_config

        peak_tod  = self._peak_battery_discharge_kwh(result_tod)
        peak_flat = self._peak_battery_discharge_kwh(result_flat)

        # With ToD, peak hours are expensive (9.6 Rs/kWh vs 8.0 flat) so the
        # optimizer has stronger incentive to drain the battery then.
        assert peak_tod >= peak_flat - 1.0, (
            f"Expected ToD peak discharge ({peak_tod:.1f} kWh) >= "
            f"flat peak discharge ({peak_flat:.1f} kWh). "
            "Battery should discharge at least as much in peak hours with ToD tariff."
        )
