"""
train_experiments.py
====================
Experimental Training Pipeline for GridMate Version 2 Wind and Hydro Models.

This script tests cyclical feature engineering on Wind and Hydro models:
- Wind: wind_direction mapped to sin/cos (from radians); hour and month mapped to sin/cos.
- Hydro: month and day_of_year mapped to sin/cos (periods 12 and 365).

Baseline models (wind_model.joblib, hydro_model.joblib) are loaded and evaluated
on the same test sets for direct comparison against the candidate models
(wind_experiment_model.joblib, hydro_experiment_model.joblib).

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

# Baseline configurations (for out-of-sample comparison)
BASELINE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "wind": {
        "target": "wind_kw",
        "train_file": "wind_train.csv",
        "test_file": "wind_test.csv",
        "baseline_model_file": "wind_model.joblib",
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
        "baseline_model_file": "hydro_model.joblib",
        "features": [
            "water_flow",
            "water_flow_lag_1",
            "rainfall",
            "month",
            "day_of_year",
        ],
    },
}

# Experiment configurations (with cyclical transformations)
EXPERIMENT_CONFIGS: Dict[str, Dict[str, Any]] = {
    "wind": {
        "target": "wind_kw",
        "candidate_model_file": "wind_experiment_model.joblib",
        "features": [
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
    },
    "hydro": {
        "target": "hydro_kw",
        "candidate_model_file": "hydro_experiment_model.joblib",
        "features": [
            "water_flow",
            "water_flow_lag_1",
            "rainfall",
            "month_sin",
            "month_cos",
            "day_of_year_sin",
            "day_of_year_cos",
        ],
    },
}

# XGBoost hyperparameters matching train.py
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


def validate_raw_dataset(
    df: pd.DataFrame,
    model_name: str,
    split_name: str,
    required_features: List[str],
    target_col: str,
) -> pd.DataFrame:
    """
    Validate raw training/testing datasets: check required columns,
    missing values, finite numeric features, and non-negative targets.
    """
    df_clean = df.copy()

    # 1. Required columns
    required_cols = ["timestamp"] + required_features + [target_col]
    missing_cols = [c for c in required_cols if c not in df_clean.columns]
    if missing_cols:
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Missing required column(s): {missing_cols}"
        )

    # 2. Check missing values
    nan_counts = df_clean[required_features + [target_col]].isnull().sum()
    if nan_counts.any():
        failing = nan_counts[nan_counts > 0].to_dict()
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Missing (NaN) values detected: {failing}"
        )

    # 3. Check finite numeric values
    for col in required_features + [target_col]:
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

    # 4. Check non-negative target
    if (df_clean[target_col] < 0.0).any():
        min_val = float(df_clean[target_col].min())
        raise ValueError(
            f"[{model_name.upper()} {split_name.upper()}] Target '{target_col}' contains negative values (min: {min_val:.4f})"
        )

    # 5. Timestamp validation
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


def engineer_wind_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply cyclical transformations to Wind dataset:
    - wind_direction: converted from degrees to radians, then sin and cos.
    - hour: cyclical sin and cos (period 24).
    - month: cyclical sin and cos (period 12).
    - Retains: wind_speed, wind_speed_lag_1, pressure, temperature, wind_kw, timestamp.
    """
    df_exp = df.copy()

    # Wind direction: radians -> sin & cos
    rad = np.radians(df_exp["wind_direction"].to_numpy())
    df_exp["wind_direction_sin"] = np.sin(rad)
    df_exp["wind_direction_cos"] = np.cos(rad)

    # Hour: period 24
    hour_val = df_exp["hour"].to_numpy()
    df_exp["hour_sin"] = np.sin(2.0 * np.pi * hour_val / 24.0)
    df_exp["hour_cos"] = np.cos(2.0 * np.pi * hour_val / 24.0)

    # Month: period 12
    month_val = df_exp["month"].to_numpy()
    df_exp["month_sin"] = np.sin(2.0 * np.pi * month_val / 12.0)
    df_exp["month_cos"] = np.cos(2.0 * np.pi * month_val / 12.0)

    return df_exp


def engineer_hydro_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply cyclical transformations to Hydro dataset:
    - month: cyclical sin and cos (period 12).
    - day_of_year: cyclical sin and cos (period 365).
    - Retains: water_flow, water_flow_lag_1, rainfall, hydro_kw, timestamp.
    """
    df_exp = df.copy()

    # Month: period 12
    month_val = df_exp["month"].to_numpy()
    df_exp["month_sin"] = np.sin(2.0 * np.pi * month_val / 12.0)
    df_exp["month_cos"] = np.cos(2.0 * np.pi * month_val / 12.0)

    # Day of year: period 365
    doy_val = df_exp["day_of_year"].to_numpy()
    df_exp["day_of_year_sin"] = np.sin(2.0 * np.pi * doy_val / 365.0)
    df_exp["day_of_year_cos"] = np.cos(2.0 * np.pi * doy_val / 365.0)

    return df_exp


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Calculate MAE, RMSE, and R2 regression metrics."""
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
    }


