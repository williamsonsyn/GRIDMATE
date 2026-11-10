"""Weather service: fetches Open-Meteo weather or historical average.

Pure Python implementation without mandatory runtime numpy/pandas dependencies.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date, datetime
import json
import logging
from pathlib import Path
import statistics
from typing import Any
import urllib.error
import urllib.request

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

_HISTORY_CACHE: list[dict[str, Any]] | None = None


def _load_history() -> list[dict[str, Any]]:
    global _HISTORY_CACHE
    if _HISTORY_CACHE is not None:
        return _HISTORY_CACHE

    train_path = config.REPO_ROOT / "forecasting_real_data" / "data" / "training_dataset.csv"
    test_path = config.REPO_ROOT / "forecasting_real_data" / "data" / "testing_dataset.csv"

    rows: list[dict[str, Any]] = []
    for path in (train_path, test_path):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        rows.append(r)
            except Exception as exc:
                log.warning("Could not read %s: %s", path, exc)

    if not rows:
        raise FileNotFoundError("Historical weather datasets not found.")

    _HISTORY_CACHE = rows
    return _HISTORY_CACHE


def get_historical_average_weather(date_str: str) -> list[dict[str, Any]]:
    """Generate 24 hours of weather using historical data for the same day of the year."""
    target_dt = datetime.strptime(date_str, "%Y-%m-%d")
    target_doy = str(target_dt.timetuple().tm_yday)
    target_month = str(target_dt.month)

    df_h = _load_history()

    # Try matching exact day_of_year
    matching = [r for r in df_h if str(r.get("day_of_year")) == target_doy]
    if len(matching) < 24:
        # Fall back to matching month
        matching = [r for r in df_h if str(r.get("month")) == target_month]
        if len(matching) < 24:
            matching = df_h

    # Group by hour to get typical 24-hour hourly profile
    numeric_cols = [
        "solar_irradiance", "temperature", "humidity", "pressure",
        "wind_speed", "wind_direction", "rainfall", "cloud_cover", "water_flow"
    ]

    by_hour: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in matching:
        try:
            h = int(r.get("hour", 0))
            by_hour[h].append(r)
        except (ValueError, TypeError):
            continue

    hourly_medians: dict[int, dict[str, float]] = {}
    for h in range(24):
        h_rows = by_hour.get(h, matching)
        medians: dict[str, float] = {}
        for col in numeric_cols:
            vals: list[float] = []
            for r in h_rows:
                v = r.get(col)
                if v is not None and v != "":
                    try:
                        vals.append(float(v))
                    except ValueError:
                        pass
            medians[col] = statistics.median(vals) if vals else 0.0
        hourly_medians[h] = medians

    rows: list[dict[str, Any]] = []
    for h in range(24):
        m = hourly_medians[h]
        ts_str = f"{date_str}T{h:02d}:00:00"

        sol = round(max(0.0, float(m.get("solar_irradiance", 0.0))), 2)
        tmp = round(float(m.get("temperature", 25.0)), 2)
        hum = round(min(100.0, max(0.0, float(m.get("humidity", 70.0)))), 1)
        prs = round(max(10.0, float(m.get("pressure", 1005.0))), 1)
        ws = round(max(0.0, float(m.get("wind_speed", 2.0))), 2)
        wd = round(float(m.get("wind_direction", 180.0)) % 360.0, 1)
        rn = round(max(0.0, float(m.get("rainfall", 0.0))), 2)
        cld = round(min(100.0, max(0.0, float(m.get("cloud_cover", 20.0)))), 1)
        wf = round(max(0.0, float(m.get("water_flow", 0.4))), 2)

        rows.append({
            "timestamp": ts_str,
            "solar_irradiance": sol,
            "temperature": tmp,
            "humidity": hum,
            "pressure": prs,
            "wind_speed": ws,
            "wind_direction": wd,
            "rainfall": rn,
            "cloud_cover": cld,
            "water_flow": wf,
        })

    return rows


def fetch_open_meteo(date_str: str) -> list[dict[str, Any]] | None:
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
    target_doy = str(target_dt.timetuple().tm_yday)
    df_h = _load_history()
    doy_slice = [r for r in df_h if str(r.get("day_of_year")) == target_doy]
    if len(doy_slice) < 24:
        doy_slice = [r for r in df_h if str(r.get("month")) == str(target_dt.month)]

    wf_by_hour: dict[int, list[float]] = defaultdict(list)
    for r in doy_slice:
        try:
            h = int(r.get("hour", 0))
            wf_by_hour[h].append(float(r.get("water_flow", 0.4)))
        except (ValueError, TypeError):
            pass

    rows: list[dict[str, Any]] = []
    for h in range(24):
        solar = float(hourly.get("shortwave_radiation", [0.0] * 24)[h] or 0.0)
        temp = float(hourly.get("temperature_2m", [25.0] * 24)[h] or 25.0)
        hum = float(hourly.get("relative_humidity_2m", [70.0] * 24)[h] or 70.0)
        pres = float(hourly.get("surface_pressure", [1005.0] * 24)[h] or 1005.0)
        ws = float(hourly.get("wind_speed_10m", [2.0] * 24)[h] or 2.0)
        wd = float(hourly.get("wind_direction_10m", [180.0] * 24)[h] or 180.0)
        rain = float(hourly.get("precipitation", [0.0] * 24)[h] or 0.0)
        cloud = float(hourly.get("cloud_cover", [20.0] * 24)[h] or 20.0)

        wf_vals = wf_by_hour.get(h, [])
        wf = statistics.median(wf_vals) if wf_vals else 0.4

        rows.append({
            "timestamp": f"{date_str}T{h:02d}:00:00",
            "solar_irradiance": round(max(0.0, solar), 2),
            "temperature": round(temp, 2),
            "humidity": round(min(100.0, max(0.0, hum)), 1),
            "pressure": round(max(10.0, pres), 1),
            "wind_speed": round(max(0.0, ws), 2),
            "wind_direction": round(wd % 360.0, 1),
            "rainfall": round(max(0.0, rain), 2),
            "cloud_cover": round(min(100.0, max(0.0, cloud)), 1),
            "water_flow": round(max(0.0, float(wf)), 2),
        })

    return rows


def get_weather_for_date(date_str: str) -> tuple[list[dict[str, Any]], str, str | None]:
    """Retrieve weather inputs for target date as list of 24 hourly records.

    Returns:
        (weather_records, source, note)
        source: 'open_meteo' or 'historical_average'
        note: 'estimated from historical average' if historical average used
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    today = date.today()
    diff_days = (target_date - today).days

    # Open-Meteo free forecast supports up to 16 days ahead
    if 0 <= diff_days <= 16:
        records = fetch_open_meteo(date_str)
        if records is not None:
            return records, "open_meteo", None

    # > 16 days ahead OR Open-Meteo unavailable -> historical average
    records_hist = get_historical_average_weather(date_str)
    return records_hist, "historical_average", "estimated from historical average"
