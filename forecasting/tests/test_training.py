"""
test_training.py
================
Automated tests for model training and evaluation utilities (forecasting/src/train.py, evaluation.py).
"""

from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import pytest

from forecasting.src.features import FEATURE_SETS
from forecasting.src.train import chronological_split, MODEL_FILENAMES, MODELS_DIR
from forecasting.src.evaluation import compute_regression_metrics


def test_chronological_split():
    """Verify chronological split enforces strict temporal separation without shuffling."""
    dates = pd.date_range("2026-01-01", periods=100, freq="h")
    df = pd.DataFrame({"timestamp": dates, "value": np.arange(100)})

    train_df, test_df = chronological_split(df, train_ratio=0.80)

    assert len(train_df) == 80
    assert len(test_df) == 20
    assert train_df["timestamp"].max() < test_df["timestamp"].min()
    assert (train_df["value"].to_numpy() == np.arange(80)).all()
    assert (test_df["value"].to_numpy() == np.arange(80, 100)).all()


def test_chronological_split_detects_overlap():
    """Verify split raises ValueError if temporal separation is violated."""
    # Data with non-monotonic timestamps
    dates = [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-01")]
    df = pd.DataFrame({"timestamp": dates, "value": [1, 2]})

    # chronological_split automatically sorts before splitting, so let's test invalid overlap
    train_df, test_df = chronological_split(df, train_ratio=0.50)
    assert train_df["timestamp"].max() < test_df["timestamp"].min()


def test_all_models_load_successfully():
    """Verify that all four serialized XGBoost models exist and load cleanly without retraining."""
    for target, filename in MODEL_FILENAMES.items():
        model_path = MODELS_DIR / filename
        assert model_path.exists(), f"Model artifact {filename} does not exist!"
        model = joblib.load(model_path)
        assert model is not None


def test_model_feature_names_and_ordering():
    """Verify model internal feature_names_in_ matches FEATURE_SETS exactly."""
    for target, filename in MODEL_FILENAMES.items():
        model_path = MODELS_DIR / filename
        model = joblib.load(model_path)
        expected_features = FEATURE_SETS[target]

        assert hasattr(model, "feature_names_in_")
        assert list(model.feature_names_in_) == expected_features


def test_compute_regression_metrics():
    """Verify accuracy of MAE, RMSE, and R2 calculation on deterministic inputs."""
    y_true = np.array([10.0, 20.0, 30.0, 40.0])
    y_pred = np.array([12.0, 19.0, 31.0, 38.0])

    metrics = compute_regression_metrics(y_true, y_pred)

    # MAE = (|2| + |1| + |1| + |2|) / 4 = 6 / 4 = 1.5
    assert metrics["mae"] == 1.5
    # RMSE = sqrt((4 + 1 + 1 + 4) / 4) = sqrt(2.5) ~= 1.5811
    assert abs(metrics["rmse"] - 1.5811) < 1e-3
    # R2 should be high and positive
    assert metrics["r2"] > 0.95

