"""Forecasting service: wraps Member 1's generate_forecast().

Supports both Vercel internal service binding (via FORECASTING_SERVICE_URL)
and local in-process execution with mock fallback.
"""
from __future__ import annotations

import contextlib
import io
import logging
import os
import sys
from threading import Lock
from typing import Any

import httpx

from .. import config
from . import mock_data

log = logging.getLogger(__name__)
JsonDict = dict[str, Any]
_lock = Lock()


class ForecastError(RuntimeError):
    """Raised when the forecast cannot be produced."""


def _get_service_url() -> str | None:
    url = os.getenv("FORECASTING_SERVICE_URL")
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        return f"https://{url}"
    return url.rstrip("/")


def _load_predict() -> Any:
    """Lazy local import for development mode only."""
    src = str(config.FORECAST_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    import predict  # type: ignore[import-not-found]  # Member 1 module

    return predict


def _round_rows(raw: JsonDict) -> JsonDict:
    rows = []
    for r in raw["forecast"]:
        rows.append(
            {
                "timestamp": str(r["timestamp"]),
                "solar_kw": round(max(0.0, float(r["solar_kw"])), 2),
                "wind_kw": round(max(0.0, float(r["wind_kw"])), 2),
                "hydro_kw": round(max(0.0, float(r["hydro_kw"])), 2),
                "load_kw": round(max(0.0, float(r["load_kw"])), 2),
            }
        )
    if not rows:
        raise ForecastError("Forecast module returned an empty forecast.")
    return {
        "location": raw.get("location", config.LOCATION),
        "forecast_horizon_hours": len(rows),
        "forecast": rows,
    }


def _get_local_forecast(scenario: str) -> JsonDict:
    """Run local in-process forecasting (dev mode)."""
    with _lock:
        predict = _load_predict()
        with contextlib.redirect_stdout(io.StringIO()):
            raw = predict.generate_forecast(
                horizon=config.HORIZON_HOURS, scenario=scenario, save_output=False
            )
    return _round_rows(raw)


def get_real_forecast(scenario: str) -> JsonDict:
    service_url = _get_service_url()
    if service_url:
        payload = {"scenario": scenario, "horizon": config.HORIZON_HOURS}
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(f"{service_url}/predict", json=payload)
                resp.raise_for_status()
                return _round_rows(resp.json())
        except Exception as exc:
            log.exception("Remote forecasting service request failed: %s", exc)
            raise ForecastError(f"Forecasting service error: {exc}") from exc

    return _get_local_forecast(scenario)


def get_forecast(scenario: str) -> tuple[JsonDict, str, list[str]]:
    """Return (forecast, source, warnings). Source is 'model' or 'mock'."""
    service_url = _get_service_url()
    if service_url:
        # In production with service binding: call remote service without silent local fallback
        if config.MODE == "mock":
            return mock_data.get_mock_forecast(scenario), "mock", []
        try:
            return get_real_forecast(scenario), "model", []
        except Exception as exc:
            log.exception("Production forecasting service failed for scenario %s", scenario)
            raise ForecastError(f"Forecasting service unavailable: {exc}") from exc

    # Local development fallback
    if config.MODE == "mock":
        return mock_data.get_mock_forecast(scenario), "mock", []
    try:
        return _get_local_forecast(scenario), "model", []
    except Exception as exc:  # noqa: BLE001 - we surface/fallback on any module failure
        log.exception("Real forecast failed for scenario %s", scenario)
        if config.MODE == "real":
            raise ForecastError(f"Forecasting failed: {exc}") from exc
        return (
            mock_data.get_mock_forecast(scenario),
            "mock",
            [f"Forecast model unavailable ({type(exc).__name__}); showing mock forecast."],
        )


def get_forecast_for_date(
    date_str: str, scenario: str = "normal"
) -> tuple[JsonDict, str, list[str], str | None]:
    """Return (forecast, source, warnings, note).

    Uses Open-Meteo or historical average weather for date_str.
    """
    from .weather_service import get_weather_for_date

    weather_records, weather_src, note = get_weather_for_date(date_str)
    if config.MODE == "mock":
        raw = mock_data.get_mock_forecast(scenario)
        for i, row in enumerate(raw["forecast"]):
            row["timestamp"] = f"{date_str}T{i:02d}:00:00"
        return raw, "mock", [], note

    service_url = _get_service_url()
    if service_url:
        # In production with service binding: call remote forecasting service directly
        payload = {
            "scenario": scenario,
            "horizon": config.HORIZON_HOURS,
            "future_weather": weather_records,
            "allow_arbitrary_dates": True,
        }
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(f"{service_url}/predict", json=payload)
                resp.raise_for_status()
                raw = resp.json()
            return _round_rows(raw), "model", [], note
        except Exception as exc:
            log.exception("Production forecasting service for date %s failed: %s", date_str, exc)
            raise ForecastError(f"Forecasting service unavailable for {date_str}: {exc}") from exc

    # Local development mode: convert records to DataFrame for predict.py if pandas is present
    try:
        import pandas as pd  # lazy local import
        df_weather = pd.DataFrame(weather_records)
    except ImportError:
        df_weather = None

    try:
        with _lock:
            predict = _load_predict()
            with contextlib.redirect_stdout(io.StringIO()):
                raw = predict.generate_forecast(
                    input_data=df_weather,
                    horizon=config.HORIZON_HOURS,
                    scenario=scenario,
                    save_output=False,
                    allow_arbitrary_dates=True,
                )
        return _round_rows(raw), "model", [], note
    except Exception as exc:  # noqa: BLE001
        log.exception("Real forecast for date %s failed", date_str)
        if config.MODE == "real":
            raise ForecastError(f"Forecasting for {date_str} failed: {exc}") from exc
        raw = mock_data.get_mock_forecast(scenario)
        for i, row in enumerate(raw["forecast"]):
            row["timestamp"] = f"{date_str}T{i:02d}:00:00"
        return (
            raw,
            "mock",
            [f"Forecast model unavailable ({type(exc).__name__}); showing mock forecast."],
            note,
        )
