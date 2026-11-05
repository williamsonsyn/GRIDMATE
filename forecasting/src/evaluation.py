"""
evaluation.py
=============
Model evaluation and metric reporting module for GridMate AI Forecasting.

Responsibilities:
1. Compute standard regression performance metrics (MAE, RMSE, R²).
2. Evaluate trained models on chronological, out-of-sample test splits without data leakage.
3. Generate structured, machine-readable metrics report formatted according to contract.
4. Save metrics into forecasting/outputs/metrics.json.
5. Explicitly label all results as synthetic-data benchmark evaluations (not actual measured data).
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Union

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_METRICS_PATH = (
    Path(__file__).resolve().parents[1] / "outputs" / "metrics.json"
)


def compute_regression_metrics(
    y_true: Union[pd.Series, np.ndarray],
    y_pred: Union[pd.Series, np.ndarray],
) -> Dict[str, float]:
    """
    Calculate MAE, RMSE, and R² score for continuous regression predictions.

    Args:
        y_true: Ground-truth target values.
        y_pred: Model predictions.

    Returns:
        Dict[str, float]: Dictionary containing rounded MAE, RMSE, and R².
    """
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    r2 = float(r2_score(y_true, y_pred))

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
    }


def build_metrics_payload(
    target_metrics: Dict[str, Dict[str, Any]],
    train_count: int,
    test_count: int,
    train_horizon: str,
    test_horizon: str,
) -> Dict[str, Any]:
    """
    Assemble the complete structured metrics payload with clear synthetic labeling.
    """
    return {
        "metadata": {
            "project": "GridMate",
            "module": "forecasting",
            "location": "Lonavala, Maharashtra",
            "data_type": "Synthetic Demo Data (Illustrative prototype results - Not measured utility data)",
            "is_synthetic": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "train_test_split": "80:20 Chronological",
            "train_samples": train_count,
            "test_samples": test_count,
            "train_horizon": train_horizon,
            "test_horizon": test_horizon,
        },
        "targets": target_metrics,
    }


def save_metrics(
    metrics_payload: Dict[str, Any],
    output_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Save the metrics dictionary as a readable, formatted JSON file.

    Args:
        metrics_payload: Structured evaluation dictionary.
        output_path: Destination path. Defaults to forecasting/outputs/metrics.json.

    Returns:
        Path: Path to the written JSON file.
    """
    dest = Path(output_path) if output_path is not None else DEFAULT_METRICS_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    return dest


def main():
    print("evaluation.py loaded successfully. Ready for evaluation pipeline invocation.")


if __name__ == "__main__":
    main()

