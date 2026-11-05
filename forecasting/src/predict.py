"""
predict.py
==========
Inference engine and scenario simulation for GridMate AI Forecasting.

Responsibilities:
1. Provide the callable API: generate_forecast(input_data=None, horizon=24, scenario="normal").
2. Support configurable forecast horizons from 6 to 24 hours (default: 24).
3. Support the 5 master scenario IDs:
   - normal
   - cloudy
   - heavy_monsoon
   - high_wind
   - peak_demand
4. Implement recursive roll-forward multi-step prediction for load_kw without lookahead leakage.
5. Predict solar_kw, wind_kw, and hydro_kw using future weather/water inputs and cached lags.
6. Enforce physical non-negativity across all outputs.
7. Save predictions to forecasting/outputs/forecast.json conforming strictly to the master contract.
8. Provide full CLI entry point: python src/predict.py --scenario normal --horizon 24.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Union

import joblib
import numpy as np
import pandas as pd

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forecasting.src.preprocessing import load_and_preprocess_data
from forecasting.src.features import FEATURE_SETS
from forecasting.src.utils import (
    DEFAULT_HORIZON_HOURS,
    LOCATION_NAME,
    MIN_HORIZON_HOURS,
    MAX_HORIZON_HOURS,
    VALID_SCENARIOS,
    generate_future_weather_inputs,
    apply_scenario_modifications,
    validate_future_inputs,
    validate_forecast_contract,
)

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
DEFAULT_OUTPUT_JSON = Path(__file__).resolve().parents[1] / "outputs" / "forecast.json"

MODEL_PATHS = {
    "solar_kw": MODELS_DIR / "solar_model.joblib",
    "wind_kw": MODELS_DIR / "wind_model.joblib",
    "hydro_kw": MODELS_DIR / "hydro_model.joblib",
    "load_kw": MODELS_DIR / "load_model.joblib",
}

# In-memory cache for loaded model instances
_LOADED_MODELS: Optional[Dict[str, Any]] = None


def get_trained_models() -> Dict[str, Any]:
    """
    Load and cache trained XGBoost model artifacts from forecasting/models/.
    """
    global _LOADED_MODELS
    if _LOADED_MODELS is None:
        _LOADED_MODELS = {}
        for target, path in MODEL_PATHS.items():
            if not path.exists():
                raise FileNotFoundError(
                    f"Trained model artifact not found for '{target}' at: {path}. "
                    "Run 'python forecasting/src/train.py' first."
                )
            _LOADED_MODELS[target] = joblib.load(path)
    return _LOADED_MODELS


def generate_forecast(
    input_data: Optional[pd.DataFrame] = None,
    horizon: int = DEFAULT_HORIZON_HOURS,
    scenario: str = "normal",
    save_output: bool = True,
    output_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Generate 6 to 24-hour ahead energy forecasts for Lonavala.

    Args:
        input_data: Optional DataFrame containing future weather inputs for the horizon.
                    If None, reproducible synthetic inputs are generated for the scenario.
        horizon: Forecast horizon length in hours (6 to 24, default: 24).
        scenario: Selected scenario ID ('normal', 'cloudy', 'heavy_monsoon', 'high_wind', 'peak_demand').
        save_output: Whether to persist results to forecasting/outputs/forecast.json.
        output_path: Destination path for forecast.json.

    Returns:
        Dict[str, Any]: Forecast dictionary adhering strictly to the shared contract.
    """
    # 1. Validate parameters
    if horizon < MIN_HORIZON_HOURS or horizon > MAX_HORIZON_HOURS:
        raise ValueError(
            f"Forecast horizon must be between {MIN_HORIZON_HOURS} and {MAX_HORIZON_HOURS} hours (got {horizon})."
        )
    if scenario not in VALID_SCENARIOS:
        raise ValueError(
            f"Unrecognized scenario '{scenario}'. Allowed scenarios: {VALID_SCENARIOS}"
        )

    # 2. Load historical context for lag generation
    df_history = load_and_preprocess_data()
    df_history = df_history.sort_values("timestamp").reset_index(drop=True)

    if len(df_history) < 24:
        raise ValueError(
            f"Insufficient historical data: at least 24 hours of observations are required "
            f"to populate lag features, but received only {len(df_history)} rows."
        )

    origin_ts = df_history["timestamp"].iloc[-1]
    start_forecast_ts = origin_ts + pd.Timedelta(hours=1)

    # Historical lookups (last 24 hours before origin T_0)
    history_lookup = df_history.set_index("timestamp")
    last_obs = df_history.iloc[-1]

    # 3. Prepare future environmental inputs
    if input_data is None:
        df_future = generate_future_weather_inputs(
            start_timestamp=start_forecast_ts,
            horizon=horizon,
            scenario=scenario,
        )
    else:
        validate_future_inputs(input_data, horizon)
        df_future = input_data.copy().sort_values("timestamp").reset_index(drop=True)
        if scenario != "normal":
            df_future = apply_scenario_modifications(df_future, scenario)

    # 4. Load trained models
    models = get_trained_models()
    solar_model = models["solar_kw"]
    wind_model = models["wind_kw"]
    hydro_model = models["hydro_kw"]
    load_model = models["load_kw"]

    forecast_records = []
    rolling_load_preds = []

    # 5. Step-by-step Inference Engine
    for step_idx in range(horizon):
        row_future = df_future.iloc[step_idx]
        current_ts = pd.to_datetime(row_future["timestamp"])

        # Temporal indicators
        hour = int(current_ts.hour)
        day_of_week = int(current_ts.day_of_week)
        day_of_year = int(current_ts.day_of_year)
        month = int(current_ts.month)
        is_weekend = int(day_of_week >= 5)

        # ---------------------------------------------------------
        # A. Solar Forecast (solar_kw)
        # ---------------------------------------------------------
        if step_idx == 0:
            solar_irradiance_lag_1 = float(last_obs["solar_irradiance"])
        else:
            solar_irradiance_lag_1 = float(df_future.iloc[step_idx - 1]["solar_irradiance"])

        solar_features = pd.DataFrame(
            [
                {
                    "solar_irradiance": float(row_future["solar_irradiance"]),
                    "solar_irradiance_lag_1": solar_irradiance_lag_1,
                    "cloud_cover": float(row_future["cloud_cover"]),
                    "temperature": float(row_future["temperature"]),
                    "humidity": float(row_future["humidity"]),
                    "hour": hour,
                    "month": month,
                    "day_of_year": day_of_year,
                }
            ]
        )[FEATURE_SETS["solar_kw"]]

        if row_future["solar_irradiance"] <= 1.0 or hour < 6 or hour > 18:
            pred_solar = 0.0
        else:
            raw_solar = float(solar_model.predict(solar_features)[0])
            pred_solar = max(0.0, raw_solar)

        # ---------------------------------------------------------
        # B. Wind Forecast (wind_kw)
        # ---------------------------------------------------------
        if step_idx == 0:
            wind_speed_lag_1 = float(last_obs["wind_speed"])
        else:
            wind_speed_lag_1 = float(df_future.iloc[step_idx - 1]["wind_speed"])

        wind_features = pd.DataFrame(
            [
                {
                    "wind_speed": float(row_future["wind_speed"]),
                    "wind_speed_lag_1": wind_speed_lag_1,
                    "wind_direction": float(row_future["wind_direction"]),
                    "pressure": float(row_future["pressure"]),
                    "temperature": float(row_future["temperature"]),
                    "hour": hour,
                    "month": month,
                }
            ]
        )[FEATURE_SETS["wind_kw"]]

        ws = row_future["wind_speed"]
        if ws < 3.0 or ws >= 25.0:
            pred_wind = 0.0
        else:
            raw_wind = float(wind_model.predict(wind_features)[0])
            pred_wind = np.clip(raw_wind, 0.0, 250.0)

        # ---------------------------------------------------------
        # C. Hydro Forecast (hydro_kw)
        # ---------------------------------------------------------
        if step_idx == 0:
            water_flow_lag_1 = float(last_obs["water_flow"])
        else:
            water_flow_lag_1 = float(df_future.iloc[step_idx - 1]["water_flow"])

        hydro_features = pd.DataFrame(
            [
                {
                    "water_flow": float(row_future["water_flow"]),
                    "water_flow_lag_1": water_flow_lag_1,
                    "rainfall": float(row_future["rainfall"]),
                    "month": month,
                    "day_of_year": day_of_year,
                }
            ]
        )[FEATURE_SETS["hydro_kw"]]

        raw_hydro = float(hydro_model.predict(hydro_features)[0])
        pred_hydro = np.clip(raw_hydro, 0.0, 300.0)

        # ---------------------------------------------------------
        # D. Recursive Electricity Demand Forecast (load_kw)
        # ---------------------------------------------------------
        # 1. historical_load_lag_24: Always historical observation (t - 24h)
        lag_24_ts = current_ts - pd.Timedelta(hours=24)
        if lag_24_ts in history_lookup.index:
            load_lag_24 = float(history_lookup.loc[lag_24_ts, "load_kw"])
        else:
            raise ValueError(
                f"Historical load observation missing for required 24-hour lag timestamp: '{lag_24_ts}'."
            )

        # 2. historical_load_lag_1:
        # Step 0 (h=1) uses observed load at T_0; Step > 0 uses previous predicted load!
        if step_idx == 0:
            load_lag_1 = float(last_obs["load_kw"])
        else:
            load_lag_1 = rolling_load_preds[-1]

        # In peak_demand scenario, elevate baseline demand inputs
        if scenario == "peak_demand":
            load_lag_1_adj = load_lag_1 * 1.25
            load_lag_24_adj = load_lag_24 * 1.25
        else:
            load_lag_1_adj = load_lag_1
            load_lag_24_adj = load_lag_24

        load_features = pd.DataFrame(
            [
                {
                    "historical_load_lag_1": load_lag_1_adj,
                    "historical_load_lag_24": load_lag_24_adj,
                    "temperature": float(row_future["temperature"]),
                    "humidity": float(row_future["humidity"]),
                    "hour": hour,
                    "day_of_week": day_of_week,
                    "month": month,
                    "is_weekend": is_weekend,
                }
            ]
        )[FEATURE_SETS["load_kw"]]

        raw_load = float(load_model.predict(load_features)[0])
        if scenario == "peak_demand":
            raw_load = raw_load * 1.15
        pred_load = max(0.0, raw_load)

        # Append to autoregressive memory for next hour
        rolling_load_preds.append(pred_load)

        # Record in output format
        forecast_records.append(
            {
                "timestamp": current_ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "solar_kw": round(float(pred_solar), 1),
                "wind_kw": round(float(pred_wind), 1),
                "hydro_kw": round(float(pred_hydro), 1),
                "load_kw": round(float(pred_load), 1),
            }
        )

    # 6. Assemble Contract JSON Payload
    payload = {
        "location": LOCATION_NAME,
        "forecast_horizon_hours": horizon,
        "forecast": forecast_records,
    }

    # 7. Validate contract schema
    validate_forecast_contract(payload, horizon=horizon)

    # 8. Persist to disk if requested
    if save_output:
        dest_path = Path(output_path) if output_path is not None else DEFAULT_OUTPUT_JSON
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    return payload


