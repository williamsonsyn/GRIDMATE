"""
test_predict.py
===============
Automated pytest suite for GridMate Version 2 Inference Engine and Scenario Simulation
(forecasting_real_data/src/predict.py).

Responsibilities & Requirements Covered:
1. Valid forecast generation for 6, 12 and 24-hour horizons.
2. All five scenarios: normal, cloudy, heavy_monsoon, high_wind, peak_demand.
3. Baseline and experimental Wind model selection.
4. Exact forecast JSON contract schema and hourly timestamp continuity.
5. Non-negative and finite prediction values; night solar rule.
6. Rejection of invalid horizons, scenarios, and model options.
7. Comprehensive custom future-weather validation:
   - Missing columns
   - Missing values (NaN)
   - Infinite values (inf)
   - Target columns (leakage prevention)
   - Incorrect / misaligned timestamps
   - Invalid humidity, cloud cover, wind direction, pressure, and negative values.
8. Recursive load lag-1 and lag-24 calculations without lookahead leakage,
   including explicit verification of historical_load_lag_24 values at every step.
9. Peak-demand uplift applied exactly once per raw prediction (1.25x),
   with adjusted predictions fed into recursive history without compounding.
10. Immutability of original input DataFrames.
11. File persistence to requested output paths using temporary directories.
12. Determinism and synthetic demonstration labelling of default weather generation.

Data Provenance & Authenticity Disclaimer:
All tests utilize AI-generated synthetic demonstration data and models calibrated to
illustrative Lonavala characteristics; outputs do not represent live utility records.
"""

from datetime import datetime
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forecasting_real_data.src.predict import (
    CONTRACT_RECORD_KEYS,
    CONTRACT_TOP_KEYS,
    LOCATION_NAME,
    VALID_SCENARIOS,
    VALID_WIND_MODELS,
    generate_forecast,
    generate_forecast_dataframe,
    load_historical_context,
    load_trained_models,
)


@pytest.fixture(scope="module")
def historical_data() -> pd.DataFrame:
    """Load combined historical context once for test module."""
    return load_historical_context()


@pytest.fixture
def origin_ts(historical_data: pd.DataFrame) -> pd.Timestamp:
    """Last historical observation timestamp T_0."""
    return historical_data["timestamp"].iloc[-1]


def make_valid_future_weather(
    origin_ts: pd.Timestamp,
    horizon: int = 6,
) -> pd.DataFrame:
    """
    Generate a clean, strictly valid future weather DataFrame
    immediately following origin_ts.
    """
    start_ts = origin_ts + pd.Timedelta(hours=1)
    timestamps = pd.date_range(start=start_ts, periods=horizon, freq="1h")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "solar_irradiance": [150.0] * horizon,
            "temperature": [22.5] * horizon,
            "humidity": [65.0] * horizon,
            "pressure": [995.0] * horizon,
            "wind_speed": [5.2] * horizon,
            "wind_direction": [180.0] * horizon,
            "rainfall": [0.0] * horizon,
            "cloud_cover": [25.0] * horizon,
            "water_flow": [12.0] * horizon,
        }
    )


# =============================================================================
# 1. Valid Forecast Horizons (6, 12, 24 Hours)
# =============================================================================

@pytest.mark.parametrize("h", [6, 12, 24])
def test_valid_horizons(h: int, tmp_path: Path):
    """Verify forecast generation for valid horizons 6, 12, and 24 hours."""
    out_file = tmp_path / f"forecast_{h}h.json"
    result = generate_forecast(horizon=h, save_output=True, output_path=out_file)
    assert result["location"] == LOCATION_NAME
    assert result["forecast_horizon_hours"] == h
    assert len(result["forecast"]) == h
    assert out_file.exists()


def test_generate_forecast_dataframe_wrapper():
    """Verify DataFrame convenience wrapper output structure and types."""
    df = generate_forecast_dataframe(horizon=6, save_output=False)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 6
    expected_cols = ["timestamp", "solar_kw", "wind_kw", "hydro_kw", "load_kw"]
    assert list(df.columns) == expected_cols
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


# =============================================================================
# 2. All Five Scenarios
# =============================================================================

@pytest.mark.parametrize("scenario", VALID_SCENARIOS)
def test_all_five_scenarios_execution(scenario: str):
    """Verify that all five master scenarios execute successfully and return contract payloads."""
    result = generate_forecast(scenario=scenario, horizon=12, save_output=False)
    assert result["location"] == LOCATION_NAME
    assert result["forecast_horizon_hours"] == 12
    assert len(result["forecast"]) == 12


