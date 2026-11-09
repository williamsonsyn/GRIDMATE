"""
utils.py — Utility helpers for GridMate optimisation module.

Provides lightweight functions used across optimizer.py, run_scenarios.py
and the test suite.
"""

import json
from pathlib import Path


def load_json(path: str | Path) -> dict:
    """Load a JSON file and return its contents as a dict.

    Parameters
    ----------
    path : str or Path
        Path to the JSON file.

    Returns
    -------
    dict
        Parsed JSON contents.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    with open(p, "r") as fh:
        return json.load(fh)


def save_json(data: dict, path: str | Path, indent: int = 4) -> None:
    """Write *data* to *path* as a formatted JSON file.

    Parent directories are created automatically.

    Parameters
    ----------
    data : dict
        Data to serialise.
    path : str or Path
        Destination file path.
    indent : int
        JSON indentation width (default 4).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        json.dump(data, fh, indent=indent)


def scale_forecast(base_forecast: dict, factors: dict) -> dict:
    """Return a copy of *base_forecast* with generation/load scaled by *factors*.

    Parameters
    ----------
    base_forecast : dict
        Original forecast in the standard input contract format.
    factors : dict
        Multipliers for each field, e.g.::

            {"solar": 0.3, "wind": 0.85, "hydro": 1.0, "load": 1.0}

    Returns
    -------
    dict
        Deep-copied and scaled forecast dict.
    """
    import json as _json
    scaled = _json.loads(_json.dumps(base_forecast))
    for hour in scaled["forecast"]:
        hour["solar_kw"] = hour["solar_kw"] * factors.get("solar", 1.0)
        hour["wind_kw"]  = hour["wind_kw"]  * factors.get("wind",  1.0)
        hour["hydro_kw"] = hour["hydro_kw"] * factors.get("hydro", 1.0)
        hour["load_kw"]  = hour["load_kw"]  * factors.get("load",  1.0)
    return scaled


def print_metrics_table(metrics: dict) -> None:
    """Pretty-print a metrics dict to stdout."""
    width = max(len(k) for k in metrics) + 2
    for key, val in metrics.items():
        print(f"  {key:<{width}}: {val}")


def build_grid_price_series(timestamps, grid_cfg: dict):
    """Return a pd.Series of grid prices (Rs/kWh) indexed by *timestamps*.

    Uses the time-of-day (ToD) tariff structure from ``grid_cfg["tod"]`` when
    present.  Falls back to a flat price equal to
    ``base_energy_charge_rs_per_kwh`` (or the legacy ``cost_per_kwh`` /
    ``grid_cost_per_kwh`` key) when ``"tod"`` is absent.

    ToD slot definitions
    --------------------
    Slot      Hours     Season         Multiplier
    normal    00–09     both           1.00
    solar     09–17     Apr–Sep        0.85  (multiplier_apr_sep)
              09–17     Oct–Mar        0.75  (multiplier_oct_mar)
    peak      17–24     both           1.20

    These values are **prototype assumptions** modelled on the MERC/MSEDCL 2026
    ToD structure.  Verify against the official tariff order before production
    use.

    Parameters
    ----------
    timestamps : array-like of pandas Timestamp
        Forecast timestamps (the DataFrame index).
    grid_cfg : dict
        Grid section from system_config.json.

    Returns
    -------
    pd.Series
        Price in Rs/kWh, indexed by *timestamps*.

    Raises
    ------
    ValueError
        If an hour is not covered by exactly one ToD slot.
    """
    import pandas as pd

    # Resolve base price — support several legacy key names
    base = grid_cfg.get("base_energy_charge_rs_per_kwh")
    if base is None:
        base = grid_cfg.get("cost_per_kwh", grid_cfg.get("grid_cost_per_kwh", 8.0))
    base = float(base)

    tod = grid_cfg.get("tod")
    if tod is None:
        # Backward-compatible flat price when "tod" key is absent
        return pd.Series(base, index=timestamps, dtype=float)

    prices = []
    for ts in timestamps:
        hour = ts.hour
        month = ts.month
        # April–September → apr_sep season; October–March → oct_mar season
        season = "apr_sep" if 4 <= month <= 9 else "oct_mar"

        matched_price = None
        match_count = 0
        for slot_name, slot in tod.items():
            if slot["from_hour"] <= hour < slot["to_hour"]:
                match_count += 1
                if slot_name == "solar":
                    multiplier = float(
                        slot.get(f"multiplier_{season}", slot.get("multiplier", 1.0))
                    )
                else:
                    multiplier = float(slot.get("multiplier", 1.0))
                matched_price = base * multiplier

        if match_count == 0:
            raise ValueError(
                f"Hour {hour} at timestamp {ts} is not covered by any ToD slot. "
                "Check the 'tod' section in system_config.json."
            )
        if match_count > 1:
            raise ValueError(
                f"Hour {hour} at timestamp {ts} is covered by multiple ToD slots "
                f"({match_count}). ToD slots must not overlap."
            )
        prices.append(matched_price)

    return pd.Series(prices, index=timestamps, dtype=float)
