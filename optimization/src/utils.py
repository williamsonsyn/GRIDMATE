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