def test_scenario_behaviour_comparisons():
    """
    Verify relative meteorological and demand behaviour across scenarios:
    - cloudy reduces solar generation compared to normal.
    - heavy_monsoon reduces solar and elevates hydro generation compared to normal.
    - high_wind elevates wind generation compared to normal.
    - peak_demand elevates electricity load compared to normal.
    """
    horizon = 24
    normal = generate_forecast(scenario="normal", horizon=horizon, save_output=False)
    cloudy = generate_forecast(scenario="cloudy", horizon=horizon, save_output=False)
    monsoon = generate_forecast(scenario="heavy_monsoon", horizon=horizon, save_output=False)
    high_wind = generate_forecast(scenario="high_wind", horizon=horizon, save_output=False)
    peak_demand = generate_forecast(scenario="peak_demand", horizon=horizon, save_output=False)

    df_norm = pd.DataFrame(normal["forecast"])
    df_cloudy = pd.DataFrame(cloudy["forecast"])
    df_monsoon = pd.DataFrame(monsoon["forecast"])
    df_wind = pd.DataFrame(high_wind["forecast"])
    df_peak = pd.DataFrame(peak_demand["forecast"])

    # 1. Cloudy attenuates solar generation
    assert df_cloudy["solar_kw"].sum() < df_norm["solar_kw"].sum()

    # 2. Monsoon attenuates solar and boosts hydro generation
    assert df_monsoon["solar_kw"].sum() < df_norm["solar_kw"].sum()
    assert df_monsoon["hydro_kw"].sum() >= df_norm["hydro_kw"].sum()

    # 3. High wind boosts wind generation
    assert df_wind["wind_kw"].sum() >= df_norm["wind_kw"].sum()

    # 4. Peak demand boosts load demand
    assert df_peak["load_kw"].sum() > df_norm["load_kw"].sum()


# =============================================================================
# 3. Baseline and Experimental Wind Model Selection
# =============================================================================

@pytest.mark.parametrize("wind_model", VALID_WIND_MODELS)
def test_wind_model_variants(wind_model: str):
    """Test that both baseline and experimental Wind models load and generate valid predictions."""
    result = generate_forecast(wind_model=wind_model, horizon=12, save_output=False)
    assert len(result["forecast"]) == 12
    df = pd.DataFrame(result["forecast"])
    assert (df["wind_kw"] >= 0.0).all()
    assert np.isfinite(df["wind_kw"]).all()


# =============================================================================
# 4. Exact JSON Schema & Hourly Timestamp Continuity
# =============================================================================

def test_forecast_json_schema_and_continuity(origin_ts: pd.Timestamp):
    """Test top-level and record-level contract schema and timestamp continuity."""
    horizon = 24
    result = generate_forecast(horizon=horizon, save_output=False)

    # Top-level schema check
    assert set(result.keys()) == CONTRACT_TOP_KEYS
    assert result["location"] == LOCATION_NAME
    assert result["forecast_horizon_hours"] == horizon

    records = result["forecast"]
    assert len(records) == horizon

    timestamps = []
    for idx, rec in enumerate(records):
        assert set(rec.keys()) == CONTRACT_RECORD_KEYS
        # ISO-8601 validation
        dt = datetime.fromisoformat(rec["timestamp"])
        timestamps.append(pd.Timestamp(dt))

        # Check numerical finite types
        for col in ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]:
            assert isinstance(rec[col], (int, float))
            assert not np.isnan(rec[col])
            assert not np.isinf(rec[col])

    # Check continuity: first step is T_0 + 1h
    expected_start = origin_ts + pd.Timedelta(hours=1)
    assert timestamps[0] == expected_start

    # Continuous 1-hour steps
    ts_series = pd.Series(timestamps)
    diffs = ts_series.diff().iloc[1:]
    assert (diffs == pd.Timedelta(hours=1)).all()


# =============================================================================
# 5. Non-negative and Finite Values; Night Solar Rule
# =============================================================================

