"""
test_scenarios.py
=================
Automated tests for scenarios, edge cases, and deterministic inference (forecasting/src/predict.py, utils.py).
"""

import numpy as np
import pandas as pd
import pytest

from forecasting.src.predict import generate_forecast
from forecasting.src.utils import validate_future_inputs


@pytest.fixture(scope="module")
def scenario_forecasts():
    """Run all 5 scenarios once for comparison across tests."""
    scenarios = ["normal", "cloudy", "heavy_monsoon", "high_wind", "peak_demand"]
    forecasts = {}
    for sc in scenarios:
        res = generate_forecast(horizon=24, scenario=sc, save_output=False)
        forecasts[sc] = pd.DataFrame(res["forecast"])
    return forecasts


def test_scenario_directionality(scenario_forecasts):
    """Verify expected directional changes across all scenarios compared to normal baseline."""
    norm = scenario_forecasts["normal"]
    cloudy = scenario_forecasts["cloudy"]
    monsoon = scenario_forecasts["heavy_monsoon"]
    wind = scenario_forecasts["high_wind"]
    peak = scenario_forecasts["peak_demand"]

    # 1. Cloudy reduces solar generation significantly
    assert cloudy["solar_kw"].mean() < norm["solar_kw"].mean() * 0.40

    # 2. Heavy monsoon reduces solar and surges hydro generation
    assert monsoon["solar_kw"].mean() < norm["solar_kw"].mean() * 0.20
    assert monsoon["hydro_kw"].mean() > norm["hydro_kw"].mean() * 1.50

    # 3. High wind surges wind generation near rated capacity
    assert wind["wind_kw"].mean() > norm["wind_kw"].mean() * 10.0

    # 4. Peak demand surges electricity demand
    assert peak["load_kw"].mean() > norm["load_kw"].mean() * 1.20


def test_scenario_determinism():
    """Verify repeated calls with identical scenario arguments return bit-identical forecasts."""
    res1 = generate_forecast(horizon=12, scenario="cloudy", save_output=False)
    res2 = generate_forecast(horizon=12, scenario="cloudy", save_output=False)

    assert res1 == res2


def test_invalid_scenario_name_raises_error():
    """Verify unrecognized scenario identifiers raise ValueError."""
    with pytest.raises(ValueError, match="Unrecognized scenario"):
        generate_forecast(horizon=24, scenario="cyclone", save_output=False)


def test_solar_zero_at_night(scenario_forecasts):
    """Verify solar generation is strictly 0.0 during night hours across all scenarios."""
    for sc, df in scenario_forecasts.items():
        hours = pd.to_datetime(df["timestamp"]).dt.hour
        night_mask = (hours < 6) | (hours > 18)
        assert (df.loc[night_mask, "solar_kw"] == 0.0).all(), f"Solar generation observed at night in '{sc}'"


def test_custom_input_validation():
    """Verify input_data validation rejects corrupt or invalid external inputs."""
    timestamps = pd.date_range("2026-10-01 00:00:00", periods=24, freq="h")
    valid_custom = pd.DataFrame(
        {
            "timestamp": timestamps,
            "temperature": 25.0,
            "humidity": 60.0,
            "solar_irradiance": 500.0,
            "cloud_cover": 0.2,
            "wind_speed": 5.0,
            "wind_direction": 90.0,
            "rainfall": 0.0,
            "pressure": 940.0,
            "water_flow": 20.0,
        }
    )

    # 1. Valid custom input succeeds
    res = generate_forecast(input_data=valid_custom, horizon=24, save_output=False)
    assert len(res["forecast"]) == 24

    # 2. Missing columns
    with pytest.raises(ValueError, match="missing required column"):
        validate_future_inputs(valid_custom.drop(columns=["temperature"]), horizon=24)

    # 3. NaNs in input
    bad_nan = valid_custom.copy()
    bad_nan.loc[0, "wind_speed"] = np.nan
    with pytest.raises(ValueError, match="contains NaN values"):
        validate_future_inputs(bad_nan, horizon=24)

    # 4. Infinite values
    bad_inf = valid_custom.copy()
    bad_inf.loc[0, "humidity"] = np.inf
    with pytest.raises(ValueError, match="contains infinite values"):
        validate_future_inputs(bad_inf, horizon=24)

    # 5. Duplicate timestamps
    bad_dup = valid_custom.copy()
    bad_dup.loc[1, "timestamp"] = bad_dup.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        validate_future_inputs(bad_dup, horizon=24)

    # 6. Row count mismatch with horizon
    with pytest.raises(ValueError, match="Input data length mismatch"):
        validate_future_inputs(valid_custom.iloc[:10], horizon=24)


def test_recursive_load_forecasting_uses_preceding_predictions(monkeypatch):
    """
    Verify that hours 2–24 strictly use the preceding predicted load (y_hat_{h-1})
    as historical_load_lag_1 and never use actual future load values.
    """
    from forecasting.src.predict import get_trained_models

    models = get_trained_models()
    load_model = models["load_kw"]

    recorded_lag_1_inputs = []
    original_predict = load_model.predict

    def spy_predict(X):
        if "historical_load_lag_1" in X.columns:
            recorded_lag_1_inputs.append(float(X["historical_load_lag_1"].iloc[0]))
        return original_predict(X)

    monkeypatch.setattr(load_model, "predict", spy_predict)

    # Run forecast for 24 hours
    res = generate_forecast(horizon=24, scenario="normal", save_output=False)
    preds = [r["load_kw"] for r in res["forecast"]]

    assert len(recorded_lag_1_inputs) == 24
    assert len(preds) == 24

    # Hour 1 (index 0) uses observed load at T_0
    # Hours 2-24 (indices 1 to 23) must match the unrounded prediction from step h-1
    for step in range(1, 24):
        expected_lag_1 = preds[step - 1]
        actual_lag_1 = recorded_lag_1_inputs[step]
        # Verify lag 1 is populated from preceding forecast within rounding tolerance
        assert abs(actual_lag_1 - expected_lag_1) < 0.2, (
            f"Step {step + 1} did not use preceding predicted load! "
            f"Expected {expected_lag_1}, got {actual_lag_1}"
        )


def test_insufficient_historical_data_raises_value_error(monkeypatch):
    """
    Verify that the inference pipeline raises a descriptive ValueError if historical
    observations are insufficient to construct the required 24-hour lag buffer.
    """
    import forecasting.src.predict as predict_module
    from forecasting.src.preprocessing import load_and_preprocess_data

    # Truncate history to only 10 rows (insufficient for 24-hour lag lookup)
    df_full = load_and_preprocess_data()
    df_insufficient = df_full.iloc[-10:].copy().reset_index(drop=True)

    monkeypatch.setattr(predict_module, "load_and_preprocess_data", lambda: df_insufficient)

    with pytest.raises(ValueError, match="Insufficient historical data|at least 24"):
        predict_module.generate_forecast(horizon=24, save_output=False)


