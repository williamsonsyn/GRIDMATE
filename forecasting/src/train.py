"""
train.py
========
Model training orchestration for GridMate AI Forecasting.

Responsibilities:
1. Load preprocessed data and engineer feature representations.
2. Execute a chronological 80:20 train/test split (strictly no random shuffling or future leakage).
3. Train four independent XGBRegressor models:
   - solar_kw
   - wind_kw
   - hydro_kw
   - load_kw
4. Serialize and save trained models to forecasting/models/:
   - solar_model.joblib
   - wind_model.joblib
   - hydro_model.joblib
   - load_model.joblib
5. Evaluate performance on the chronological test split and persist metrics to forecasting/outputs/metrics.json.
6. Clearly mark all outputs as synthetic demo evaluations.
"""

from pathlib import Path
import sys
from typing import Dict, Tuple

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forecasting.src.preprocessing import load_and_preprocess_data, TARGET_COLUMNS
from forecasting.src.features import create_features, get_feature_columns
from forecasting.src.evaluation import (
    compute_regression_metrics,
    build_metrics_payload,
    save_metrics,
)

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
OUTPUTS_DIR = Path(__file__).resolve().parents[1] / "outputs"

MODEL_FILENAMES = {
    "solar_kw": "solar_model.joblib",
    "wind_kw": "wind_model.joblib",
    "hydro_kw": "hydro_model.joblib",
    "load_kw": "load_model.joblib",
}

DEFAULT_HYPERPARAMETERS = {
    "n_estimators": 150,
    "learning_rate": 0.05,
    "max_depth": 5,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "random_state": 42,
    "n_jobs": -1,
}


def chronological_split(
    df: pd.DataFrame,
    train_ratio: float = 0.80,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split the dataset chronologically into train and test sets without lookahead bias.

    Args:
        df: Feature-engineered DataFrame with sorted datetime 'timestamp'.
        train_ratio: Proportion of observations used for training (default: 0.80).

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (train_df, test_df)

    Raises:
        ValueError: If chronological integrity is violated.
    """
    if not df["timestamp"].is_monotonic_increasing:
        df = df.sort_values("timestamp").reset_index(drop=True)

    total_rows = len(df)
    split_idx = int(total_rows * train_ratio)

    train_df = df.iloc[:split_idx].copy().reset_index(drop=True)
    test_df = df.iloc[split_idx:].copy().reset_index(drop=True)

    # Enforce strict temporal separation
    max_train_ts = train_df["timestamp"].max()
    min_test_ts = test_df["timestamp"].min()
    if max_train_ts >= min_test_ts:
        raise ValueError(
            f"Chronological split violation: max train timestamp ({max_train_ts}) "
            f"is not strictly before min test timestamp ({min_test_ts})."
        )

    return train_df, test_df


def train_single_model(
    target: str,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    hyperparameters: Dict[str, any] = None,
) -> xgb.XGBRegressor:
    """
    Train an individual XGBRegressor on the provided training features and target.
    """
    params = hyperparameters or DEFAULT_HYPERPARAMETERS
    model = xgb.XGBRegressor(**params)
    model.fit(X_train, y_train)
    return model


def train_and_evaluate_all():
    """
    Full pipeline: load data, generate features, split chronologically,
    train 4 XGBoost regressors, serialize models, evaluate, and save metrics.
    """
    print("=" * 65)
    print("  GRIDMATE — AI FORECASTING MODEL TRAINING & EVALUATION")
    print("  (Synthetic Benchmark Pipeline — Not Measured Lonavala Data)")
    print("=" * 65)

    # 1. Load and Preprocess
    print("\n[Step 1/5] Loading and validating synthetic dataset...")
    df_raw = load_and_preprocess_data()
    print(f"  Loaded raw observations: {df_raw.shape[0]} rows x {df_raw.shape[1]} columns")

    # 2. Feature Engineering
    print("\n[Step 2/5] Creating temporal and past-observation lag features...")
    df_features = create_features(df_raw, drop_na=True)
    print(f"  Engineered feature matrix: {df_features.shape[0]} rows x {df_features.shape[1]} columns")

    # 3. Chronological 80:20 Train/Test Split
    print("\n[Step 3/5] Splitting data chronologically (80% Train, 20% Test)...")
    train_df, test_df = chronological_split(df_features, train_ratio=0.80)
    train_horizon = f"{train_df['timestamp'].iloc[0]} to {train_df['timestamp'].iloc[-1]}"
    test_horizon = f"{test_df['timestamp'].iloc[0]} to {test_df['timestamp'].iloc[-1]}"

    print(f"  Training set:   {len(train_df):5d} rows | Horizon: {train_horizon}")
    print(f"  Test set:       {len(test_df):5d} rows | Horizon: {test_horizon}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    models: Dict[str, xgb.XGBRegressor] = {}
    evaluation_metrics: Dict[str, Dict[str, any]] = {}

    # 4. Model Training & Evaluation
    print("\n[Step 4/5] Training 4 independent XGBoost models...")
    for target in TARGET_COLUMNS:
        feature_cols = get_feature_columns(target)
        X_train = train_df[feature_cols]
        y_train = train_df[target]
        X_test = test_df[feature_cols]
        y_test = test_df[target]

        print(f"\n  --- Training '{target}' (Inputs: {len(feature_cols)} features) ---")
        model = train_single_model(target, X_train, y_train)
        models[target] = model

        # Save model artifact
        model_filename = MODEL_FILENAMES[target]
        model_filepath = MODELS_DIR / model_filename
        joblib.dump(model, model_filepath)
        print(f"    Saved model artifact: {model_filepath.name}")

        # Out-of-sample chronological test prediction
        y_pred = model.predict(X_test)
        # Power is non-negative
        y_pred = np.clip(y_pred, 0.0, None)

        metrics = compute_regression_metrics(y_test, y_pred)
        metrics["test_samples"] = len(y_test)
        metrics["features"] = feature_cols
        evaluation_metrics[target] = metrics

        print(f"    Test Results -> MAE: {metrics['mae']:7.2f} kW | RMSE: {metrics['rmse']:7.2f} kW | R²: {metrics['r2']:6.4f}")

    # 5. Persist Metrics Report
    print("\n[Step 5/5] Saving evaluation report to metrics.json...")
    metrics_payload = build_metrics_payload(
        target_metrics=evaluation_metrics,
        train_count=len(train_df),
        test_count=len(test_df),
        train_horizon=train_horizon,
        test_horizon=test_horizon,
    )
    saved_path = save_metrics(metrics_payload)
    print(f"  Metrics successfully saved to: {saved_path}")

    print("\n" + "=" * 65)
    print("  MODEL TRAINING & EVALUATION COMPLETED SUCCESSFULLY")
    print("=" * 65)
    return models, evaluation_metrics


if __name__ == "__main__":
    train_and_evaluate_all()