@pytest.mark.parametrize("scenario", VALID_SCENARIOS)
def test_non_negative_finite_and_solar_night_rule(scenario: str):
    """Ensure all predictions are non-negative and finite, and solar generation is 0 at night."""
    result = generate_forecast(scenario=scenario, horizon=24, save_output=False)
    for rec in result["forecast"]:
        dt = datetime.fromisoformat(rec["timestamp"])
        hour = dt.hour

        assert rec["solar_kw"] >= 0.0
        assert rec["wind_kw"] >= 0.0
        assert rec["hydro_kw"] >= 0.0
        assert rec["load_kw"] >= 0.0

        # Physical solar night rule: 0 between 19:00 and 05:00
        if hour < 6 or hour > 18:
            assert rec["solar_kw"] == 0.0


# =============================================================================
# 6. Invalid Horizons, Scenarios, and Model Selections
# =============================================================================

@pytest.mark.parametrize("bad_horizon", [5, 25, 0, -1, 100, "24", 12.5, True, False])
def test_invalid_horizon_raises_value_error(bad_horizon):
    """Verify that horizons < 6, > 24, or non-integer types raise ValueError."""
    with pytest.raises(ValueError, match="Forecast horizon must be an integer between 6 and 24"):
        generate_forecast(horizon=bad_horizon, save_output=False)


@pytest.mark.parametrize("bad_scenario", ["storm", "hurricane", "sunny", "", None, 123])
def test_invalid_scenario_raises_value_error(bad_scenario):
    """Verify that unrecognized scenarios raise ValueError."""
    with pytest.raises(ValueError, match="Unrecognized scenario"):
        generate_forecast(scenario=bad_scenario, save_output=False)


@pytest.mark.parametrize("bad_model", ["candidate", "transformer", "arima", "", None])
def test_invalid_wind_model_raises_value_error(bad_model):
    """Verify that unrecognized wind models raise ValueError."""
    with pytest.raises(ValueError, match="Unrecognized wind_model|Invalid wind_model"):
        generate_forecast(wind_model=bad_model, save_output=False)


# =============================================================================
# 7. Custom Future Weather Validation
# =============================================================================

def test_custom_weather_valid(origin_ts: pd.Timestamp):
    """Verify that valid custom future inputs produce forecasts matching horizon."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    result = generate_forecast(input_data=df_custom, horizon=6, save_output=False)
    assert len(result["forecast"]) == 6


def test_custom_weather_row_count_mismatch(origin_ts: pd.Timestamp):
    """Length mismatch between input_data and horizon raises ValueError."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    with pytest.raises(ValueError, match="Input data length mismatch"):
        generate_forecast(input_data=df_custom, horizon=12, save_output=False)


def test_custom_weather_missing_columns(origin_ts: pd.Timestamp):
    """Missing required column raises ValueError."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    df_bad = df_custom.drop(columns=["solar_irradiance"])
    with pytest.raises(ValueError, match="missing required column"):
        generate_forecast(input_data=df_bad, horizon=6, save_output=False)


def test_custom_weather_missing_values(origin_ts: pd.Timestamp):
    """NaN value in input raises ValueError."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    df_custom.loc[2, "temperature"] = np.nan
    with pytest.raises(ValueError, match="contains NaN values"):
        generate_forecast(input_data=df_custom, horizon=6, save_output=False)


def test_custom_weather_infinite_values(origin_ts: pd.Timestamp):
    """Infinite value in input raises ValueError."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    df_custom.loc[1, "wind_speed"] = np.inf
    with pytest.raises(ValueError, match="contains infinite values"):
        generate_forecast(input_data=df_custom, horizon=6, save_output=False)


@pytest.mark.parametrize("target_col", ["load_kw", "solar_kw", "wind_kw", "hydro_kw"])
def test_custom_weather_forbidden_targets(origin_ts: pd.Timestamp, target_col: str):
    """Supplying target columns in future weather raises ValueError to prevent data leakage."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    df_custom[target_col] = 100.0
    with pytest.raises(ValueError, match="Target column.*detected in future inputs"):
        generate_forecast(input_data=df_custom, horizon=6, save_output=False)


def test_custom_weather_incorrect_start_timestamp(origin_ts: pd.Timestamp):
    """First timestamp not immediately following T_0 raises ValueError."""
    start_ts = origin_ts + pd.Timedelta(hours=5)
    timestamps = pd.date_range(start=start_ts, periods=6, freq="1h")
    df_bad = make_valid_future_weather(origin_ts, horizon=6)
    df_bad["timestamp"] = timestamps
    with pytest.raises(ValueError, match="timestamps must immediately follow"):
        generate_forecast(input_data=df_bad, horizon=6, save_output=False)


