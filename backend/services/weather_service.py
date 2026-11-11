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

try:
    from .. import config
except (ImportError, ValueError):
    import config  # type: ignore[no-redef]

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

# 24-hour historical median environmental baseline for Lonavala (derived from historical dataset)
LONAVALA_HOURLY_BASELINE: dict[int, dict[str, float]] = {
    0: {"solar_irradiance": 0.0, "temperature": 24.87, "humidity": 90.56, "pressure": 997.0, "wind_speed": 2.71, "wind_direction": 228.35, "rainfall": 0.06, "cloud_cover": 77.0, "water_flow": 0.38},
    1: {"solar_irradiance": 0.0, "temperature": 24.74, "humidity": 91.06, "pressure": 996.4, "wind_speed": 2.8, "wind_direction": 224.3, "rainfall": 0.06, "cloud_cover": 83.0, "water_flow": 0.38},
    2: {"solar_irradiance": 0.0, "temperature": 24.59, "humidity": 91.59, "pressure": 996.0, "wind_speed": 2.83, "wind_direction": 222.75, "rainfall": 0.06, "cloud_cover": 92.0, "water_flow": 0.38},
    3: {"solar_irradiance": 0.0, "temperature": 24.49, "humidity": 92.0, "pressure": 995.85, "wind_speed": 2.79, "wind_direction": 220.1, "rainfall": 0.06, "cloud_cover": 94.0, "water_flow": 0.38},
    4: {"solar_irradiance": 0.0, "temperature": 24.44, "humidity": 92.02, "pressure": 996.2, "wind_speed": 2.75, "wind_direction": 213.8, "rainfall": 0.05, "cloud_cover": 91.0, "water_flow": 0.38},
    5: {"solar_irradiance": 0.0, "temperature": 24.4, "humidity": 92.04, "pressure": 996.8, "wind_speed": 2.71, "wind_direction": 196.4, "rainfall": 0.04, "cloud_cover": 95.0, "water_flow": 0.38},
    6: {"solar_irradiance": 36.78, "temperature": 25.08, "humidity": 88.1, "pressure": 997.5, "wind_speed": 3.01, "wind_direction": 184.5, "rainfall": 0.05, "cloud_cover": 90.0, "water_flow": 0.38},
    7: {"solar_irradiance": 148.48, "temperature": 26.22, "humidity": 81.39, "pressure": 998.1, "wind_speed": 3.66, "wind_direction": 194.9, "rainfall": 0.04, "cloud_cover": 72.0, "water_flow": 0.38},
    8: {"solar_irradiance": 307.0, "temperature": 27.59, "humidity": 75.86, "pressure": 998.6, "wind_speed": 3.98, "wind_direction": 224.6, "rainfall": 0.04, "cloud_cover": 72.0, "water_flow": 0.38},
    9: {"solar_irradiance": 483.45, "temperature": 28.52, "humidity": 71.75, "pressure": 998.6, "wind_speed": 3.88, "wind_direction": 235.5, "rainfall": 0.04, "cloud_cover": 67.0, "water_flow": 0.38},
    10: {"solar_irradiance": 611.17, "temperature": 29.66, "humidity": 66.06, "pressure": 998.2, "wind_speed": 3.68, "wind_direction": 242.6, "rainfall": 0.03, "cloud_cover": 61.0, "water_flow": 0.38},
    11: {"solar_irradiance": 696.03, "temperature": 30.75, "humidity": 63.5, "pressure": 997.5, "wind_speed": 3.48, "wind_direction": 251.7, "rainfall": 0.03, "cloud_cover": 58.0, "water_flow": 0.38},
    12: {"solar_irradiance": 701.17, "temperature": 31.32, "humidity": 61.95, "pressure": 996.7, "wind_speed": 3.83, "wind_direction": 260.2, "rainfall": 0.03, "cloud_cover": 73.0, "water_flow": 0.38},
    13: {"solar_irradiance": 622.17, "temperature": 31.56, "humidity": 59.91, "pressure": 995.8, "wind_speed": 4.37, "wind_direction": 267.4, "rainfall": 0.04, "cloud_cover": 72.0, "water_flow": 0.38},
    14: {"solar_irradiance": 506.77, "temperature": 31.19, "humidity": 59.76, "pressure": 995.3, "wind_speed": 4.87, "wind_direction": 271.4, "rainfall": 0.04, "cloud_cover": 82.0, "water_flow": 0.38},
    15: {"solar_irradiance": 359.15, "temperature": 30.79, "humidity": 61.34, "pressure": 995.0, "wind_speed": 5.08, "wind_direction": 275.6, "rainfall": 0.04, "cloud_cover": 81.0, "water_flow": 0.38},
    16: {"solar_irradiance": 194.85, "temperature": 29.87, "humidity": 62.1, "pressure": 995.1, "wind_speed": 5.09, "wind_direction": 278.6, "rainfall": 0.03, "cloud_cover": 77.0, "water_flow": 0.38},
    17: {"solar_irradiance": 64.75, "temperature": 27.9, "humidity": 74.91, "pressure": 995.6, "wind_speed": 4.49, "wind_direction": 283.7, "rainfall": 0.03, "cloud_cover": 79.0, "water_flow": 0.38},
    18: {"solar_irradiance": 1.73, "temperature": 26.51, "humidity": 83.09, "pressure": 996.2, "wind_speed": 3.7, "wind_direction": 285.3, "rainfall": 0.02, "cloud_cover": 67.0, "water_flow": 0.38},
    19: {"solar_irradiance": 0.0, "temperature": 25.93, "humidity": 85.78, "pressure": 996.9, "wind_speed": 3.23, "wind_direction": 283.5, "rainfall": 0.02, "cloud_cover": 80.0, "water_flow": 0.38},
    20: {"solar_irradiance": 0.0, "temperature": 25.77, "humidity": 87.15, "pressure": 997.5, "wind_speed": 2.86, "wind_direction": 273.6, "rainfall": 0.03, "cloud_cover": 80.0, "water_flow": 0.38},
    21: {"solar_irradiance": 0.0, "temperature": 25.57, "humidity": 88.71, "pressure": 997.9, "wind_speed": 2.72, "wind_direction": 239.8, "rainfall": 0.03, "cloud_cover": 76.0, "water_flow": 0.38},
    22: {"solar_irradiance": 0.0, "temperature": 25.23, "humidity": 90.13, "pressure": 997.9, "wind_speed": 2.67, "wind_direction": 231.7, "rainfall": 0.03, "cloud_cover": 78.0, "water_flow": 0.38},
    23: {"solar_irradiance": 0.0, "temperature": 24.96, "humidity": 90.98, "pressure": 997.6, "wind_speed": 2.67, "wind_direction": 230.0, "rainfall": 0.05, "cloud_cover": 78.0, "water_flow": 0.38},
}

