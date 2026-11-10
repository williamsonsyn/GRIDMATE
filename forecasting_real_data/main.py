"""Forecasting internal microservice for GridMate (Version 2).

Produces multi-target hourly energy forecasts (solar_kw, wind_kw, hydro_kw, load_kw)
using trained XGBoost models.
"""
from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path
import sys
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
SRC_DIR = BASE_DIR / "src"
MODELS_DIR = BASE_DIR / "models"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import predict  # type: ignore[import-not-found]

app = FastAPI(
    title="GridMate AI Forecasting Service",
    description="Internal microservice for XGBoost multi-target renewable energy forecasting",
    version="2.0.0",
)


class PredictPayload(BaseModel):
    scenario: str = "normal"
    horizon: int = 24
    future_weather: Optional[list[dict[str, Any]]] = None
    allow_arbitrary_dates: bool = False


@app.get("/health", tags=["health"])
def health() -> dict[str, Any]:
    expected_models = ["solar_model.joblib", "wind_model.joblib", "hydro_model.joblib", "load_model.joblib"]
    models_ok = all((MODELS_DIR / m).exists() for m in expected_models)
    return {
        "status": "ok" if models_ok else "degraded",
        "service": "forecasting",
        "models_present": models_ok,
        "version": "v2",
    }


@app.post("/predict", tags=["forecasting"])
def generate_forecast(payload: PredictPayload) -> dict[str, Any]:
    try:
        df_weather = None
        if payload.future_weather:
            df_weather = pd.DataFrame(payload.future_weather)
            if "timestamp" in df_weather.columns:
                df_weather["timestamp"] = pd.to_datetime(df_weather["timestamp"])

        with contextlib.redirect_stdout(io.StringIO()):
            raw = predict.generate_forecast(
                input_data=df_weather,
                horizon=payload.horizon,
                scenario=payload.scenario,
                save_output=False,
                allow_arbitrary_dates=payload.allow_arbitrary_dates or (df_weather is not None),
            )
        return raw
    except Exception as exc:
        log.exception("Forecast generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

