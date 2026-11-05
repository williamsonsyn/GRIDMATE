"""
test_features.py
================
Automated tests for feature engineering module (forecasting/src/features.py).
"""

import pandas as pd
import pytest

from forecasting.src.preprocessing import load_and_preprocess_data
from forecasting.src.features import (
    create_features,
    get_feature_columns,
    FEATURE_SETS,
)


@pytest.fixture
def clean_sample_data():
    """Load preprocessed data."""
    return load_and_preprocess_data()


def test_calendar_features(clean_sample_data):
    """Verify that temporal calendar features are accurately extracted."""
    df_feat = create_features(clean_sample_data.head(50), drop_na=False)

    for col in ["hour", "day_of_week", "day_of_year", "month", "is_weekend"]:
        assert col in df_feat.columns

    # Verify specific known timestamp properties
    # 2025-10-01 14:00:00 (Wednesday -> day_of_week=2, not weekend)
    row_14 = df_feat[df_feat["timestamp"] == "2025-10-01 14:00:00"].iloc[0]
    assert row_14["hour"] == 14
    assert row_14["month"] == 10
    assert row_14["day_of_week"] == 2
    assert row_14["is_weekend"] == 0


def test_lag_alignment_using_known_observations(clean_sample_data):
    """Verify that lag features strictly correspond to earlier observations."""
    df_feat = create_features(clean_sample_data, drop_na=True)

    idx = 50
    row_t = df_feat.iloc[idx]
    row_t_minus_1 = df_feat.iloc[idx - 1]
    row_t_minus_24 = df_feat.iloc[idx - 24]

    # Verify lag_1 features match t-1 observation
    assert row_t["historical_load_lag_1"] == row_t_minus_1["load_kw"]
    assert row_t["solar_irradiance_lag_1"] == row_t_minus_1["solar_irradiance"]
    assert row_t["wind_speed_lag_1"] == row_t_minus_1["wind_speed"]
    assert row_t["water_flow_lag_1"] == row_t_minus_1["water_flow"]

    # Verify lag_24 features match t-24 observation
    assert row_t["historical_load_lag_24"] == row_t_minus_24["load_kw"]


def test_input_dataframe_immutability(clean_sample_data):
    """Verify create_features does not mutate the caller's input DataFrame."""
    df_orig = clean_sample_data.copy(deep=True)
    df_copy = clean_sample_data.copy(deep=True)

    _ = create_features(df_copy, drop_na=True)

    assert df_copy.equals(df_orig), "Original DataFrame was mutated during feature creation!"


def test_lag_induced_nan_handling(clean_sample_data):
    """Verify that initial lag rows are properly handled."""
    # When drop_na=True, initial 24 unpopulated rows are removed
    df_dropped = create_features(clean_sample_data, drop_na=True)
    assert len(df_dropped) == len(clean_sample_data) - 24
    assert not df_dropped.isnull().any().any()

    # When drop_na=False, initial rows contain NaNs in lag columns
    df_retained = create_features(clean_sample_data, drop_na=False)
    assert len(df_retained) == len(clean_sample_data)
    assert df_retained["historical_load_lag_24"].iloc[:24].isnull().all()


def test_target_exclusion_from_features():
    """Verify that targets are strictly excluded from their own input feature sets."""
    for target, feat_list in FEATURE_SETS.items():
        assert target not in feat_list, f"Target '{target}' leaked into its own feature set!"


def test_get_feature_columns():
    """Verify feature column lookup and unrecognized target handling."""
    for target in ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]:
        feats = get_feature_columns(target)
        assert isinstance(feats, list)
        assert len(feats) > 0

    with pytest.raises(KeyError, match="Unrecognized target"):
        get_feature_columns("invalid_power_target")

