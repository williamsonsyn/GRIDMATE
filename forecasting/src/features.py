"""
features.py
===========
Feature engineering pipeline for GridMate AI Forecasting.

Responsibilities:
1. Extract cyclical and calendar temporal features from timestamp.
2. Generate past-observation lag features for weather, water flow, and demand without lookahead bias.
3. Define target-specific feature sets for each of the four models:
   - solar_kw
   - wind_kw
   - hydro_kw
   - load_kw
4. Enforce strict isolation: prevent targets from appearing in their own feature sets.
5. Guarantee non-destructive processing: do not mutate the caller's input DataFrame.
6. Handle lag-induced initial NaNs cleanly without backward imputation.
"""

from pathlib import Path
import sys
from typing import Dict, List

import numpy as np
import pandas as pd

# Ensure repository root is on sys.path for clean imports when run directly
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forecasting.src.preprocessing import load_and_preprocess_data, TARGET_COLUMNS


# Target-specific feature lists (Target column is strictly excluded from its own features)
SOLAR_FEATURES: List[str] = [
    "solar_irradiance",
    "solar_irradiance_lag_1",
    "cloud_cover",
    "temperature",
    "humidity",
    "hour",
    "month",
    "day_of_year",
]

WIND_FEATURES: List[str] = [
    "wind_speed",
    "wind_speed_lag_1",
    "wind_direction",
    "pressure",
    "temperature",
    "hour",
    "month",
]

HYDRO_FEATURES: List[str] = [
    "water_flow",
    "water_flow_lag_1",
    "rainfall",
    "month",
    "day_of_year",
]

LOAD_FEATURES: List[str] = [
    "historical_load_lag_1",
    "historical_load_lag_24",
    "temperature",
    "humidity",
    "hour",
    "day_of_week",
    "month",
    "is_weekend",
]

FEATURE_SETS: Dict[str, List[str]] = {
    "solar_kw": SOLAR_FEATURES,
    "wind_kw": WIND_FEATURES,
    "hydro_kw": HYDRO_FEATURES,
    "load_kw": LOAD_FEATURES,
}


def get_feature_columns(target: str) -> List[str]:
    """
    Retrieve the designated feature column list for a specific generation/load target.

    Args:
        target: One of ['solar_kw', 'wind_kw', 'hydro_kw', 'load_kw']

    Returns:
        List[str]: List of column names to be used as model inputs.

    Raises:
        KeyError: If target is not recognized.
    """
    if target not in FEATURE_SETS:
        raise KeyError(
            f"Unrecognized target '{target}'. Expected one of {list(FEATURE_SETS.keys())}"
        )
    return FEATURE_SETS[target].copy()


def create_features(df: pd.DataFrame, drop_na: bool = True) -> pd.DataFrame:
    """
    Extract temporal features and past-observation lag features.

    Features generated:
    - Temporal: hour, day_of_week, day_of_year, month, is_weekend
    - Past-Observation Lags:
        * historical_load_lag_1 (t - 1)
        * historical_load_lag_24 (t - 24)
        * solar_irradiance_lag_1 (t - 1)
        * wind_speed_lag_1 (t - 1)
        * water_flow_lag_1 (t - 1)

    Guarantees:
    - Does not mutate the input DataFrame.
    - Preserves all original columns (including timestamp, targets, and is_synthetic).
    - Prevents lookahead data leakage by strictly using past shifts (shift >= 1).
    - If drop_na is True, cleanly removes initial rows with unpopulated lags (e.g. first 24 hours).
      Does not use backward filling or future lookahead.

    Args:
        df: Input DataFrame containing cleaned weather, demand, and generation data.
        drop_na: Whether to drop initial unpopulated lag rows (default: True).

    Returns:
        pd.DataFrame: New DataFrame containing original and engineered features.
    """
    # 1. Non-destructive copy
    data = df.copy()

    # 2. Enforce chronological ordering before lag shifting
    if not data["timestamp"].is_monotonic_increasing:
        data = data.sort_values("timestamp").reset_index(drop=True)

    # 3. Temporal Features
    ts = data["timestamp"]
    data["hour"] = ts.dt.hour
    data["day_of_week"] = ts.dt.day_of_week
    data["day_of_year"] = ts.dt.day_of_year
    data["month"] = ts.dt.month
    data["is_weekend"] = (data["day_of_week"] >= 5).astype(int)

    # 4. Past-observation Lag Features (Strictly past, no future leakage)
    data["historical_load_lag_1"] = data["load_kw"].shift(1)
    data["historical_load_lag_24"] = data["load_kw"].shift(24)
    data["solar_irradiance_lag_1"] = data["solar_irradiance"].shift(1)
    data["wind_speed_lag_1"] = data["wind_speed"].shift(1)
    data["water_flow_lag_1"] = data["water_flow"].shift(1)

    # 5. Clean handling of lag NaNs
    if drop_na:
        data = data.dropna().reset_index(drop=True)

    return data


