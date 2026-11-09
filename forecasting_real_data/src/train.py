"""
train.py
========
Version 2 AI Forecasting Model Training Pipeline for GridMate.

Trains four independent XGBoost regression models (solar_kw, wind_kw,
hydro_kw, load_kw) using pre-split model-specific training and testing CSV pairs.

Provenance:
AI-generated synthetic demonstration data; not actual measured Lonavala energy data.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
try:
    from sklearn.metrics import root_mean_squared_error
except ImportError:
    from sklearn.metrics import mean_squared_error

    def root_mean_squared_error(y_true, y_pred):
        return float(np.sqrt(mean_squared_error(y_true, y_pred)))

import xgboost as xgb

# Resolve directory paths relative to this script / repository structure
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent  # forecasting_real_data
REPO_ROOT = BASE_DIR.parent   # repository root
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"

DATASET_PROVENANCE = (
    "AI-generated synthetic demonstration data; not actual measured Lonavala energy data"
)

# Exact model-specific feature sets and target configurations
MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "solar": {
        "target": "solar_kw",
        "train_file": "solar_train.csv",
        "test_file": "solar_test.csv",
        "model_file": "solar_model.joblib",
        "features": [
            "solar_irradiance",
            "solar_irradiance_lag_1",
            "cloud_cover",
            "temperature",
            "humidity",
            "hour",
            "month",
            "day_of_year",
        ],
    },
    "wind": {
        "target": "wind_kw",
        "train_file": "wind_train.csv",
        "test_file": "wind_test.csv",
        "model_file": "wind_model.joblib",
        "features": [
            "wind_speed",
            "wind_speed_lag_1",
            "wind_direction",
            "pressure",
            "temperature",
            "hour",
            "month",
        ],
    },
    "hydro": {
        "target": "hydro_kw",
        "train_file": "hydro_train.csv",
        "test_file": "hydro_test.csv",
        "model_file": "hydro_model.joblib",
        "features": [
            "water_flow",
            "water_flow_lag_1",
            "rainfall",
            "month",
            "day_of_year",
        ],
    },
    "load": {
        "target": "load_kw",
        "train_file": "load_train.csv",
        "test_file": "load_test.csv",
        "model_file": "load_model.joblib",
        "features": [
            "historical_load_lag_1",
            "historical_load_lag_24",
            "temperature",
            "humidity",
            "hour",
            "day_of_week",
            "month",
            "is_weekend",
        ],
    },
}

# Fixed XGBoost hyperparameters
XGB_HYPERPARAMETERS = {
    "objective": "reg:squarederror",
    "n_estimators": 150,
    "learning_rate": 0.05,
    "max_depth": 5,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "random_state": 42,
    "n_jobs": -1,
}


def validate_dataset(
    df: pd.DataFrame,
    model_name: str,
    split_name: str,
    feature_cols: List[str],
    target_col: str,
) -> pd.DataFrame:
    """
    Validate schema, feature ordering, missing values, finite numeric values,
    and non-negative targets.
    """
    df_clean = df.copy()

    # 1. Validate required columns existence
    required_cols = ["timestamp"] + feature_cols + [target_col]
    missing_cols = [c for c in required_cols if c not in df_clean.columns]
    if missing_cols:
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Missing required column(s): {missing_cols}"
        )

    # 2. Convert boolean features (e.g., is_weekend) to numeric integers (0/1)
    for col in feature_cols:
        if col in df_clean.columns:
            if pd.api.types.is_bool_dtype(df_clean[col]) or set(df_clean[col].dropna().unique()).issubset({True, False, "True", "False"}):
                df_clean[col] = df_clean[col].astype(int)

    # 3. Check for missing (NaN / null) values in features and target
    nan_counts = df_clean[feature_cols + [target_col]].isnull().sum()
    if nan_counts.any():
        failing = nan_counts[nan_counts > 0].to_dict()
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Missing (NaN) values detected: {failing}"
        )

    # 4. Check for infinite values (+/- inf) in features and target
    for col in feature_cols + [target_col]:
        if not pd.api.types.is_numeric_dtype(df_clean[col]):
            raise ValueError(
                f"[{model_name.upper()} {split_name.upper()}] Column '{col}' is not numeric (dtype: {df_clean[col].dtype})"
            )
        vals = df_clean[col].to_numpy()
        if not np.isfinite(vals).all():
            inf_count = int(np.isinf(vals).sum())
            raise ValueError(
                f"[{model_name.upper()} {split_name.upper()}] Column '{col}' contains {inf_count} infinite value(s)"
            )

    # 5. Check non-negative target constraint
    negative_mask = df_clean[target_col] < 0.0
    if negative_mask.any():
        min_val = float(df_clean[target_col].min())
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Target '{target_col}' contains negative values (min: {min_val:.4f})"
        )

    # 6. Validate and parse timestamp
    df_clean["timestamp"] = pd.to_datetime(df_clean["timestamp"])
    if df_clean["timestamp"].isnull().any():
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Invalid or unparseable timestamps detected"
        )

    return df_clean


def validate_chronological_separation(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    model_name: str,
) -> Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """
    Verify that the training observations strictly precede testing observations.
    """
    max_train_ts = train_df["timestamp"].max()
    min_train_ts = train_df["timestamp"].min()
    min_test_ts = test_df["timestamp"].min()
    max_test_ts = test_df["timestamp"].max()

    if max_train_ts >= min_test_ts:
        raise ValueError(
            f"[{model_name.upper()}] Chronological separation violation: "
            f"max training timestamp ({max_train_ts}) >= min testing timestamp ({min_test_ts})"
        )

    return min_train_ts, max_train_ts, min_test_ts, max_test_ts


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Dict[str, float]:
    """
    Calculate MAE, RMSE, and R2 regression metrics.
    """
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
    }


def train_all_models() -> Dict[str, Any]:
    """
    Main training workflow for Version 2 forecasting models.
    """
    print("=" * 72)
    print("  GRIDMATE — AI FORECASTING MODEL TRAINING (VERSION 2)")
    print(f"  Provenance: {DATASET_PROVENANCE}")
    print("=" * 72)

    # Verify directories
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory does not exist at: {DATA_DIR}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    metrics_payload: Dict[str, Any] = {
        "metadata": {
            "project": "GridMate",
            "module": "forecasting_real_data",
            "version": "2.0",
            "dataset_provenance": DATASET_PROVENANCE,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_type": "XGBoost Regressor",
            "hyperparameters": XGB_HYPERPARAMETERS,
        },
        "targets": {},
    }

    trained_models: Dict[str, xgb.XGBRegressor] = {}

    for model_name, cfg in MODEL_CONFIGS.items():
        target_col = cfg["target"]
        train_file = DATA_DIR / cfg["train_file"]
        test_file = DATA_DIR / cfg["test_file"]
        model_file = MODELS_DIR / cfg["model_file"]
        feature_cols = cfg["features"]

        print(f"\n[{model_name.upper()}] Target: '{target_col}'")
        print(f"  Loading training data: {train_file.name}")
        if not train_file.exists():
            raise FileNotFoundError(f"Training file not found: {train_file}")
        raw_train = pd.read_csv(train_file)

        print(f"  Loading testing data:  {test_file.name}")
        if not test_file.exists():
            raise FileNotFoundError(f"Testing file not found: {test_file}")
        raw_test = pd.read_csv(test_file)

        # Validate datasets
        train_df = validate_dataset(raw_train, model_name, "train", feature_cols, target_col)
        test_df = validate_dataset(raw_test, model_name, "test", feature_cols, target_col)

        # Validate chronological separation
        min_train_ts, max_train_ts, min_test_ts, max_test_ts = validate_chronological_separation(
            train_df, test_df, model_name
        )
        print(f"  Chronological integrity verified:")
        print(f"    Train: {len(train_df)} rows ({min_train_ts} to {max_train_ts})")
        print(f"    Test:  {len(test_df)} rows ({min_test_ts} to {max_test_ts})")

        # Feature extraction in exact specified order (excluding timestamp and target)
        X_train = train_df[feature_cols].copy()
        y_train = train_df[target_col].to_numpy(dtype=float)
        X_test = test_df[feature_cols].copy()
        y_test = test_df[target_col].to_numpy(dtype=float)

        print(f"  Features ({len(feature_cols)}): {feature_cols}")

        # Instantiate and train XGBRegressor
        print("  Training XGBRegressor...")
        model = xgb.XGBRegressor(**XGB_HYPERPARAMETERS)
        model.fit(X_train, y_train)

        # Evaluate on Train Set
        y_train_pred = model.predict(X_train)
        y_train_pred = np.clip(y_train_pred, 0.0, None)
        train_metrics = compute_metrics(y_train, y_train_pred)

        # Evaluate on Test Set
        y_test_pred = model.predict(X_test)
        y_test_pred = np.clip(y_test_pred, 0.0, None)
        test_metrics = compute_metrics(y_test, y_test_pred)

        print(f"  Train Metrics -> MAE: {train_metrics['mae']:7.2f} kW | RMSE: {train_metrics['rmse']:7.2f} kW | R²: {train_metrics['r2']:6.4f}")
        print(f"  Test Metrics  -> MAE: {test_metrics['mae']:7.2f} kW | RMSE: {test_metrics['rmse']:7.2f} kW | R²: {test_metrics['r2']:6.4f}")

        # Save trained model artifact
        joblib.dump(model, model_file)
        print(f"  Saved model artifact: {model_file}")

        trained_models[model_name] = model

        # Record metrics payload
        metrics_payload["targets"][target_col] = {
            "model_name": model_name,
            "artifact_file": cfg["model_file"],
            "features": feature_cols,
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "train_horizon": f"{min_train_ts} to {max_train_ts}",
            "test_horizon": f"{min_test_ts} to {max_test_ts}",
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
        }

    # Save metrics JSON
    metrics_path = OUTPUTS_DIR / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    print(f"\n[SUCCESS] Metrics successfully saved to: {metrics_path}")
    print("=" * 72)
    return metrics_payload


if __name__ == "__main__":
    train_all_models()
