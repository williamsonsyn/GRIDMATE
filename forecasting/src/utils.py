"""
utils.py
========
Utilities, scenario definitions, and contract validators for GridMate AI Forecasting.

Responsibilities:
1. Define and manage the five required weather/demand scenarios:
   - normal
   - cloudy
   - heavy_monsoon
   - high_wind
   - peak_demand
2. Generate synthetic future weather and environmental inputs when user inputs are not supplied.
3. Validate user-provided future inputs against required schema and physical domain bounds.
4. Enforce strict validation of the shared forecast.json contract schema.
"""

from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forecasting.src.preprocessing import NUMERICAL_BOUNDS

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

REQUIRED_FUTURE_INPUT_COLUMNS = [
    "timestamp",
    "temperature",
    "humidity",
    "solar_irradiance",
    "cloud_cover",
    "wind_speed",
    "wind_direction",
    "rainfall",
    "pressure",
    "water_flow",
]

CONTRACT_FORECAST_KEYS = [
    "timestamp",
    "solar_kw",
    "wind_kw",
    "hydro_kw",
    "load_kw",
]


def generate_future_weather_inputs(
    start_timestamp: pd.Timestamp,
    horizon: int = DEFAULT_HORIZON_HOURS,
    scenario: str = "normal",
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate reproducible synthetic future weather and environmental inputs
    for the requested forecast horizon.

    DISCLAIMER:
    These are illustrative synthetic demonstration inputs for prototype benchmarking
    and do NOT represent real-world meteorological forecasts for Lonavala.

    Args:
        start_timestamp: Timestamp of the first forecast step (T_0 + 1 hour).
        horizon: Forecast horizon length in hours (6 to 24).
        scenario: One of ['normal', 'cloudy', 'heavy_monsoon', 'high_wind', 'peak_demand'].
        seed: Random seed for deterministic reproducibility.

    Returns:
        pd.DataFrame: Table of future environmental inputs for each horizon step.
    """
    if horizon < MIN_HORIZON_HOURS or horizon > MAX_HORIZON_HOURS:
        raise ValueError(
            f"Forecast horizon must be between {MIN_HORIZON_HOURS} and {MAX_HORIZON_HOURS} hours (got {horizon})."
        )
    if scenario not in VALID_SCENARIOS:
        raise ValueError(
            f"Unrecognized scenario '{scenario}'. Allowed scenarios: {VALID_SCENARIOS}"
        )

    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(start=start_timestamp, periods=horizon, freq="h")

    hour = timestamps.hour.to_numpy()
    day_of_year = timestamps.day_of_year.to_numpy()

    # 1. Base October diurnal profile (early dry season in Western Ghats)
    # Solar profile (0 at night, peak ~850 W/m² at solar noon)
    solar_angle = np.maximum(0.0, np.sin(np.pi * (hour - 6) / 12.0))
    solar_angle[hour < 6] = 0.0
    solar_angle[hour > 18] = 0.0

    cloud_cover = np.full(horizon, 0.18) + rng.normal(0, 0.02, size=horizon)
    cloud_cover = np.clip(cloud_cover, 0.0, 1.0)

    solar_irradiance = np.where(
        solar_angle > 0,
        850.0 * solar_angle * (1.0 - 0.75 * (cloud_cover ** 1.3)),
        0.0,
    )

    temperature = 22.0 + 6.0 * np.sin(2 * np.pi * (hour - 8) / 24.0) + rng.normal(0, 0.5, size=horizon)
    humidity = 65.0 - 1.2 * (temperature - 22.0) + rng.normal(0, 1.5, size=horizon)
    wind_speed = np.full(horizon, 4.2) + 0.8 * np.sin(2 * np.pi * (hour - 12) / 24.0) + rng.normal(0, 0.3, size=horizon)
    wind_speed = np.clip(wind_speed, 1.0, 15.0)
    wind_direction = np.full(horizon, 85.0) + rng.normal(0, 5.0, size=horizon)
    rainfall = np.zeros(horizon)
    pressure = np.full(horizon, 942.5) + rng.normal(0, 0.4, size=horizon)
    water_flow = np.full(horizon, 18.5) + rng.normal(0, 0.3, size=horizon)

    df_future = pd.DataFrame(
        {
            "timestamp": timestamps,
            "temperature": np.round(temperature, 2),
            "humidity": np.round(np.clip(humidity, 20.0, 100.0), 1),
            "solar_irradiance": np.round(solar_irradiance, 2),
            "cloud_cover": np.round(cloud_cover, 3),
            "wind_speed": np.round(wind_speed, 2),
            "wind_direction": np.round(wind_direction % 360.0, 1),
            "rainfall": np.round(rainfall, 2),
            "pressure": np.round(pressure, 1),
            "water_flow": np.round(water_flow, 2),
        }
    )

    # 2. Apply deterministic scenario perturbations
    df_future = apply_scenario_modifications(df_future, scenario)
    return df_future


def apply_scenario_modifications(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    """
    Apply deterministic meteorological/demand modifications for the selected scenario.

    Scenario Logic:
    - 'normal': Baseline conditions.
    - 'cloudy': Cloud cover increases to ~0.88, reducing solar irradiance by ~75%.
    - 'heavy_monsoon': High rainfall (18 mm/hr), dense clouds (0.95), irradiance down by ~90%,
      water flow surges to 85 m³/s (driving hydro up).
    - 'high_wind': Sustained high wind speed (~12.8 m/s, above rated ~11 m/s) driving wind up.
    - 'peak_demand': Higher temperature (+4°C), signaling peak cooling demand and high residential load.
    """
    df_mod = df.copy()

    if scenario == "normal":
        pass  # Baseline unchanged

    elif scenario == "cloudy":
        df_mod["cloud_cover"] = np.clip(df_mod["cloud_cover"] + 0.65, 0.0, 0.95)
        # Solar irradiance severely attenuated
        df_mod["solar_irradiance"] = np.round(df_mod["solar_irradiance"] * 0.25, 2)
        df_mod["temperature"] = np.round(df_mod["temperature"] - 2.5, 2)

    elif scenario == "heavy_monsoon":
        df_mod["cloud_cover"] = 0.95
        df_mod["solar_irradiance"] = np.round(df_mod["solar_irradiance"] * 0.10, 2)
        df_mod["rainfall"] = 18.50
        df_mod["water_flow"] = 85.00
        df_mod["humidity"] = 96.0
        df_mod["temperature"] = 21.0

    elif scenario == "high_wind":
        df_mod["wind_speed"] = 12.80  # Above rated turbine speed (11 m/s)
        df_mod["wind_direction"] = 245.0  # Prevailing monsoon wind direction

    elif scenario == "peak_demand":
        df_mod["temperature"] = np.round(df_mod["temperature"] + 4.5, 2)
        df_mod["humidity"] = np.round(np.clip(df_mod["humidity"] + 10.0, 0.0, 100.0), 1)

    return df_mod


def validate_future_inputs(df: pd.DataFrame, horizon: int) -> None:
    """
    Validate user-supplied future input data.
    """
    # 1. Row count
    if len(df) != horizon:
        raise ValueError(
            f"Input data length mismatch: expected exactly {horizon} rows, but received {len(df)} rows."
        )

    # 2. Required columns
    missing = [col for col in REQUIRED_FUTURE_INPUT_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Input data missing required column(s): {missing}")

    # 3. Timestamps
    ts = pd.to_datetime(df["timestamp"])
    if ts.isnull().any():
        raise ValueError("Input data contains missing/null timestamp(s).")
    if ts.duplicated().any():
        raise ValueError("Input data contains duplicate timestamps.")

    if len(ts) > 1:
        diffs = ts.diff().iloc[1:]
        if not (diffs == pd.Timedelta(hours=1)).all():
            raise ValueError("Input data timestamps must be continuous hourly observations.")

    # 4. Numerical domain checks
    for col in REQUIRED_FUTURE_INPUT_COLUMNS:
        if col == "timestamp":
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise ValueError(f"Input data column '{col}' must have a numeric dtype.")
        if df[col].isnull().any():
            raise ValueError(f"Input data column '{col}' contains NaN values.")
        if not np.isfinite(df[col].to_numpy()).all():
            raise ValueError(f"Input data column '{col}' contains infinite values.")

        # Check bounds
        if col in NUMERICAL_BOUNDS:
            lower, upper = NUMERICAL_BOUNDS[col]
            if (df[col] < lower).any() or (df[col] > upper).any():
                raise ValueError(
                    f"Input data column '{col}' contains values outside physical bounds [{lower}, {upper}]."
                )


def validate_forecast_contract(payload: Dict[str, Any], horizon: int = 24) -> None:
    """
    Enforce strict validation of the shared forecast.json schema contract.

    Contract:
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
    """
    # Top-level keys
    expected_top_keys = {"location", "forecast_horizon_hours", "forecast"}
    actual_top_keys = set(payload.keys())
    if actual_top_keys != expected_top_keys:
        extra = actual_top_keys - expected_top_keys
        missing = expected_top_keys - actual_top_keys
        raise ValueError(
            f"forecast.json contract violation: expected keys {expected_top_keys}, "
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

    forecast_list = payload["forecast"]
    if not isinstance(forecast_list, list):
        raise ValueError("forecast.json violation: 'forecast' field must be a list of records.")

    if len(forecast_list) != horizon:
        raise ValueError(
            f"forecast.json violation: expected {horizon} forecast records, got {len(forecast_list)}"
        )

    # Validate each record
    expected_record_keys = set(CONTRACT_FORECAST_KEYS)
    timestamps = []

    for idx, record in enumerate(forecast_list):
        rec_keys = set(record.keys())
        if rec_keys != expected_record_keys:
            raise ValueError(
                f"forecast.json record #{idx} key violation: expected {expected_record_keys}, got {rec_keys}"
            )

        ts_str = record["timestamp"]
        try:
            # Parse ISO-8601 timestamp
            dt = datetime.fromisoformat(ts_str)
            timestamps.append(dt)
        except Exception as e:
            raise ValueError(f"forecast.json record #{idx} has invalid ISO-8601 timestamp '{ts_str}': {e}")

        # Non-negative power checks
        for power_field in ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]:
            val = record[power_field]
            if not isinstance(val, (int, float)):
                raise ValueError(
                    f"forecast.json record #{idx} field '{power_field}' is not numeric (type: {type(val)})."
                )
            if np.isnan(val) or np.isinf(val):
                raise ValueError(
                    f"forecast.json record #{idx} field '{power_field}' is NaN or infinite."
                )
            if val < 0.0:
                raise ValueError(
                    f"forecast.json record #{idx} field '{power_field}' is negative ({val} < 0.0)."
                )

    # Check consecutive hourly timestamps
    ts_series = pd.Series(timestamps)
    if len(ts_series) > 1:
        step_diffs = ts_series.diff().iloc[1:]
        if not (step_diffs == pd.Timedelta(hours=1)).all():
            raise ValueError("forecast.json violation: forecast timestamps must be consecutive hourly steps.")


def main():
    print("utils.py loaded successfully. Ready for inference and validation.")


if __name__ == "__main__":
    main()