def main():
    print("Loading preprocessed dataset...")
    df_raw = load_and_preprocess_data()
    raw_shape = df_raw.shape
    raw_copy_check = df_raw.copy(deep=True)

    print("Running create_features(df_raw)...")
    df_feat = create_features(df_raw, drop_na=True)
    feat_shape = df_feat.shape

    # 1. Shape and rows lost
    rows_lost = raw_shape[0] - feat_shape[0]
    print("\n=== Dataset Shapes & Row Audit ===")
    print(f"Original shape: {raw_shape}")
    print(f"Engineered feature shape: {feat_shape}")
    print(f"Rows dropped due to lag creation: {rows_lost} (expected: 24 for 24h lag)")

    # 2. Verify immutability of input DataFrame
    is_unchanged = df_raw.equals(raw_copy_check)
    print(f"Original DataFrame unchanged: {is_unchanged}")
    assert is_unchanged, "Original DataFrame was mutated!"

    # 3. Column inventory
    print("\n=== Resulting Columns (Total: {}) ===".format(len(df_feat.columns)))
    for idx, col in enumerate(df_feat.columns, 1):
        print(f"  {idx:2d}. {col:25s} (dtype: {df_feat[col].dtype})")

    # 4. Verify lag correspondence to earlier timestamps
    print("\n=== Lag Verification Check ===")
    test_idx = 100
    row_t = df_feat.iloc[test_idx]
    row_t_minus_1 = df_feat.iloc[test_idx - 1]
    row_t_minus_24 = df_feat.iloc[test_idx - 24]

    print(f"Inspection at timestamp: {row_t['timestamp']}")
    print(f"  - load_kw at (t-1):                {row_t_minus_1['load_kw']:.2f}")
    print(f"  - historical_load_lag_1 at t:      {row_t['historical_load_lag_1']:.2f}")
    assert row_t["historical_load_lag_1"] == row_t_minus_1["load_kw"], "Mismatch in historical_load_lag_1!"

    print(f"  - load_kw at (t-24):               {row_t_minus_24['load_kw']:.2f}")
    print(f"  - historical_load_lag_24 at t:     {row_t['historical_load_lag_24']:.2f}")
    assert row_t["historical_load_lag_24"] == row_t_minus_24["load_kw"], "Mismatch in historical_load_lag_24!"

    print(f"  - solar_irradiance at (t-1):       {row_t_minus_1['solar_irradiance']:.2f}")
    print(f"  - solar_irradiance_lag_1 at t:     {row_t['solar_irradiance_lag_1']:.2f}")
    assert row_t["solar_irradiance_lag_1"] == row_t_minus_1["solar_irradiance"], "Mismatch in solar_irradiance_lag_1!"

    print(f"  - wind_speed at (t-1):             {row_t_minus_1['wind_speed']:.2f}")
    print(f"  - wind_speed_lag_1 at t:           {row_t['wind_speed_lag_1']:.2f}")
    assert row_t["wind_speed_lag_1"] == row_t_minus_1["wind_speed"], "Mismatch in wind_speed_lag_1!"

    print(f"  - water_flow at (t-1):             {row_t_minus_1['water_flow']:.2f}")
    print(f"  - water_flow_lag_1 at t:           {row_t['water_flow_lag_1']:.2f}")
    assert row_t["water_flow_lag_1"] == row_t_minus_1["water_flow"], "Mismatch in water_flow_lag_1!"
    print("[PASS] All lag values strictly match past observations.")

    # 5. Target isolation check
    print("\n=== Target Isolation Check ===")
    for target, feat_list in FEATURE_SETS.items():
        is_isolated = target not in feat_list
        print(f"Target '{target:8s}': excluded from features -> {is_isolated}")
        assert is_isolated, f"Target '{target}' leaked into its own feature set!"


if __name__ == "__main__":
    main()

