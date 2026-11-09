"""Weather service: fetches Open-Meteo weather or historical average."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import config

log = logging.getLogger(__name__)

LONAVALA_LAT = 18.7557
LONAVALA_LON = 73.4091

REQUIRED_FUTURE_COLS = [
    "timestamp",
    "solar_irradiance",
    "temperature",
    "humidity",
    "pressure",
    "wind_speed",
    "wind_direction",
    "rainfall",
    "cloud_cover",
    "water_flow",
]

_HISTORY_CACHE: pd.DataFrame | None = None


def _load_history() -> pd.DataFrame:
    global _HISTORY_CACHE
    if _HISTORY_CACHE is not None:
        return _HISTORY_CACHE

    train_path = config.REPO_ROOT / "forecasting_real_data" / "data" / "training_dataset.csv"
    test_path = config.REPO_ROOT / "forecasting_real_data" / "data" / "testing_dataset.csv"

    frames = []
    if train_path.exists():
        frames.append(pd.read_csv(train_path))
    if test_path.exists():
        frames.append(pd.read_csv(test_path))

    if not frames:
        raise FileNotFoundError("Historical weather datasets not found.")

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    _HISTORY_CACHE = df
    return _HISTORY_CACHE


def get_historical_average_weather(date_str: str) -> pd.DataFrame:
    """Generate 24 hours of weather using historical data for the same day of the year."""
    target_dt = datetime.strptime(date_str, "%Y-%m-%d")
    target_doy = target_dt.timetuple().tm_yday
    target_month = target_dt.month

    df_h = _load_history()

    # Try matching exact day_of_year
    matching = df_h[df_h["day_of_year"] == target_doy]
    if len(matching) < 24:
        # Fall back to matching month
        matching = df_h[df_h["month"] == target_month]
        if len(matching) < 24:
            matching = df_h

    # Group by hour to get typical 24-hour hourly profile
    numeric_cols = [
        "solar_irradiance", "temperature", "humidity", "pressure",
        "wind_speed", "wind_direction", "rainfall", "cloud_cover", "water_flow"
    ]
    hourly = matching.groupby("hour")[numeric_cols].median()

    rows: list[dict[str, Any]] = []
    for h in range(24):
        ts_str = f"{date_str}T{h:02d}:00:00"
        if h in hourly.index:
            row_dict = hourly.loc[h].to_dict()
        else:
            row_dict = {c: float(matching[c].median()) for c in numeric_cols}

        row_dict["timestamp"] = ts_str
        row_dict["solar_irradiance"] = round(float(max(0.0, row_dict.get("solar_irradiance", 0.0))), 2)
        row_dict["temperature"] = round(float(row_dict.get("temperature", 25.0)), 2)
        row_dict["humidity"] = round(float(np.clip(row_dict.get("humidity", 70.0), 0.0, 100.0)), 1)
        row_dict["pressure"] = round(float(max(10.0, row_dict.get("pressure", 1005.0))), 1)
        row_dict["wind_speed"] = round(float(max(0.0, row_dict.get("wind_speed", 2.0))), 2)
        row_dict["wind_direction"] = round(float(row_dict.get("wind_direction", 180.0) % 360.0), 1)
        row_dict["rainfall"] = round(float(max(0.0, row_dict.get("rainfall", 0.0))), 2)
        row_dict["cloud_cover"] = round(float(np.clip(row_dict.get("cloud_cover", 20.0), 0.0, 100.0)), 1)
        row_dict["water_flow"] = round(float(max(0.0, row_dict.get("water_flow", 0.4))), 2)
        rows.append(row_dict)

    return pd.DataFrame(rows)[REQUIRED_FUTURE_COLS]


def fetch_open_meteo(date_str: str) -> pd.DataFrame | None:
    """Fetch hourly weather from Open-Meteo for Lonavala on date_str."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LONAVALA_LAT}&longitude={LONAVALA_LON}"
        f"&hourly=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m,wind_direction_10m,"
        f"precipitation,cloud_cover,shortwave_radiation"
        f"&wind_speed_unit=ms&start_date={date_str}&end_date={date_str}"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GridMate/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        log.warning("Open-Meteo request failed (%s): %s", type(exc).__name__, exc)
        return None

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if len(times) != 24:
        log.warning("Open-Meteo returned %d hours instead of 24", len(times))
        return None

    # Get water_flow from historical context for this day of year
    target_dt = datetime.strptime(date_str, "%Y-%m-%d")
    target_doy = target_dt.timetuple().tm_yday
    df_h = _load_history()
    doy_slice = df_h[df_h["day_of_year"] == target_doy]
    if len(doy_slice) < 24:
        doy_slice = df_h[df_h["month"] == target_dt.month]
    water_flow_hourly = doy_slice.groupby("hour")["water_flow"].median().to_dict()

    rows: list[dict[str, Any]] = []
    for h in range(24):
        # Open-Meteo gives shortwave_radiation in W/m² (Global Horizontal Irradiance)
        solar = float(hourly.get("shortwave_radiation", [0.0] * 24)[h] or 0.0)
        temp = float(hourly.get("temperature_2m", [25.0] * 24)[h] or 25.0)
        hum = float(hourly.get("relative_humidity_2m", [70.0] * 24)[h] or 70.0)
        pres = float(hourly.get("surface_pressure", [1005.0] * 24)[h] or 1005.0)
        ws = float(hourly.get("wind_speed_10m", [2.0] * 24)[h] or 2.0)
        wd = float(hourly.get("wind_direction_10m", [180.0] * 24)[h] or 180.0)
        rain = float(hourly.get("precipitation", [0.0] * 24)[h] or 0.0)
        cloud = float(hourly.get("cloud_cover", [20.0] * 24)[h] or 20.0)
        wf = float(water_flow_hourly.get(h, 0.4))

        rows.append({
            "timestamp": f"{date_str}T{h:02d}:00:00",
            "solar_irradiance": round(max(0.0, solar), 2),
            "temperature": round(temp, 2),
            "humidity": round(float(np.clip(hum, 0.0, 100.0)), 1),
            "pressure": round(max(10.0, pres), 1),
            "wind_speed": round(max(0.0, ws), 2),
            "wind_direction": round(wd % 360.0, 1),
            "rainfall": round(max(0.0, rain), 2),
            "cloud_cover": round(float(np.clip(cloud, 0.0, 100.0)), 1),
            "water_flow": round(max(0.0, wf), 2),
        })

    return pd.DataFrame(rows)[REQUIRED_FUTURE_COLS]


def get_weather_for_date(date_str: str) -> tuple[pd.DataFrame, str, str | None]:
    """Retrieve weather inputs for target date.

    Returns:
        (df_weather, source, note)
        source: 'open_meteo' or 'historical_average'
        note: 'estimated from historical average' if historical average used
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    today = date.today()
    diff_days = (target_date - today).days

    # Open-Meteo free forecast supports up to 16 days ahead
    if 0 <= diff_days <= 16:
        df = fetch_open_meteo(date_str)
        if df is not None:
            return df, "open_meteo", None

    # > 16 days ahead OR Open-Meteo unavailable -> historical average
    df_hist = get_historical_average_weather(date_str)
    return df_hist, "historical_average", "estimated from historical average"
