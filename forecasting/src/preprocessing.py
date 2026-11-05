"""
preprocessing.py
================
Data loading, validation, and preprocessing module for GridMate AI Forecasting.

Responsibilities:
1. Load energy and weather dataset from CSV independently of current working directory.
2. Validate dataset schema: ensure all 15 required columns exist and report any unexpected extra columns.
3. Convert 'timestamp' to pandas datetime and enforce chronological ordering.
4. Verify timestamp integrity: guarantee zero duplicates and strict hourly continuity (freq='h').
5. Explicitly validate that all numerical columns are true numeric dtypes and reject string tokens.
6. Verify numerical integrity: detect NaN, nulls, and positive/negative infinity.
7. Enforce physical domain boundaries (non-negative power targets and plausible atmospheric ranges).
8. Safely validate and cast 'is_synthetic': reject invalid values and non-synthetic (False) records.
9. Preserve all valid extreme observations without silent filtering.
"""

from pathlib import Path
from typing import Optional, Union
import numpy as np
import pandas as pd

# Default path to synthetic dataset (resolved relative to this file)
DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "synthetic_lonavala_energy_data.csv"
)

# 15 Required Contract Columns
REQUIRED_COLUMNS = [
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
    "solar_kw",
    "wind_kw",
    "hydro_kw",
    "load_kw",
    "is_synthetic",
]

TARGET_COLUMNS = ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]

NUMERIC_COLUMNS = [
    col for col in REQUIRED_COLUMNS if col not in ["timestamp", "is_synthetic"]
]

# Physical and Domain Boundaries
NUMERICAL_BOUNDS = {
    "solar_kw": (0.0, 2000.0),
    "wind_kw": (0.0, 1000.0),
    "hydro_kw": (0.0, 1000.0),
    "load_kw": (0.0, 5000.0),
    "humidity": (0.0, 100.0),
    "cloud_cover": (0.0, 1.0),
    "wind_direction": (0.0, 360.0),
    "wind_speed": (0.0, 60.0),
    "solar_irradiance": (0.0, 1500.0),
    "rainfall": (0.0, 300.0),
    "pressure": (800.0, 1100.0),
    "water_flow": (0.0, 500.0),
    "temperature": (-10.0, 60.0),
}


