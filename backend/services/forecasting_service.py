"""Forecasting service: wraps Member 1's generate_forecast()."""
from __future__ import annotations

import contextlib
import io
import logging
import sys
from threading import Lock
from typing import Any

from .. import config
from . import mock_data

log = logging.getLogger(__name__)
JsonDict = dict[str, Any]
_lock = Lock()


class ForecastError(RuntimeError):
    """Raised when the forecast cannot be produced."""


def _load_predict() -> Any:
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


def get_real_forecast(scenario: str) -> JsonDict:
    with _lock:
        predict = _load_predict()
        with contextlib.redirect_stdout(io.StringIO()):
            raw = predict.generate_forecast(
                horizon=config.HORIZON_HOURS, scenario=scenario, save_output=False
            )
    return _round_rows(raw)


def get_forecast(scenario: str) -> tuple[JsonDict, str, list[str]]:
    """Return (forecast, source, warnings). Source is 'model' or 'mock'."""
    if config.MODE == "mock":
        return mock_data.get_mock_forecast(scenario), "mock", []
    try:
        return get_real_forecast(scenario), "model", []
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

    df_weather, weather_src, note = get_weather_for_date(date_str)
    if config.MODE == "mock":
        raw = mock_data.get_mock_forecast(scenario)
        for i, row in enumerate(raw["forecast"]):
            row["timestamp"] = f"{date_str}T{i:02d}:00:00"
        return raw, "mock", [], note

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