def run_experiments() -> Dict[str, Any]:
    """
    Run Wind and Hydro cyclical feature engineering experiments,
    evaluate candidate models, compare against baseline models,
    and save candidate models and experiment_metrics.json.
    """
    print("=" * 84)
    print("  GRIDMATE — WIND & HYDRO CYCLICAL FEATURE EXPERIMENTS (VERSION 2)")
    print(f"  Provenance: {DATASET_PROVENANCE}")
    print("=" * 84)

    # Verify directories
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory does not exist at: {DATA_DIR}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    results_payload: Dict[str, Any] = {
        "metadata": {
            "project": "GridMate",
            "module": "forecasting_real_data",
            "experiment_name": "Wind & Hydro Cyclical Feature Engineering",
            "dataset_provenance": DATASET_PROVENANCE,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_type": "XGBoost Regressor",
            "hyperparameters": XGB_HYPERPARAMETERS,
            "disclaimer": (
                "Improvements observed in this experiment are derived from synthetic "
                "demonstration data and do not constitute proof of real-world forecasting accuracy."
            ),
        },
        "experiments": {},
    }

    comparison_rows = []

    for model_name in ["wind", "hydro"]:
        base_cfg = BASELINE_CONFIGS[model_name]
        exp_cfg = EXPERIMENT_CONFIGS[model_name]

        target_col = base_cfg["target"]
        train_file = DATA_DIR / base_cfg["train_file"]
        test_file = DATA_DIR / base_cfg["test_file"]
        baseline_model_file = MODELS_DIR / base_cfg["baseline_model_file"]
        candidate_model_file = MODELS_DIR / exp_cfg["candidate_model_file"]

        baseline_features = base_cfg["features"]
        experiment_features = exp_cfg["features"]

        print(f"\n[{model_name.upper()}] Target: '{target_col}'")
        print(f"  Loading raw training data: {train_file.name}")
        if not train_file.exists():
            raise FileNotFoundError(f"Training file not found: {train_file}")
        raw_train = pd.read_csv(train_file)

        print(f"  Loading raw testing data:  {test_file.name}")
        if not test_file.exists():
            raise FileNotFoundError(f"Testing file not found: {test_file}")
        raw_test = pd.read_csv(test_file)

        # 1. Validate raw dataset and chronological separation
        train_df = validate_raw_dataset(raw_train, model_name, "train", baseline_features, target_col)
        test_df = validate_raw_dataset(raw_test, model_name, "test", baseline_features, target_col)
        min_train_ts, max_train_ts, min_test_ts, max_test_ts = validate_chronological_separation(
            train_df, test_df, model_name
        )
        print(f"  Chronological separation verified:")
        print(f"    Train: {len(train_df)} rows ({min_train_ts} to {max_train_ts})")
        print(f"    Test:  {len(test_df)} rows ({min_test_ts} to {max_test_ts})")

        # 2. Evaluate Baseline Model on identical test rows
        print(f"  Loading baseline model: {baseline_model_file.name}")
        if not baseline_model_file.exists():
            raise FileNotFoundError(
                f"Baseline model artifact not found at: {baseline_model_file}. "
                "Train baseline models using train.py first."
            )
        baseline_model = joblib.load(baseline_model_file)

        X_base_test = test_df[baseline_features].copy()
        y_test = test_df[target_col].to_numpy(dtype=float)

        y_base_test_pred = baseline_model.predict(X_base_test)
        y_base_test_pred = np.clip(y_base_test_pred, 0.0, None)
        base_test_metrics = compute_metrics(y_test, y_base_test_pred)

        print(f"  Baseline Test Metrics  -> MAE: {base_test_metrics['mae']:7.4f} kW | RMSE: {base_test_metrics['rmse']:7.4f} kW | R²: {base_test_metrics['r2']:6.4f}")

        # 3. Apply cyclical feature engineering
        print("  Applying cyclical feature transformations...")
        if model_name == "wind":
            exp_train_df = engineer_wind_features(train_df)
            exp_test_df = engineer_wind_features(test_df)
        elif model_name == "hydro":
            exp_train_df = engineer_hydro_features(train_df)
            exp_test_df = engineer_hydro_features(test_df)

        # Verify no NaNs or infs introduced
        for f in experiment_features:
            assert np.isfinite(exp_train_df[f].to_numpy()).all(), f"Non-finite value in train feature {f}"
            assert np.isfinite(exp_test_df[f].to_numpy()).all(), f"Non-finite value in test feature {f}"

        X_exp_train = exp_train_df[experiment_features].copy()
        y_train = exp_train_df[target_col].to_numpy(dtype=float)
        X_exp_test = exp_test_df[experiment_features].copy()

        print(f"  Experimental Features ({len(experiment_features)}): {experiment_features}")

        # 4. Train experimental XGBRegressor
        print("  Training experimental XGBRegressor...")
        exp_model = xgb.XGBRegressor(**XGB_HYPERPARAMETERS)
        exp_model.fit(X_exp_train, y_train)

        # 5. Evaluate experimental model on train and test
        y_exp_train_pred = exp_model.predict(X_exp_train)
        y_exp_train_pred = np.clip(y_exp_train_pred, 0.0, None)
        exp_train_metrics = compute_metrics(y_train, y_exp_train_pred)

        y_exp_test_pred = exp_model.predict(X_exp_test)
        y_exp_test_pred = np.clip(y_exp_test_pred, 0.0, None)
        exp_test_metrics = compute_metrics(y_test, y_exp_test_pred)

        print(f"  Experiment Train Metrics -> MAE: {exp_train_metrics['mae']:7.4f} kW | RMSE: {exp_train_metrics['rmse']:7.4f} kW | R²: {exp_train_metrics['r2']:6.4f}")
        print(f"  Experiment Test Metrics  -> MAE: {exp_test_metrics['mae']:7.4f} kW | RMSE: {exp_test_metrics['rmse']:7.4f} kW | R²: {exp_test_metrics['r2']:6.4f}")

        # 6. Save candidate model artifact (do not overwrite baseline)
        joblib.dump(exp_model, candidate_model_file)
        print(f"  Saved candidate model artifact: {candidate_model_file}")

        # 7. Compare baseline vs experiment
        delta_mae = round(exp_test_metrics["mae"] - base_test_metrics["mae"], 4)
        delta_rmse = round(exp_test_metrics["rmse"] - base_test_metrics["rmse"], 4)
        delta_r2 = round(exp_test_metrics["r2"] - base_test_metrics["r2"], 4)

        comparison_summary = {
            "mae_delta": delta_mae,
            "rmse_delta": delta_rmse,
            "r2_delta": delta_r2,
            "mae_improved": bool(delta_mae < 0),
            "rmse_improved": bool(delta_rmse < 0),
            "r2_improved": bool(delta_r2 > 0),
        }

        comparison_rows.append({
            "target": target_col,
            "base_mae": base_test_metrics["mae"],
            "exp_mae": exp_test_metrics["mae"],
            "delta_mae": delta_mae,
            "base_rmse": base_test_metrics["rmse"],
            "exp_rmse": exp_test_metrics["rmse"],
            "delta_rmse": delta_rmse,
            "base_r2": base_test_metrics["r2"],
            "exp_r2": exp_test_metrics["r2"],
            "delta_r2": delta_r2,
        })

        results_payload["experiments"][model_name] = {
            "target": target_col,
            "baseline_artifact": base_cfg["baseline_model_file"],
            "candidate_artifact": exp_cfg["candidate_model_file"],
            "baseline_features": baseline_features,
            "experiment_features": experiment_features,
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "train_horizon": f"{min_train_ts} to {max_train_ts}",
            "test_horizon": f"{min_test_ts} to {max_test_ts}",
            "baseline_test_metrics": base_test_metrics,
            "experiment_train_metrics": exp_train_metrics,
            "experiment_test_metrics": exp_test_metrics,
            "test_comparison": comparison_summary,
        }

    # Save experiment metrics JSON
    metrics_path = OUTPUTS_DIR / "experiment_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)

    print(f"\n[SUCCESS] Experiment metrics successfully saved to: {metrics_path}")

    # Print comparison table
    print("\n" + "=" * 84)
    print("  EXPERIMENT VS BASELINE PERFORMANCE COMPARISON (TEST SET)")
    print("=" * 84)
    header = f"{'Target':<10} | {'Metric':<6} | {'Baseline':>10} | {'Experiment':>10} | {'Delta':>10} | {'Change':<12}"
    print(header)
    print("-" * 84)

    for row in comparison_rows:
        t = row["target"]
        # MAE
        c_mae = "Improved" if row["delta_mae"] < 0 else ("Degraded" if row["delta_mae"] > 0 else "Unchanged")
        print(f"{t:<10} | {'MAE':<6} | {row['base_mae']:10.4f} | {row['exp_mae']:10.4f} | {row['delta_mae']:+10.4f} | {c_mae:<12}")
        # RMSE
        c_rmse = "Improved" if row["delta_rmse"] < 0 else ("Degraded" if row["delta_rmse"] > 0 else "Unchanged")
        print(f"{'':<10} | {'RMSE':<6} | {row['base_rmse']:10.4f} | {row['exp_rmse']:10.4f} | {row['delta_rmse']:+10.4f} | {c_rmse:<12}")
        # R2
        c_r2 = "Improved" if row["delta_r2"] > 0 else ("Degraded" if row["delta_r2"] < 0 else "Unchanged")
        print(f"{'':<10} | {'R2':<6} | {row['base_r2']:10.4f} | {row['exp_r2']:10.4f} | {row['delta_r2']:+10.4f} | {c_r2:<12}")
        print("-" * 84)

    print("\n[NOTE ON INTERPRETATION]")
    print("Any metric differences observed here are experimental findings based on")
    print("AI-generated synthetic demonstration data. They benchmark model responsiveness")
    print("to cyclical trigonometric encoding, but do NOT constitute proof of real-world")
    print("forecasting accuracy on measured physical energy assets in Lonavala.")
    print("=" * 84)

    return results_payload


if __name__ == "__main__":
    run_experiments()