def validate_schema(df: pd.DataFrame) -> None:
    """
    Verify presence of all required columns and detect any unexpected additional columns.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    extra = [col for col in df.columns if col not in REQUIRED_COLUMNS]

    errors = []
    if missing:
        errors.append(f"missing required column(s): {missing}")
    if extra:
        errors.append(f"unexpected additional column(s): {extra}")

    if errors:
        raise ValueError("Dataset schema violation: " + "; ".join(errors))


def validate_timestamp_continuity(df: pd.DataFrame) -> None:
    """
    Verify that timestamps have no duplicates and form a strictly continuous hourly sequence.
    """
    if df["timestamp"].isnull().any():
        null_count = int(df["timestamp"].isnull().sum())
        raise ValueError(
            f"Data integrity violation: found {null_count} missing/null timestamp(s)."
        )

    # Check for duplicates
    dup_mask = df["timestamp"].duplicated(keep=False)
    if dup_mask.any():
        num_dups = int(dup_mask.sum())
        sample_dups = df.loc[dup_mask, "timestamp"].head(3).tolist()
        raise ValueError(
            f"Data integrity violation: found {num_dups} duplicate timestamps. Samples: {sample_dups}"
        )

    # Check continuity (hourly intervals)
    if len(df) > 1:
        time_diffs = df["timestamp"].diff().iloc[1:]
        expected_step = pd.Timedelta(hours=1)
        discontinuities = time_diffs != expected_step

        if discontinuities.any():
            first_break_idx = discontinuities.idxmax()
            prev_ts = df.loc[first_break_idx - 1, "timestamp"]
            curr_ts = df.loc[first_break_idx, "timestamp"]
            actual_delta = time_diffs.loc[first_break_idx]
            gap_count = int(discontinuities.sum())
            raise ValueError(
                f"Timestamp continuity violation: detected {gap_count} gap(s) or irregular interval(s) in hourly observations. "
                f"First gap observed between '{prev_ts}' and '{curr_ts}' (delta: {actual_delta}, expected: {expected_step})."
            )


def validate_numeric_types(df: pd.DataFrame) -> None:
    """
    Verify that all expected numerical columns have numeric dtypes and contain no NaNs or infinities.
    """
    non_numeric_cols = []
    for col in NUMERIC_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            non_numeric_cols.append((col, str(df[col].dtype)))

    if non_numeric_cols:
        details = [f"'{col}' (dtype: {dtype})" for col, dtype in non_numeric_cols]
        raise ValueError(
            f"Data type violation: expected numerical dtype for column(s), but found: {details}. "
            "Ensure columns contain valid numeric numbers and no string tokens."
        )

    # Check missing (NaN / None) values
    null_cols = df[NUMERIC_COLUMNS].isnull().sum()
    if null_cols.any():
        failing = null_cols[null_cols > 0].to_dict()
        raise ValueError(
            f"Data integrity violation: numerical columns contain missing (NaN) values: {failing}"
        )

    # Check infinite (+inf / -inf) values
    inf_cols = {}
    for col in NUMERIC_COLUMNS:
        inf_count = int(np.isinf(df[col].to_numpy()).sum())
        if inf_count > 0:
            inf_cols[col] = inf_count

    if inf_cols:
        raise ValueError(
            f"Data integrity violation: infinite (+inf/-inf) values detected in column(s): {inf_cols}"
        )


def validate_domain_bounds(df: pd.DataFrame) -> None:
    """
    Validate numerical ranges and non-negative constraints without discarding valid observations.
    """
    for col, (lower, upper) in NUMERICAL_BOUNDS.items():
        vals = df[col]
        below_min = vals < lower
        above_max = vals > upper

        if below_min.any():
            min_found = float(vals.min())
            raise ValueError(
                f"Domain boundary violation in '{col}': found minimum value {min_found:.4f} < lower bound {lower}"
            )
        if above_max.any():
            max_found = float(vals.max())
            raise ValueError(
                f"Domain boundary violation in '{col}': found maximum value {max_found:.4f} > upper bound {upper}"
            )


def validate_and_cast_synthetic_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Safely validate and cast the 'is_synthetic' column.
    
    Rejects:
    - Missing (NaN/null) values.
    - Invalid non-boolean values/strings.
    - Any False values (since this dataset must be strictly synthetic).
    """
    col = "is_synthetic"
    if df[col].isnull().any():
        null_count = int(df[col].isnull().sum())
        raise ValueError(f"Data integrity violation: '{col}' contains {null_count} missing value(s).")

    valid_true_values = {True, 1, "True", "true", "TRUE"}
    valid_false_values = {False, 0, "False", "false", "FALSE"}
    allowed_values = valid_true_values | valid_false_values

    unique_vals = set(df[col].unique())
    invalid_vals = unique_vals - allowed_values
    if invalid_vals:
        raise ValueError(
            f"Data integrity violation: '{col}' contains unrecognized boolean representation(s): {invalid_vals}"
        )

    has_false = any(val in valid_false_values for val in unique_vals)
    if has_false:
        false_count = int(df[col].isin(valid_false_values).sum())
        raise ValueError(
            f"Data integrity violation: '{col}' contains {false_count} non-synthetic (False) record(s). "
            "All records in this dataset must be strictly synthetic."
        )

    # Safely cast to native boolean dtype
    df[col] = df[col].isin(valid_true_values).astype(bool)
    return df


def load_and_preprocess_data(
    csv_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Load, validate, and preprocess the GridMate energy and weather dataset.

    Args:
        csv_path: Path to the input CSV file. Defaults to
                  forecasting/data/synthetic_lonavala_energy_data.csv.

    Returns:
        pd.DataFrame: Cleaned, validated, chronologically sorted DataFrame with
                      parsed datetime timestamp and preserved 'is_synthetic' flag.

    Raises:
        FileNotFoundError: If the specified CSV file does not exist.
        ValueError: If schema, integrity, continuity, types, or domain bounds fail.
    """
    resolved_path = Path(csv_path) if csv_path is not None else DEFAULT_DATA_PATH
    if not resolved_path.exists():
        raise FileNotFoundError(f"Dataset file not found at: {resolved_path}")

    # 1. Load raw dataset
    df = pd.read_csv(resolved_path)

    # 2. Validate columns (missing or unexpected extra)
    validate_schema(df)

    # 3. Parse timestamp to datetime & sort chronologically
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # 4. Validate timestamp continuity and uniqueness
    validate_timestamp_continuity(df)

    # 5. Validate numeric types, missing values, and infinities
    validate_numeric_types(df)

    # 6. Validate physical & domain boundaries
    validate_domain_bounds(df)

    # 7. Safe validation and casting of 'is_synthetic'
    df = validate_and_cast_synthetic_flag(df)

    return df


def main():
    print(f"Loading and preprocessing data from: {DEFAULT_DATA_PATH}")
    df = load_and_preprocess_data()

    print("\n[SUCCESS] Preprocessing and all validation checks passed successfully.")
    print(f"Dataset Shape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"Observation Horizon: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
    print(f"Is Synthetic Data: {df['is_synthetic'].all()} ({df['is_synthetic'].sum()}/{len(df)} rows)")

    print("\n=== Column Data Types ===")
    for col, dtype in df.dtypes.items():
        print(f"  {col:20s}: {dtype}")

    print("\n=== Sample Records (Head 3) ===")
    print(df.head(3).to_string(index=False))

    print("\n=== Sample Records (Tail 3) ===")
    print(df.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