_HISTORY_CACHE: list[dict[str, Any]] | None = None
_WEATHER_CACHE: dict[str, list[dict[str, Any]]] = {}


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

    _HISTORY_CACHE = rows
    return _HISTORY_CACHE


def get_historical_average_weather(date_str: str) -> list[dict[str, Any]]:
    """Generate 24 hours of weather using historical data for the same day of the year,

    or the precomputed Lonavala hourly baseline if raw datasets are not present on disk.
    """
    df_h = _load_history()

    hourly_medians: dict[int, dict[str, float]] = {}

    if not df_h:
        # Standalone container deployment without local CSVs -> use embedded baseline
        hourly_medians = {h: dict(LONAVALA_HOURLY_BASELINE[h]) for h in range(24)}
    else:
        target_dt = datetime.strptime(date_str, "%Y-%m-%d")
        target_doy = str(target_dt.timetuple().tm_yday)
        target_month = str(target_dt.month)

        matching = [r for r in df_h if str(r.get("day_of_year")) == target_doy]
        if len(matching) < 24:
            matching = [r for r in df_h if str(r.get("month")) == target_month]
            if len(matching) < 24:
                matching = df_h

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
                medians[col] = statistics.median(vals) if vals else LONAVALA_HOURLY_BASELINE[h].get(col, 0.0)
            hourly_medians[h] = medians

    rows: list[dict[str, Any]] = []
    for h in range(24):
        m = hourly_medians.get(h, LONAVALA_HOURLY_BASELINE[h])
        ts_str = f"{date_str}T{h:02d}:00:00"

        sol = round(max(0.0, float(m.get("solar_irradiance", 0.0))), 2)
        tmp = round(float(m.get("temperature", 25.0)), 2)
        hum = round(min(100.0, max(0.0, float(m.get("humidity", 70.0)))), 1)
        prs = round(max(10.0, float(m.get("pressure", 1005.0))), 1)
        ws = round(max(0.0, float(m.get("wind_speed", 2.0))), 2)
        wd = round(float(m.get("wind_direction", 180.0)) % 360.0, 1)
        rn = round(max(0.0, float(m.get("rainfall", 0.0))), 2)
        cld = round(min(100.0, max(0.0, float(m.get("cloud_cover", 20.0)))), 1)
        wf = round(max(0.0, float(m.get("water_flow", 0.38))), 2)

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
    if date_str in _WEATHER_CACHE:
        return _WEATHER_CACHE[date_str]

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
            wf_by_hour[h].append(float(r.get("water_flow", 0.38)))
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
        wf = statistics.median(wf_vals) if wf_vals else LONAVALA_HOURLY_BASELINE.get(h, {}).get("water_flow", 0.38)

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

    _WEATHER_CACHE[date_str] = rows
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
