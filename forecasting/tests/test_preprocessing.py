"""
test_preprocessing.py
=====================
Automated tests for data preprocessing and validation module (forecasting/src/preprocessing.py).
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from forecasting.src.preprocessing import (
    REQUIRED_COLUMNS,
    NUMERICAL_BOUNDS,
    load_and_preprocess_data,
    validate_schema,
    validate_timestamp_continuity,
    validate_numeric_types,
    validate_domain_bounds,
    validate_and_cast_synthetic_flag,
)


@pytest.fixture
def clean_sample_data():
    """Load preprocessed data to serve as a baseline fixture for edge testing."""
    return load_and_preprocess_data()


def test_successful_csv_loading(clean_sample_data):
    """Verify that dataset loads successfully with correct dimensions and chronological sorting."""
    df = clean_sample_data
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 8760
    assert len(df.columns) == 15
    assert df["timestamp"].is_monotonic_increasing


def test_required_columns(clean_sample_data):
    """Verify schema check succeeds on valid data and catches missing/extra columns."""
    df = clean_sample_data
    validate_schema(df)  # Should not raise

    # Test missing column
    with pytest.raises(ValueError, match="missing required column"):
        validate_schema(df.drop(columns=["solar_kw"]))

    # Test unexpected extra column
    df_extra = df.copy()
    df_extra["unexpected_col"] = 42
    with pytest.raises(ValueError, match="unexpected additional column"):
        validate_schema(df_extra)


def test_missing_and_infinite_values(clean_sample_data):
    """Verify detection of missing (NaN) and infinite (+/-inf) values."""
    df = clean_sample_data

    # Test NaN injection
    df_nan = df.copy()
    df_nan.loc[5, "temperature"] = np.nan
    with pytest.raises(ValueError, match="missing \\(NaN\\) values"):
        validate_numeric_types(df_nan)

    # Test positive infinity injection
    df_pinf = df.copy()
    df_pinf.loc[10, "wind_speed"] = np.inf
    with pytest.raises(ValueError, match="infinite"):
        validate_numeric_types(df_pinf)

    # Test negative infinity injection
    df_ninf = df.copy()
    df_ninf.loc[10, "pressure"] = -np.inf
    with pytest.raises(ValueError, match="infinite"):
        validate_numeric_types(df_ninf)


def test_duplicate_timestamps(clean_sample_data):
    """Verify duplicate timestamp detection."""
    df = clean_sample_data.copy()
    df.loc[1, "timestamp"] = df.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="duplicate timestamps"):
        validate_timestamp_continuity(df)


def test_hourly_timestamp_continuity(clean_sample_data):
    """Verify detection of missing observation hours in the time series."""
    df = clean_sample_data.copy()
    # Drop index 10 to create a 2-hour gap between 9 and 11
    df_gap = df.drop(index=10).reset_index(drop=True)
    with pytest.raises(ValueError, match="Timestamp continuity violation"):
        validate_timestamp_continuity(df_gap)


def test_invalid_numerical_types(clean_sample_data):
    """Verify non-numeric text columns are detected and rejected."""
    df = clean_sample_data.copy()
    df["rainfall"] = df["rainfall"].astype(str)
    with pytest.raises(ValueError, match="Data type violation"):
        validate_numeric_types(df)


def test_domain_bounds(clean_sample_data):
    """Verify that domain boundary and non-negativity checks are enforced."""
    df = clean_sample_data

    # Negative solar generation
    df_neg_solar = df.copy()
    df_neg_solar.loc[10, "solar_kw"] = -1.0
    with pytest.raises(ValueError, match="Domain boundary violation in 'solar_kw'"):
        validate_domain_bounds(df_neg_solar)

    # Negative load
    df_neg_load = df.copy()
    df_neg_load.loc[10, "load_kw"] = -10.0
    with pytest.raises(ValueError, match="Domain boundary violation in 'load_kw'"):
        validate_domain_bounds(df_neg_load)

    # Humidity exceeding 100%
    df_high_hum = df.copy()
    df_high_hum.loc[10, "humidity"] = 105.0
    with pytest.raises(ValueError, match="Domain boundary violation in 'humidity'"):
        validate_domain_bounds(df_high_hum)


def test_safe_is_synthetic_validation(clean_sample_data):
    """Verify is_synthetic validation rejects invalid representations and False values."""
    df = clean_sample_data

    # Reject non-synthetic False
    df_false = df.copy()
    df_false.loc[0, "is_synthetic"] = False
    with pytest.raises(ValueError, match="non-synthetic \\(False\\) record"):
        validate_and_cast_synthetic_flag(df_false)

    # Reject unrecognized value
    df_invalid = df.copy()
    df_invalid["is_synthetic"] = df_invalid["is_synthetic"].astype(object)
    df_invalid.loc[0, "is_synthetic"] = "corrupted_text"
    with pytest.raises(ValueError, match="unrecognized boolean representation"):
        validate_and_cast_synthetic_flag(df_invalid)

    # Valid conversion preserves boolean dtype
    df_valid = validate_and_cast_synthetic_flag(clean_sample_data.copy())
    assert df_valid["is_synthetic"].dtype == bool
    assert df_valid["is_synthetic"].all()