def test_custom_weather_non_continuous_timestamps(origin_ts: pd.Timestamp):
    """Non-continuous hourly steps raise ValueError."""
    start_ts = origin_ts + pd.Timedelta(hours=1)
    timestamps = pd.date_range(start=start_ts, periods=6, freq="2h")
    df_bad = make_valid_future_weather(origin_ts, horizon=6)
    df_bad["timestamp"] = timestamps
    with pytest.raises(ValueError, match="continuous hourly observations"):
        generate_forecast(input_data=df_bad, horizon=6, save_output=False)


def test_custom_weather_duplicate_timestamps(origin_ts: pd.Timestamp):
    """Duplicate timestamps raise ValueError."""
    df_bad = make_valid_future_weather(origin_ts, horizon=6)
    df_bad.loc[1, "timestamp"] = df_bad.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        generate_forecast(input_data=df_bad, horizon=6, save_output=False)


@pytest.mark.parametrize(
    "col, bad_val, err_pattern",
    [
        # humidity: must be in [0, 100]. Actual message:
        #   "Input data column 'humidity' contains N value(s) outside physical range [0, 100]."
        ("humidity", -1.0, r"'humidity' contains \d+ value\(s\) outside physical range"),
        ("humidity", 100.5, r"'humidity' contains \d+ value\(s\) outside physical range"),
        # cloud_cover: must be in [0, 100]. Actual message mirrors humidity.
        ("cloud_cover", -0.1, r"'cloud_cover' contains \d+ value\(s\) outside physical range"),
        ("cloud_cover", 101.0, r"'cloud_cover' contains \d+ value\(s\) outside physical range"),
        # wind_direction: must be in [0, 360]. Actual message mirrors humidity.
        ("wind_direction", -5.0, r"'wind_direction' contains \d+ value\(s\) outside physical range"),
        ("wind_direction", 360.5, r"'wind_direction' contains \d+ value\(s\) outside physical range"),
        # pressure: must be strictly > 0. Actual message:
        #   "Input data column 'pressure' contains N non-positive value(s); pressure must be strictly greater than zero."
        ("pressure", 0.0, r"pressure must be strictly greater than zero"),
        ("pressure", -10.0, r"pressure must be strictly greater than zero"),
        # Non-negative variables. Actual message:
        #   "Input data column '{col}' contains N negative value(s)."
        ("solar_irradiance", -5.0, r"'solar_irradiance' contains \d+ negative value\(s\)"),
        ("wind_speed", -1.0, r"'wind_speed' contains \d+ negative value\(s\)"),
        ("rainfall", -0.5, r"'rainfall' contains \d+ negative value\(s\)"),
        ("water_flow", -2.0, r"'water_flow' contains \d+ negative value\(s\)"),
    ],
)
def test_custom_weather_domain_bounds(origin_ts: pd.Timestamp, col: str, bad_val: float, err_pattern: str):
    """Test physical domain bound violations raise descriptive ValueError."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    df_custom.loc[2, col] = bad_val
    with pytest.raises(ValueError, match=err_pattern):
        generate_forecast(input_data=df_custom, horizon=6, save_output=False)


# =============================================================================
# 8. Recursive Load Forecasting Mechanics (No Future Leakage)
# =============================================================================

def test_recursive_load_lag_mechanics(historical_data: pd.DataFrame):
    """
    Verify recursive load forecasting mechanics at every step of a 6-hour horizon:

    historical_load_lag_1 rules:
    - Step 0 (h=1): must equal the actual observed load at T_0 (last_obs["load_kw"]).
    - Step k (h=k+1) for k >= 1: must equal the previous step's predicted load
      (from rolling_load_preds, which is pred_load = max(0, raw), i.e. unrounded).

    historical_load_lag_24 rules (6-hour horizon only):
    - For all 6 steps the lag timestamp (current_ts - 24h) is <= T_0, so each
      lag_24 value is looked up directly from the observed historical dataset.
    - Verified by computing history.set_index("timestamp").loc[lag_ts, "load_kw"]
      for every step, confirming no future target value ever enters inference.
    """
    # Build the expected lag-24 values using the same logic as predict.py
    origin_ts = historical_data["timestamp"].iloc[-1]
    start_forecast_ts = origin_ts + pd.Timedelta(hours=1)
    history_lookup = historical_data.set_index("timestamp")
    last_obs = historical_data.iloc[-1]

    horizon = 6
    expected_lag24: list[float] = []
    for step_idx in range(horizon):
        current_ts = start_forecast_ts + pd.Timedelta(hours=step_idx)
        lag_24_ts = current_ts - pd.Timedelta(hours=24)
        # For a 6-hour horizon every lag timestamp is well within history
        assert lag_24_ts <= origin_ts, f"step {step_idx}: lag_24_ts {lag_24_ts} should be <= origin_ts {origin_ts}"
        assert lag_24_ts in history_lookup.index, f"step {step_idx}: lag timestamp {lag_24_ts} missing from history"
        expected_lag24.append(float(history_lookup.loc[lag_24_ts, "load_kw"]))

    # Spy on the load model to capture the exact feature values passed each step
    captured_lag1: list[float] = []
    captured_lag24: list[float] = []
    models = load_trained_models(wind_model="baseline")
    load_model = models["load"]
    original_predict = load_model.predict

    def spy_predict(features):
        captured_lag1.append(float(features["historical_load_lag_1"].iloc[0]))
        captured_lag24.append(float(features["historical_load_lag_24"].iloc[0]))
        return original_predict(features)

    with patch.object(load_model, "predict", side_effect=spy_predict):
        result = generate_forecast(horizon=horizon, save_output=False)

    assert len(captured_lag1) == horizon
    assert len(captured_lag24) == horizon

    # --- lag-1 assertions ---
    # Step 0: must receive the actual historical load at T_0 (unmodified)
    assert captured_lag1[0] == pytest.approx(float(last_obs["load_kw"]))

    # Steps 1–5: must receive the previous step's predicted load exactly
    # (rolling_load_preds stores pred_load = max(0, raw), which may differ from the
    # rounded forecast record by up to 0.01; use abs=0.02 to accommodate rounding)
    for step_idx in range(1, horizon):
        prev_pred = result["forecast"][step_idx - 1]["load_kw"]
        assert captured_lag1[step_idx] == pytest.approx(prev_pred, abs=0.02), (
            f"step {step_idx}: lag_1 input {captured_lag1[step_idx]:.4f} "
            f"does not match previous predicted load {prev_pred:.4f}"
        )

    # --- lag-24 assertions ---
    # Every step in a 6-hour horizon must draw from observed history, never from future targets
    for step_idx in range(horizon):
        assert captured_lag24[step_idx] == pytest.approx(expected_lag24[step_idx]), (
            f"step {step_idx}: lag_24 input {captured_lag24[step_idx]:.4f} "
            f"does not match expected historical value {expected_lag24[step_idx]:.4f}"
        )


# =============================================================================
# 9. Peak-Demand Uplift Applied Once Without Compounding
# =============================================================================

def test_peak_demand_uplift_applied_once_without_compounding():
    """
    Verify the peak_demand scenario applies exactly a 1.25x multiplier to each
    raw load model prediction, with no compounding through lag inputs.

    Specifically:
    1. The raw prediction returned by load_model.predict() is captured per step.
    2. Each final forecast load = max(0.0, raw * 1.25), rounded to 2 d.p.
       (abs=0.02 tolerance covers the round-then-compare gap).
    3. The unrounded adjusted prediction (pred_load = max(0, raw*1.25)) is fed
       into rolling_load_preds and used as lag_1 for the next step.
    4. The lag_1 and lag_24 inputs to the model are NOT pre-multiplied by 1.25.
    5. NOTE: cumulative uplift across the horizon CAN exceed 25% because adjusted
       predictions propagate through the recursive lag-1 chain, so we do NOT
       assert that the whole forecast is exactly 25% above normal.
    """
    raw_preds: list[float] = []
    captured_lag1: list[float] = []
    models = load_trained_models(wind_model="baseline")
    load_model = models["load"]
    original_predict = load_model.predict

    def spy_predict(features):
        captured_lag1.append(float(features["historical_load_lag_1"].iloc[0]))
        out = original_predict(features)
        raw_preds.append(float(out[0]))
        return out

    with patch.object(load_model, "predict", side_effect=spy_predict):
        result = generate_forecast(scenario="peak_demand", horizon=6, save_output=False)

    horizon = 6
    assert len(raw_preds) == horizon
    assert len(captured_lag1) == horizon

    # 1. Each final prediction == max(0.0, raw * 1.25), within rounding tolerance
    for step_idx in range(horizon):
        expected_pred = max(0.0, raw_preds[step_idx] * 1.25)
        actual_pred = result["forecast"][step_idx]["load_kw"]
        assert actual_pred == pytest.approx(expected_pred, abs=0.02), (
            f"step {step_idx}: final pred {actual_pred:.4f} != max(0, raw*1.25) = {expected_pred:.4f}"
        )

    # 2. Lag-1 inputs to the model must equal the previous adjusted prediction,
    #    proving the adjusted value is propagated without an additional 1.25 multiplier.
    #    Step 0 lag-1 is the observed historical load — not checked here (covered by test_recursive_load_lag_mechanics).
    for step_idx in range(1, horizon):
        prev_pred = result["forecast"][step_idx - 1]["load_kw"]
        assert captured_lag1[step_idx] == pytest.approx(prev_pred, abs=0.02), (
            f"step {step_idx}: lag_1 input {captured_lag1[step_idx]:.4f} "
            f"does not match previous adjusted prediction {prev_pred:.4f} — "
            "suggests lag input was double-multiplied"
        )

    # 3. Confirm the lag-1 input is NOT the raw (un-uplifted) model output,
    #    i.e. the full uplifted value is propagated, not the original raw value.
    #    For step 1 onwards: lag_1 should be ~1.25 * raw[step-1], not ~raw[step-1].
    for step_idx in range(1, horizon):
        raw_prev = raw_preds[step_idx - 1]
        unadjusted_lag1 = max(0.0, raw_prev)   # what lag-1 would be WITHOUT the 1.25 uplift
        # The captured lag-1 should be closer to 1.25*raw_prev than to raw_prev
        # (provided raw_prev > 0, which holds for all load forecasts)
        if raw_prev > 0:
            adjusted_lag1_expected = max(0.0, raw_prev * 1.25)
            diff_from_adjusted = abs(captured_lag1[step_idx] - adjusted_lag1_expected)
            diff_from_unadjusted = abs(captured_lag1[step_idx] - unadjusted_lag1)
            assert diff_from_adjusted < diff_from_unadjusted, (
                f"step {step_idx}: lag_1 input {captured_lag1[step_idx]:.4f} is closer to "
                f"unadjusted raw {unadjusted_lag1:.4f} than to adjusted {adjusted_lag1_expected:.4f} — "
                "adjusted prediction is not being propagated into recursive history"
            )


# =============================================================================
# 10. Immutability of Original Input DataFrames
# =============================================================================

def test_input_dataframe_immutability(origin_ts: pd.Timestamp):
    """Verify that passing an input_data DataFrame does not mutate it in-place."""
    df_custom = make_valid_future_weather(origin_ts, horizon=6)
    df_copy = df_custom.copy(deep=True)

    for scn in VALID_SCENARIOS:
        generate_forecast(input_data=df_custom, scenario=scn, horizon=6, save_output=False)
        pd.testing.assert_frame_equal(df_custom, df_copy)


# =============================================================================
# 11. Output Persistence to Requested Custom Path
# =============================================================================

def test_save_forecast_to_custom_path(tmp_path: Path):
    """Verify that forecasts persist to custom output paths without touching committed demonstration files."""
    custom_dir = tmp_path / "custom_outputs"
    custom_file = custom_dir / "forecast_run.json"

    result = generate_forecast(
        horizon=6,
        save_output=True,
        output_path=custom_file,
    )

    assert custom_file.exists()
    with open(custom_file, "r", encoding="utf-8") as f:
        persisted = json.load(f)

    assert persisted == result
    assert persisted["forecast_horizon_hours"] == 6
    assert len(persisted["forecast"]) == 6


# =============================================================================
# 12. Default Weather Determinism & Synthetic Disclaimer
# =============================================================================

def test_demonstration_weather_deterministic():
    """Verify that generating forecasts with default inputs is completely deterministic."""
    res1 = generate_forecast(horizon=12, save_output=False)
    res2 = generate_forecast(horizon=12, save_output=False)
    assert res1 == res2


def test_demonstration_weather_synthetic_disclaimer(capsys):
    """Verify that default demonstration weather prints the synthetic disclaimer."""
    generate_forecast(input_data=None, horizon=6, save_output=False)
    captured = capsys.readouterr()
    assert "DISCLAIMER" in captured.out
    assert "AI-generated synthetic demonstration inputs" in captured.out
    assert "NOT actual measured Lonavala weather forecasts" in captured.out
