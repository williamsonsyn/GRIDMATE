"""
predict.py
==========
GridMate Version 2 AI Forecasting Inference Engine and Scenario Simulation.

Member 1 Responsibility:
Produces multi-target hourly energy forecasts (solar_kw, wind_kw, hydro_kw, load_kw)
for microgrid dispatch optimization (Member 2), supporting 6 to 24-hour horizons
across baseline and simulated weather/demand scenarios.

Data Provenance & Authenticity Disclaimer:
------------------------------------------
CRITICAL NOTICE:
All targets, historical training/testing datasets, and default future environmental
inputs in this module are AI-generated synthetic demonstration data, calibrated to
illustrative Western Ghats / Lonavala climate characteristics. They do NOT represent
actual physical sensor measurements or utility operational records from Lonavala, Maharashtra.
Outputs are generated strictly for academic and prototype demonstration, and no claim of
real-world accuracy is made. Do not use for live utility operations.

Responsibilities:
1. Load trained XGBoost models from forecasting_real_data/models/:
   - solar_model.joblib
   - wind_model.joblib (baseline) or wind_experiment_model.joblib (cyclical experiment)
   - hydro_model.joblib (hydro_experiment_model.joblib is strictly excluded because the experimental hydro model performed worse on the held-out test set: baseline R² = -0.7383 vs cyclical experiment R² = -4.9384)
   - load_model.joblib
2. Load and validate historical context by combining training_dataset.csv and testing_dataset.csv,
   ensuring strict chronological continuity and at least 24 hours of observations.
3. Provide the primary callable interface:
   generate_forecast(input_data=None, horizon=24, scenario='normal', save_output=True, output_path=None, wind_model='baseline')
4. Support 6 to 24-hour horizons with physical domain validation and non-negative power bounds.
5. Generate deterministic demonstration future weather using 7-day historical hourly medians when input_data is None.
6. Validate external future weather inputs against required schema, physical bounds, and absence of target columns.
7. Support 5 deterministic scenarios: normal, cloudy, heavy_monsoon, high_wind, peak_demand.
8. Implement recursive roll-forward forecasting for load_kw without lookahead data leakage.
9. Enforce strict adherence to Member 2 shared forecast.json contract schema.
10. Provide CLI execution with argument parsing and readable summary output.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
import pandas as pd

# Master contract specifications
LOCATION_NAME = "Lonavala"
MIN_HORIZON_HOURS = 6
MAX_HORIZON_HOURS = 24
DEFAULT_HORIZON_HOURS = 24

VALID_SCENARIOS = [
    "normal",
    "cloudy",
    "heavy_monsoon",
    "high_wind",
    "peak_demand",
]

VALID_WIND_MODELS = [
    "baseline",
    "experiment",
]

REQUIRED_FUTURE_COLS = [
    "timestamp",
    "solar_irradiance",
    "temperature",
    "humidity",
    "pressure",
    "wind_speed",
    "wind_direction",
    "rainfall",
    "cloud_cover",
    "water_flow",
]

FORBIDDEN_TARGET_COLS = [
    "solar_kw",
    "wind_kw",
    "hydro_kw",
    "load_kw",
]

CONTRACT_TOP_KEYS = {"location", "forecast_horizon_hours", "forecast"}
CONTRACT_RECORD_KEYS = {"timestamp", "solar_kw", "wind_kw", "hydro_kw", "load_kw"}

# Directory resolution relative to this file
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent  # forecasting_real_data
REPO_ROOT = BASE_DIR.parent   # repository root
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
DEFAULT_OUTPUT_JSON = BASE_DIR / "outputs" / "forecast.json"

# Exact model feature sets matching Version 2 training pipelines
FEATURE_SETS: Dict[str, List[str]] = {
    "solar": [
        "solar_irradiance",
        "solar_irradiance_lag_1",
        "cloud_cover",
        "temperature",
        "humidity",
        "hour",
        "month",
        "day_of_year",
    ],
    "wind_baseline": [
        "wind_speed",
        "wind_speed_lag_1",
        "wind_direction",
        "pressure",
        "temperature",
        "hour",
        "month",
    ],
    "wind_experiment": [
        "wind_speed",
        "wind_speed_lag_1",
        "wind_direction_sin",
        "wind_direction_cos",
        "pressure",
        "temperature",
        "hour_sin",
        "hour_cos",
        "month_sin",
        "month_cos",
    ],
    "hydro": [
        "water_flow",
        "water_flow_lag_1",
        "rainfall",
        "month",
        "day_of_year",
    ],
    "load": [
        "historical_load_lag_1",
        "historical_load_lag_24",
        "temperature",
        "humidity",
        "hour",
        "day_of_week",
        "month",
        "is_weekend",
    ],
}

# Cache for loaded model artifacts to prevent repeated disk I/O
_LOADED_MODELS: Dict[str, Any] = {}


def load_trained_models(wind_model: str = "baseline") -> Dict[str, Any]:
    """
    Load and cache trained XGBoost model artifacts from forecasting_real_data/models/.

    Models:
    - solar: solar_model.joblib
    - wind: wind_model.joblib (baseline) or wind_experiment_model.joblib (experiment)
    - hydro: hydro_model.joblib (NOTE: hydro_experiment_model.joblib is strictly excluded
             because the experimental hydro model performed worse on the held-out test set:
             baseline R^2 = -0.7383 vs cyclical experiment R^2 = -4.9384)
    - load: load_model.joblib

    Args:
        wind_model: 'baseline' (raw features) or 'experiment' (cyclical features).

    Returns:
        Dict[str, Any]: Mapping of model identifiers to loaded model instances.
    """
    if wind_model not in VALID_WIND_MODELS:
        raise ValueError(
            f"Invalid wind_model '{wind_model}'. Allowed options: {VALID_WIND_MODELS}"
        )

    cache_key = f"v2_models_{wind_model}"
    if cache_key not in _LOADED_MODELS:
        solar_path = MODELS_DIR / "solar_model.joblib"
        hydro_path = MODELS_DIR / "hydro_model.joblib"
        load_path = MODELS_DIR / "load_model.joblib"

        if wind_model == "baseline":
            wind_path = MODELS_DIR / "wind_model.joblib"
        else:
            wind_path = MODELS_DIR / "wind_experiment_model.joblib"

        model_paths = {
            "solar": solar_path,
            "wind": wind_path,
            "hydro": hydro_path,
            "load": load_path,
        }

        for target_name, path in model_paths.items():
            if not path.exists():
                raise FileNotFoundError(
                    f"Trained model artifact for '{target_name}' not found at: {path}. "
                    "Ensure models have been trained and saved to forecasting_real_data/models/."
                )

        _LOADED_MODELS[cache_key] = {
            "solar": joblib.load(solar_path),
            "wind": joblib.load(wind_path),
            "hydro": joblib.load(hydro_path),
            "load": joblib.load(load_path),
        }

    return _LOADED_MODELS[cache_key]


def load_historical_context() -> pd.DataFrame:
    """
    Load combined historical observations by concatenating training_dataset.csv
    and testing_dataset.csv from forecasting_real_data/data/.

    Validates:
    - Chronological sorting and hourly continuity.
    - No duplicate timestamps.
    - At least 24 historical rows for lag feature population.

    Returns:
        pd.DataFrame: Continuous historical dataset sorted chronologically.
    """
    train_path = DATA_DIR / "training_dataset.csv"
    test_path = DATA_DIR / "testing_dataset.csv"

    if not train_path.exists():
        raise FileNotFoundError(f"Historical training data not found at: {train_path}")
    if not test_path.exists():
        raise FileNotFoundError(f"Historical testing data not found at: {test_path}")

    df_train = pd.read_csv(train_path)
    df_test = pd.read_csv(test_path)

    df_combined = pd.concat([df_train, df_test], ignore_index=True)
    df_combined["timestamp"] = pd.to_datetime(df_combined["timestamp"])
    df_combined = df_combined.sort_values("timestamp").reset_index(drop=True)

    # Validate duplicate timestamps
    if df_combined["timestamp"].duplicated().any():
        dups = int(df_combined["timestamp"].duplicated().sum())
        raise ValueError(
            f"Combined historical dataset contains {dups} duplicate timestamp(s)."
        )

    # Validate hourly continuity
    if len(df_combined) > 1:
        diffs = df_combined["timestamp"].diff().iloc[1:]
        if not (diffs == pd.Timedelta(hours=1)).all():
            raise ValueError(
                "Combined historical dataset contains gaps in hourly continuity."
            )

    # Validate minimum historical length (at least 24 hours required for lag features)
    if len(df_combined) < 24:
        raise ValueError(
            f"Insufficient historical data: at least 24 hours of observations are required "
            f"to populate lag features, but received only {len(df_combined)} rows."
        )

    return df_combined


def apply_scenario_modifications(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """
    Apply deterministic scenario modifications to future environmental inputs.
    Does not modify the input DataFrame in-place.

    Scenarios:
    - 'normal': Baseline conditions unchanged.
    - 'cloudy': Cloud cover increases, reducing solar irradiance by ~75%.
    - 'heavy_monsoon': High rainfall (18.5 mm), dense cloud cover, solar down by ~90%,
      water flow surges to 85.0 m³/s, high humidity (96%), cooling temp to 21°C.
    - 'high_wind': Sustained high wind speed (12.8 m/s, prevailing direction 245°).
    - 'peak_demand': Higher ambient temperature (+4.5°C) and humidity (+10%).

    Args:
        df: Future environmental inputs DataFrame.
        scenario: Scenario identifier.

    Returns:
        pd.DataFrame: Modified environmental inputs DataFrame.
    """
    df_mod = df.copy()

    if scenario == "normal":
        pass

    elif scenario == "cloudy":
        # Handle both percentage (0-100) and fraction (0-1) scale seamlessly
        if (df_mod["cloud_cover"] <= 1.0).all():
            df_mod["cloud_cover"] = np.clip(df_mod["cloud_cover"] + 0.65, 0.0, 0.95)
        else:
            df_mod["cloud_cover"] = np.clip(df_mod["cloud_cover"] + 65.0, 0.0, 95.0)
        df_mod["solar_irradiance"] = np.round(df_mod["solar_irradiance"] * 0.25, 2)
        df_mod["temperature"] = np.round(df_mod["temperature"] - 2.5, 2)

    elif scenario == "heavy_monsoon":
        if (df_mod["cloud_cover"] <= 1.0).all():
            df_mod["cloud_cover"] = 0.95
        else:
            df_mod["cloud_cover"] = 95.0
        df_mod["solar_irradiance"] = np.round(df_mod["solar_irradiance"] * 0.10, 2)
        df_mod["rainfall"] = 18.50
        df_mod["water_flow"] = 85.00
        df_mod["humidity"] = 96.0
        df_mod["temperature"] = 21.0

    elif scenario == "high_wind":
        df_mod["wind_speed"] = 12.80
        df_mod["wind_direction"] = 245.0

    elif scenario == "peak_demand":
        df_mod["temperature"] = np.round(df_mod["temperature"] + 4.5, 2)
        df_mod["humidity"] = np.round(np.clip(df_mod["humidity"] + 10.0, 0.0, 100.0), 1)

    # Ensure all scenario modifications strictly satisfy physical domain bounds:
    # humidity: [0, 100], cloud_cover: [0, 100], wind_direction: [0, 360], pressure: > 0,
    # non-negative: solar_irradiance >= 0, wind_speed >= 0, rainfall >= 0, water_flow >= 0
    df_mod["humidity"] = np.clip(df_mod["humidity"], 0.0, 100.0)
    df_mod["cloud_cover"] = np.clip(df_mod["cloud_cover"], 0.0, 100.0)
    df_mod["wind_direction"] = np.clip(df_mod["wind_direction"], 0.0, 360.0)
    df_mod["pressure"] = np.maximum(df_mod["pressure"], 0.1)
    df_mod["solar_irradiance"] = np.clip(df_mod["solar_irradiance"], 0.0, None)
    df_mod["wind_speed"] = np.clip(df_mod["wind_speed"], 0.0, None)
    df_mod["rainfall"] = np.clip(df_mod["rainfall"], 0.0, None)
    df_mod["water_flow"] = np.clip(df_mod["water_flow"], 0.0, None)

    return df_mod


def generate_demonstration_weather(
    df_history: pd.DataFrame,
    start_ts: pd.Timestamp,
    horizon: int = 24,
    scenario: str = "normal",
) -> pd.DataFrame:
    """
    Generate deterministic demonstration future weather inputs for the requested horizon
    using the median of the latest seven days (168 hours) in history for the matching hour
    of the day, with a fallback to the latest observed values.

    DISCLAIMER:
    These inputs are AI-generated synthetic demonstration values for prototype benchmarking;
    they do NOT represent real-world meteorological forecasts for Lonavala.

    Args:
        df_history: Historical observations DataFrame.
        start_ts: Starting timestamp for the forecast (T_0 + 1 hour).
        horizon: Forecast horizon length in hours.
        scenario: Selected scenario identifier.

    Returns:
        pd.DataFrame: Future environmental inputs.
    """
    weather_numeric_cols = [c for c in REQUIRED_FUTURE_COLS if c != "timestamp"]

    # Use the latest 168 hours (7 days) for hourly medians
    recent_history = df_history.tail(168).copy()
    recent_history["_hour"] = recent_history["timestamp"].dt.hour
    hourly_medians = recent_history.groupby("_hour")[weather_numeric_cols].median()

    last_obs = df_history.iloc[-1]

    rows: List[Dict[str, Any]] = []
    for step_idx in range(horizon):
        step_ts = start_ts + pd.Timedelta(hours=step_idx)
        h = int(step_ts.hour)
        if h in hourly_medians.index:
            row_dict = hourly_medians.loc[h].to_dict()
        else:
            row_dict = {col: float(last_obs[col]) for col in weather_numeric_cols}

        # Apply standard numerical roundings and non-negativity clamps
        row_dict["timestamp"] = step_ts
        row_dict["solar_irradiance"] = round(float(np.clip(row_dict["solar_irradiance"], 0.0, None)), 2)
        row_dict["temperature"] = round(float(row_dict["temperature"]), 2)
        row_dict["humidity"] = round(float(np.clip(row_dict["humidity"], 0.0, 100.0)), 1)
        row_dict["pressure"] = round(float(max(0.1, row_dict["pressure"])), 1)
        row_dict["wind_speed"] = round(float(np.clip(row_dict["wind_speed"], 0.0, None)), 2)
        row_dict["wind_direction"] = round(float(np.clip(row_dict["wind_direction"] % 360.0, 0.0, 360.0)), 1)
        row_dict["rainfall"] = round(float(np.clip(row_dict["rainfall"], 0.0, None)), 2)
        row_dict["cloud_cover"] = round(float(np.clip(row_dict["cloud_cover"], 0.0, 100.0)), 1)
        row_dict["water_flow"] = round(float(np.clip(row_dict["water_flow"], 0.0, None)), 2)
        rows.append(row_dict)

    df_future = pd.DataFrame(rows)[REQUIRED_FUTURE_COLS]

    # Apply scenario perturbations if requested
    if scenario != "normal":
        df_future = apply_scenario_modifications(df_future, scenario)

    return df_future


def validate_future_inputs(
    df: pd.DataFrame,
    horizon: int,
    origin_ts: pd.Timestamp,
    allow_arbitrary_dates: bool = False,
) -> None:
    """
    Validate user-provided future weather input DataFrame.

    Checks:
    1. Exactly horizon rows.
    2. All required environmental columns present.
    3. No target columns present (prevents lookahead data leakage).
    4. Continuous hourly timestamps immediately following origin_ts.
    5. Finite numeric values and physical domain bounds:
       - humidity between 0 and 100 inclusive
       - cloud_cover between 0 and 100 inclusive
       - wind_direction between 0 and 360 inclusive
       - pressure strictly greater than zero
       - solar_irradiance, wind_speed, rainfall, water_flow: non-negative (>= 0)

    Args:
        df: User-supplied future input DataFrame.
        horizon: Required forecast horizon.
        origin_ts: Last observed historical timestamp.
    """
    if len(df) != horizon:
        raise ValueError(
            f"Input data length mismatch: expected exactly {horizon} rows, but received {len(df)} rows."
        )

    # Check required columns
    missing_cols = [c for c in REQUIRED_FUTURE_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Input data missing required column(s): {missing_cols}")

    # Check no target columns to prevent lookahead data leakage
    found_targets = [c for c in FORBIDDEN_TARGET_COLS if c in df.columns]
    if found_targets:
        raise ValueError(
            f"Target column(s) detected in future inputs: {found_targets}. "
            "Target columns must not be supplied in inference inputs to prevent data leakage."
        )

    # Check timestamps
    ts = pd.to_datetime(df["timestamp"])
    if ts.isnull().any():
        raise ValueError("Input data contains missing or null timestamp(s).")
    if ts.duplicated().any():
        raise ValueError("Input data contains duplicate timestamps.")

    expected_first_ts = origin_ts + pd.Timedelta(hours=1)
    if not allow_arbitrary_dates and ts.iloc[0] != expected_first_ts:
        raise ValueError(
            f"Input data timestamps must immediately follow the last historical timestamp ({origin_ts}). "
            f"Expected first timestamp: {expected_first_ts}, received: {ts.iloc[0]}."
        )

    if len(ts) > 1:
        diffs = ts.diff().iloc[1:]
        if not (diffs == pd.Timedelta(hours=1)).all():
            raise ValueError("Input data timestamps must be continuous hourly observations.")

    # Numerical checks
    weather_numeric_cols = [c for c in REQUIRED_FUTURE_COLS if c != "timestamp"]
    for col in weather_numeric_cols:
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Input data column '{col}' must be numeric.")
        if df[col].isnull().any():
            raise ValueError(f"Input data column '{col}' contains NaN values.")
        if not np.isfinite(df[col].to_numpy()).all():
            raise ValueError(f"Input data column '{col}' contains infinite values.")

    # Physical domain bound checks:
    # 1. humidity between 0 and 100 inclusive
    if (df["humidity"] < 0.0).any() or (df["humidity"] > 100.0).any():
        invalid_count = int(((df["humidity"] < 0.0) | (df["humidity"] > 100.0)).sum())
        raise ValueError(
            f"Input data column 'humidity' contains {invalid_count} value(s) outside physical range [0, 100]."
        )

    # 2. cloud_cover between 0 and 100 inclusive
    if (df["cloud_cover"] < 0.0).any() or (df["cloud_cover"] > 100.0).any():
        invalid_count = int(((df["cloud_cover"] < 0.0) | (df["cloud_cover"] > 100.0)).sum())
        raise ValueError(
            f"Input data column 'cloud_cover' contains {invalid_count} value(s) outside physical range [0, 100]."
        )

    # 3. wind_direction between 0 and 360 inclusive
    if (df["wind_direction"] < 0.0).any() or (df["wind_direction"] > 360.0).any():
        invalid_count = int(((df["wind_direction"] < 0.0) | (df["wind_direction"] > 360.0)).sum())
        raise ValueError(
            f"Input data column 'wind_direction' contains {invalid_count} value(s) outside physical range [0, 360]."
        )

    # 4. pressure strictly greater than zero
    if (df["pressure"] <= 0.0).any():
        invalid_count = int((df["pressure"] <= 0.0).sum())
        raise ValueError(
            f"Input data column 'pressure' contains {invalid_count} non-positive value(s); pressure must be strictly greater than zero."
        )

    # 5. Non-negative checks for physically non-negative variables
    non_negative_cols = [
        "solar_irradiance",
        "wind_speed",
        "rainfall",
        "water_flow",
    ]
    for col in non_negative_cols:
        if (df[col] < 0.0).any():
            neg_count = int((df[col] < 0.0).sum())
            raise ValueError(
                f"Input data column '{col}' contains {neg_count} negative value(s)."
            )


def validate_forecast_contract(payload: Dict[str, Any], horizon: int = 24) -> None:
    """
    Enforce strict validation of the shared forecast.json contract schema.

    Schema:
    {
      "location": "Lonavala",
      "forecast_horizon_hours": 24,
      "forecast": [
        {
          "timestamp": "ISO-8601",
          "solar_kw": float >= 0,
          "wind_kw": float >= 0,
          "hydro_kw": float >= 0,
          "load_kw": float >= 0
        }
      ]
    }

    Args:
        payload: Forecast dictionary payload.
        horizon: Expected horizon length.
    """
    actual_top_keys = set(payload.keys())
    if actual_top_keys != CONTRACT_TOP_KEYS:
        missing = CONTRACT_TOP_KEYS - actual_top_keys
        extra = actual_top_keys - CONTRACT_TOP_KEYS
        raise ValueError(
            f"forecast.json contract violation: expected top keys {CONTRACT_TOP_KEYS}, "
            f"found missing={missing}, extra={extra}"
        )

    if payload["location"] != LOCATION_NAME:
        raise ValueError(
            f"forecast.json location violation: expected '{LOCATION_NAME}', got '{payload['location']}'"
        )

    if payload["forecast_horizon_hours"] != horizon:
        raise ValueError(
            f"forecast.json horizon violation: expected {horizon}, got {payload['forecast_horizon_hours']}"
        )

    records = payload["forecast"]
    if not isinstance(records, list):
        raise ValueError("forecast.json violation: 'forecast' field must be a list of records.")

    if len(records) != horizon:
        raise ValueError(
            f"forecast.json violation: expected {horizon} forecast records, got {len(records)}"
        )

    for idx, rec in enumerate(records):
        rec_keys = set(rec.keys())
        if rec_keys != CONTRACT_RECORD_KEYS:
            missing = CONTRACT_RECORD_KEYS - rec_keys
            extra = rec_keys - CONTRACT_RECORD_KEYS
            raise ValueError(
                f"forecast.json record #{idx} schema violation: missing={missing}, extra={extra}"
            )

        # Validate timestamp parseability
        try:
            datetime.fromisoformat(rec["timestamp"])
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"forecast.json record #{idx} has invalid ISO-8601 timestamp: '{rec['timestamp']}'"
            ) from exc

        # Validate finite non-negative power values
        for target in ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]:
            val = rec[target]
            if not isinstance(val, (int, float)) or np.isnan(val) or np.isinf(val):
                raise ValueError(
                    f"forecast.json record #{idx} target '{target}' has non-finite value: {val}"
                )
            if val < 0.0:
                raise ValueError(
                    f"forecast.json record #{idx} target '{target}' has negative value: {val}"
                )


def generate_forecast(
    input_data: Optional[pd.DataFrame] = None,
    horizon: int = DEFAULT_HORIZON_HOURS,
    scenario: str = "normal",
    save_output: bool = True,
    output_path: Optional[Union[str, Path]] = None,
    wind_model: str = "baseline",
    allow_arbitrary_dates: bool = False,
) -> Dict[str, Any]:
    """
    Generate 6 to 24-hour ahead multi-target energy forecasts for Lonavala.

    Args:
        input_data: Optional DataFrame containing future environmental inputs for the horizon.
                    If None, reproducible demonstration inputs are generated based on the
                    7-day historical hourly medians.
        horizon: Forecast horizon length in hours (6 to 24, default: 24).
        scenario: Selected scenario ID ('normal', 'cloudy', 'heavy_monsoon', 'high_wind', 'peak_demand').
        save_output: Whether to persist results to JSON file on disk.
        output_path: Destination path for forecast.json (default: forecasting_real_data/outputs/forecast.json).
        wind_model: Wind model variant: 'baseline' (raw features) or 'experiment' (cyclical sin/cos features).

    Returns:
        Dict[str, Any]: Forecast dictionary adhering strictly to the shared contract:
                        {
                            "location": "Lonavala",
                            "forecast_horizon_hours": horizon,
                            "forecast": [
                                {
                                    "timestamp": "ISO-8601",
                                    "solar_kw": float >= 0,
                                    "wind_kw": float >= 0,
                                    "hydro_kw": float >= 0,
                                    "load_kw": float >= 0,
                                },
                                ...
                            ]
                        }
    """
    # 1. Parameter validation
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < MIN_HORIZON_HOURS or horizon > MAX_HORIZON_HOURS:
        raise ValueError(
            f"Forecast horizon must be an integer between {MIN_HORIZON_HOURS} and {MAX_HORIZON_HOURS} hours (got {horizon})."
        )
    if scenario not in VALID_SCENARIOS:
        raise ValueError(
            f"Unrecognized scenario '{scenario}'. Allowed scenarios: {VALID_SCENARIOS}"
        )
    if wind_model not in VALID_WIND_MODELS:
        raise ValueError(
            f"Unrecognized wind_model '{wind_model}'. Allowed options: {VALID_WIND_MODELS}"
        )

    # 2. Load historical context for lag generation
    df_history = load_historical_context()
    origin_ts = df_history["timestamp"].iloc[-1]
    start_forecast_ts = origin_ts + pd.Timedelta(hours=1)
    history_lookup = df_history.set_index("timestamp")
    last_obs = df_history.iloc[-1]

    # 3. Prepare future environmental inputs
    if input_data is None:
        print(
            "[NOTE] Future weather inputs generated using 7-day historical median.\n"
            "       DISCLAIMER: These are AI-generated synthetic demonstration inputs for\n"
            "       prototype benchmarking, NOT actual measured Lonavala weather forecasts."
        )
        df_future = generate_demonstration_weather(
            df_history=df_history,
            start_ts=start_forecast_ts,
            horizon=horizon,
            scenario=scenario,
        )
    else:
        validate_future_inputs(
            input_data, horizon=horizon, origin_ts=origin_ts, allow_arbitrary_dates=allow_arbitrary_dates
        )
        df_future = input_data.copy().sort_values("timestamp").reset_index(drop=True)
        if scenario != "normal":
            df_future = apply_scenario_modifications(df_future, scenario)

    # 4. Load trained models
    models = load_trained_models(wind_model=wind_model)
    solar_model = models["solar"]
    wind_model_inst = models["wind"]
    hydro_model = models["hydro"]
    load_model = models["load"]

    forecast_records: List[Dict[str, Any]] = []
    rolling_load_preds: List[float] = []

    # 5. Recursive multi-step prediction loop
    for step_idx in range(horizon):
        row_future = df_future.iloc[step_idx]
        current_ts = pd.to_datetime(row_future["timestamp"])

        hour = int(current_ts.hour)
        month = int(current_ts.month)
        day_of_week = int(current_ts.day_of_week)
        day_of_year = int(current_ts.day_of_year)
        is_weekend = bool(day_of_week >= 5)

        # -------------------------------------------------------------
        # A. Solar Model (solar_kw)
        # -------------------------------------------------------------
        if step_idx == 0:
            solar_irradiance_lag_1 = float(last_obs["solar_irradiance"]) if not allow_arbitrary_dates else float(row_future["solar_irradiance"])
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
        )[FEATURE_SETS["solar"]]

        # Physical solar clipping: 0 at night or under negligible irradiance
        if float(row_future["solar_irradiance"]) <= 1.0 or hour < 6 or hour > 18:
            pred_solar = 0.0
        else:
            raw_solar = float(solar_model.predict(solar_features)[0])
            pred_solar = max(0.0, raw_solar)

        # -------------------------------------------------------------
        # B. Wind Model (wind_kw)
        # -------------------------------------------------------------
        if step_idx == 0:
            wind_speed_lag_1 = float(last_obs["wind_speed"]) if not allow_arbitrary_dates else float(row_future["wind_speed"])
        else:
            wind_speed_lag_1 = float(df_future.iloc[step_idx - 1]["wind_speed"])

        if wind_model == "baseline":
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
            )[FEATURE_SETS["wind_baseline"]]
        else:
            # Cyclical sin/cos transformations matching train_experiments.py
            wd_rad = np.radians(float(row_future["wind_direction"]))
            wind_direction_sin = float(np.sin(wd_rad))
            wind_direction_cos = float(np.cos(wd_rad))
            hour_sin = float(np.sin(2.0 * np.pi * hour / 24.0))
            hour_cos = float(np.cos(2.0 * np.pi * hour / 24.0))
            month_sin = float(np.sin(2.0 * np.pi * month / 12.0))
            month_cos = float(np.cos(2.0 * np.pi * month / 12.0))

            wind_features = pd.DataFrame(
                [
                    {
                        "wind_speed": float(row_future["wind_speed"]),
                        "wind_speed_lag_1": wind_speed_lag_1,
                        "wind_direction_sin": wind_direction_sin,
                        "wind_direction_cos": wind_direction_cos,
                        "pressure": float(row_future["pressure"]),
                        "temperature": float(row_future["temperature"]),
                        "hour_sin": hour_sin,
                        "hour_cos": hour_cos,
                        "month_sin": month_sin,
                        "month_cos": month_cos,
                    }
                ]
            )[FEATURE_SETS["wind_experiment"]]

        ws = float(row_future["wind_speed"])
        # Physical turbine operating envelope (cut-in: 3.0 m/s, cut-out: 25.0 m/s)
        if ws < 3.0 or ws >= 25.0:
            pred_wind = 0.0
        else:
            raw_wind = float(wind_model_inst.predict(wind_features)[0])
            pred_wind = max(0.0, raw_wind)

        # -------------------------------------------------------------
        # C. Hydro Model (hydro_kw)
        # Note: hydro_model.joblib is used; hydro_experiment_model.joblib is excluded
        # because the experimental hydro model performed worse on the held-out test set
        # (baseline R^2 = -0.7383 vs cyclical experiment R^2 = -4.9384).
        # -------------------------------------------------------------
        if step_idx == 0:
            water_flow_lag_1 = float(last_obs["water_flow"]) if not allow_arbitrary_dates else float(row_future["water_flow"])
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
        )[FEATURE_SETS["hydro"]]

        raw_hydro = float(hydro_model.predict(hydro_features)[0])
        pred_hydro = max(0.0, raw_hydro)

        # -------------------------------------------------------------
        # D. Recursive Load Model (load_kw)
        # -------------------------------------------------------------
        # 1. historical_load_lag_24:
        lag_24_ts = current_ts - pd.Timedelta(hours=24)
        if lag_24_ts <= origin_ts:
            if lag_24_ts in history_lookup.index:
                load_lag_24 = float(history_lookup.loc[lag_24_ts, "load_kw"])
            elif allow_arbitrary_dates:
                matching_h = df_history[df_history["hour"] == hour]
                load_lag_24 = float(matching_h["load_kw"].median() if len(matching_h) > 0 else 600.0)
            else:
                raise ValueError(
                    f"Historical load observation missing for required 24-hour lag timestamp: '{lag_24_ts}'."
                )
        else:
            # When lag timestamp refers to an earlier forecast step
            prior_step_idx = int((lag_24_ts - start_forecast_ts) / pd.Timedelta(hours=1))
            if 0 <= prior_step_idx < len(rolling_load_preds):
                load_lag_24 = float(rolling_load_preds[prior_step_idx])
            elif allow_arbitrary_dates:
                matching_h = df_history[df_history["hour"] == hour]
                load_lag_24 = float(matching_h["load_kw"].median() if len(matching_h) > 0 else 600.0)
            else:
                raise ValueError(
                    f"Predicted load missing for required 24-hour lag timestamp: '{lag_24_ts}'."
                )

        # 2. historical_load_lag_1:
        if step_idx == 0:
            if not allow_arbitrary_dates:
                load_lag_1 = float(last_obs["load_kw"])
            else:
                prev_h = (hour - 1) % 24
                matching_prev = df_history[df_history["hour"] == prev_h]
                load_lag_1 = float(matching_prev["load_kw"].median() if len(matching_prev) > 0 else 600.0)
        else:
            load_lag_1 = float(rolling_load_preds[-1])

        # Pass unmodified historical/predicted values to the load model to avoid repeated compounding
        load_features = pd.DataFrame(
            [
                {
                    "historical_load_lag_1": load_lag_1,
                    "historical_load_lag_24": load_lag_24,
                    "temperature": float(row_future["temperature"]),
                    "humidity": float(row_future["humidity"]),
                    "hour": hour,
                    "day_of_week": day_of_week,
                    "month": month,
                    "is_weekend": is_weekend,
                }
            ]
        )[FEATURE_SETS["load"]]

        raw_load = float(load_model.predict(load_features)[0])
        # Apply 25% uplift factor exactly once to current raw prediction in peak_demand
        if scenario == "peak_demand":
            raw_load = raw_load * 1.25
        pred_load = max(0.0, raw_load)

        # Append to autoregressive memory for subsequent forecast hours
        rolling_load_preds.append(pred_load)

        forecast_records.append(
            {
                "timestamp": current_ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "solar_kw": round(float(pred_solar), 2),
                "wind_kw": round(float(pred_wind), 2),
                "hydro_kw": round(float(pred_hydro), 2),
                "load_kw": round(float(pred_load), 2),
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


def generate_forecast_dataframe(
    input_data: Optional[pd.DataFrame] = None,
    horizon: int = DEFAULT_HORIZON_HOURS,
    scenario: str = "normal",
    save_output: bool = True,
    output_path: Optional[Union[str, Path]] = None,
    wind_model: str = "baseline",
) -> pd.DataFrame:
    """
    Convenience wrapper returning predictions as a pandas DataFrame.

    Args:
        input_data: Optional future inputs DataFrame.
        horizon: Forecast horizon (6 to 24).
        scenario: Scenario identifier.
        save_output: Whether to persist JSON to disk.
        output_path: Destination path for JSON.
        wind_model: 'baseline' or 'experiment'.

    Returns:
        pd.DataFrame: Table of forecasts with columns [timestamp, solar_kw, wind_kw, hydro_kw, load_kw].
    """
    result = generate_forecast(
        input_data=input_data,
        horizon=horizon,
        scenario=scenario,
        save_output=save_output,
        output_path=output_path,
        wind_model=wind_model,
    )
    df = pd.DataFrame(result["forecast"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GridMate Version 2 AI Forecasting Inference Engine (Member 1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Provenance & Authenticity Disclaimer:\n"
            "  This system uses AI-generated synthetic demonstration data and models.\n"
            "  It does NOT use live meteorological sensors or measured Lonavala utility records.\n"
            "  Outputs are for academic / prototype benchmarking only and must not be used for\n"
            "  real-world grid operations or life-critical utility management."
        ),
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="normal",
        choices=VALID_SCENARIOS,
        help="Simulation scenario (normal, cloudy, heavy_monsoon, high_wind, peak_demand). Default: normal.",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=DEFAULT_HORIZON_HOURS,
        help="Forecast horizon in hours (6 to 24). Default: 24.",
    )
    parser.add_argument(
        "--wind-model",
        type=str,
        default="baseline",
        choices=VALID_WIND_MODELS,
        help="Wind model selection: 'baseline' (raw features) or 'experiment' (cyclical sin/cos features). Default: baseline.",
    )
    parser.add_argument(
        "--future-weather",
        type=str,
        default=None,
        help="Optional path to a custom future weather CSV file containing hourly horizon inputs.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT_JSON),
        help="Path to output forecast.json file. Default: forecasting_real_data/outputs/forecast.json.",
    )

    args = parser.parse_args()

    custom_inputs = None
    if args.future_weather:
        fw_path = Path(args.future_weather)
        if not fw_path.is_absolute():
            fw_path = (REPO_ROOT / fw_path).resolve()
        if not fw_path.exists():
            print(f"[ERROR] Custom future weather file not found at: {fw_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Loading custom future weather inputs from: {fw_path}")
        custom_inputs = pd.read_csv(fw_path)

    print("=" * 70)
    print("  GRIDMATE VERSION 2 — AI FORECASTING INFERENCE ENGINE")
    print("=" * 70)
    print(f"  Location:     {LOCATION_NAME}")
    print(f"  Scenario:     {args.scenario}")
    print(f"  Horizon:      {args.horizon} hours")
    print(f"  Wind Model:   {args.wind_model}")
    print(f"  Output JSON:  {args.output}\n")

    try:
        result = generate_forecast(
            input_data=custom_inputs,
            horizon=args.horizon,
            scenario=args.scenario,
            save_output=True,
            output_path=args.output,
            wind_model=args.wind_model,
        )
    except Exception as exc:
        print(f"[ERROR] Forecast generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[SUCCESS] Forecast successfully generated and validated ({len(result['forecast'])} hourly timesteps).")
    print(f"Saved to: {args.output}\n")

    df_preview = pd.DataFrame(result["forecast"])
    print("=== Forecast Summary (Mean / Min / Max in kW) ===")
    summary = pd.DataFrame(
        {
            "Mean (kW)": df_preview[["solar_kw", "wind_kw", "hydro_kw", "load_kw"]].mean().round(2),
            "Min (kW)": df_preview[["solar_kw", "wind_kw", "hydro_kw", "load_kw"]].min().round(2),
            "Max (kW)": df_preview[["solar_kw", "wind_kw", "hydro_kw", "load_kw"]].max().round(2),
        }
    )
    print(summary.to_string())

    print("\n=== First 3 Forecast Records ===")
    print(df_preview.head(3).to_string(index=False))

    print("\n=== Last 3 Forecast Records ===")
    print(df_preview.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