def main():
    parser = argparse.ArgumentParser(
        description="GridMate AI Forecasting Inference Engine (Member 1)"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="normal",
        choices=VALID_SCENARIOS,
        help="Scenario identifier (normal, cloudy, heavy_monsoon, high_wind, peak_demand)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=DEFAULT_HORIZON_HOURS,
        help="Forecast horizon in hours (6 to 24, default: 24)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT_JSON),
        help="Path to output forecast.json file",
    )

    args = parser.parse_args()

    print("=" * 65)
    print("  GRIDMATE — AI FORECASTING INFERENCE ENGINE")
    print("=" * 65)
    print(f"  Location:  {LOCATION_NAME}")
    print(f"  Scenario:  {args.scenario}")
    print(f"  Horizon:   {args.horizon} hours")
    print(f"  Output:    {args.output}\n")

    result = generate_forecast(
        input_data=None,
        horizon=args.horizon,
        scenario=args.scenario,
        save_output=True,
        output_path=args.output,
    )

    print(f"[SUCCESS] Forecast generated and validated ({len(result['forecast'])} hourly timesteps).")
    print(f"Saved to: {args.output}\n")

    # Display sample preview
    df_preview = pd.DataFrame(result["forecast"])
    print("=== Forecast Summary (Mean / Min / Max in kW) ===")
    summary = pd.DataFrame(
        {
            "Mean (kW)": df_preview[["solar_kw", "wind_kw", "hydro_kw", "load_kw"]].mean().round(1),
            "Min (kW)": df_preview[["solar_kw", "wind_kw", "hydro_kw", "load_kw"]].min().round(1),
            "Max (kW)": df_preview[["solar_kw", "wind_kw", "hydro_kw", "load_kw"]].max().round(1),
        }
    )
    print(summary.to_string())

    print("\n=== First 3 Forecast Records ===")
    print(df_preview.head(3).to_string(index=False))

    print("\n=== Last 3 Forecast Records ===")
    print(df_preview.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()

