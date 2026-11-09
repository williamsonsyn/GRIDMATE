"""
metrics.py — Post-optimisation metric calculations for GridMate.

All metrics are derived from actual optimisation results.
Definitions are documented here and in README.md.
"""


def calculate_metrics(
    total_load_kwh: float,
    total_grid_kwh: float,
    total_avail_kwh: float,
    total_curtailed_kwh: float,
    bat_charging_kwh: float,
    bat_discharging_kwh: float,
    bat_capacity_kwh: float,
    n_hours: int,
    emission_factor: float,
) -> dict:
    """Calculate all required dispatch metrics.

    Parameters
    ----------
    total_load_kwh : float
        Total energy demanded over the horizon (kWh).
    total_grid_kwh : float
        Total grid energy imported (kWh).
    total_avail_kwh : float
        Total available renewable energy (solar + wind + hydro, kWh).
    total_curtailed_kwh : float
        Total renewable energy curtailed (kWh).
    bat_charging_kwh : float
        Total energy charged into the battery (kWh, positive).
    bat_discharging_kwh : float
        Total energy discharged from the battery (kWh, positive).
    bat_capacity_kwh : float
        Battery energy capacity (kWh).
    n_hours : int
        Number of optimisation timesteps.
    emission_factor : float
        Grid CO₂ emission factor (kg CO₂ / kWh).

    Returns
    -------
    dict
        Metric values rounded to 2 decimal places.
    """

    # Renewable penetration
    # = energy supplied to load that is NOT from grid / total load
    # Note: battery may store grid energy, but as a prototype simplification
    # we treat all non-grid energy as renewable.
    non_grid_kwh = max(0.0, total_load_kwh - total_grid_kwh)
    renewable_penetration = (
        (non_grid_kwh / total_load_kwh) * 100.0 if total_load_kwh > 0 else 0.0
    )

    # Grid dependency
    # = grid energy / total load
    grid_dependency = (
        (total_grid_kwh / total_load_kwh) * 100.0 if total_load_kwh > 0 else 0.0
    )

    # Curtailment
    # = curtailed renewable / total available renewable
    curtailment_pct = (
        (total_curtailed_kwh / total_avail_kwh) * 100.0
        if total_avail_kwh > 0 else 0.0
    )

    # Battery utilisation
    # = (charge throughput + discharge throughput) / maximum possible throughput
    # Maximum throughput assumes the battery is fully cycled every hour.
    max_throughput = 2.0 * bat_capacity_kwh * n_hours
    bat_throughput = bat_charging_kwh + bat_discharging_kwh
    battery_utilisation = (
        (bat_throughput / max_throughput) * 100.0 if max_throughput > 0 else 0.0
    )

    # Estimated CO₂ avoided
    # = non-grid energy × assumed grid emission factor
    # ESTIMATE: actual CO₂ varies by time, mix and marginal generator.
    co2_avoided_kg = non_grid_kwh * emission_factor

    return {
        "renewable_penetration_percent": round(renewable_penetration, 2),
        "grid_dependency_percent":       round(grid_dependency,       2),
        "curtailment_percent":           round(curtailment_pct,       2),
        "battery_utilization_percent":   round(battery_utilisation,   2),
        "estimated_co2_avoided_kg":      round(co2_avoided_kg,        2),
    }


def calculate_cost_metrics(dispatch_rows, prices, *args, **kwargs) -> dict:
    """Calculate cost and savings metrics from hourly dispatch and grid prices.

    Treat each timestep as 1 hour (kW = kWh per step).

    Parameters
    ----------
    dispatch_rows : list of dict, pd.DataFrame, or pd.Series
        Hourly dispatch rows containing at least 'grid_kw' and 'load_kw'.
        Also supports legacy calls where grid_kw series is passed as the first
        argument with total_load_kwh passed in args.
    prices : list, array, pd.Series, or scalar
        Hourly grid price in Rs/kWh for each timestep.

    Returns
    -------
    dict
        - total_grid_cost_rs: sum over hours of grid_kw[t] * price[t] (round 2 decimals)
        - grid_only_cost_rs: baseline cost if entire load was grid-supplied at hourly prices (round 2 decimals)
        - baseline_cost_rs: alias for grid_only_cost_rs (round 2 decimals)
        - savings_rs: grid_only_cost_rs - total_grid_cost_rs (round 2 decimals)
        - savings_percent: savings_rs / grid_only_cost_rs * 100 (round 1 decimal)
        - average_cost_rs_per_kwh_served: total_grid_cost_rs / total load kWh (round 2 decimals)
        - grid_only_average_cost_rs_per_kwh: baseline price per kWh served (round 2 decimals)
        - label: prototype disclaimer string
    """
    # 1-hour timestep assumption: energy (kWh) = power (kW) * 1 hour.
    if isinstance(dispatch_rows, list):
        grid_kws = [float(r.get("grid_kw", 0.0)) for r in dispatch_rows]
        load_kws = [float(r.get("load_kw", 0.0)) for r in dispatch_rows]
    elif hasattr(dispatch_rows, "columns"):  # pd.DataFrame
        grid_kws = [float(x) for x in dispatch_rows["grid_kw"]]
        load_kws = [float(x) for x in dispatch_rows["load_kw"]]
    elif hasattr(dispatch_rows, "__iter__"):  # pd.Series or iterable (legacy positional support)
        grid_kws = [float(x) for x in dispatch_rows]
        if len(args) >= 1:
            total_load_kwh = float(args[0])
            # Evenly distribute total load across hours if individual load_kw not given
            n = len(grid_kws) if len(grid_kws) > 0 else 1
            load_kws = [total_load_kwh / n] * len(grid_kws)
        else:
            load_kws = [0.0] * len(grid_kws)
    else:
        raise TypeError(f"Unsupported dispatch_rows type: {type(dispatch_rows)}")

    # Extract price list matching dispatch length
    if isinstance(prices, (int, float)):
        prices_list = [float(prices)] * len(grid_kws)
    elif hasattr(prices, "tolist"):
        prices_list = [float(p) for p in prices.tolist()]
    else:
        prices_list = [float(p) for p in prices]

    if len(prices_list) != len(grid_kws):
        raise ValueError(
            f"Length mismatch: {len(prices_list)} prices vs {len(grid_kws)} dispatch rows"
        )

    # Actual cost: sum over hours of grid_kw[t] * price[t] * 1h
    total_grid_cost = sum(g * p for g, p in zip(grid_kws, prices_list))

    # Baseline cost: if legacy base_price was passed as 4th positional argument, use it;
    # otherwise compute hourly baseline where entire load is bought from grid at hourly prices.
    if len(args) >= 2:
        grid_only_cost = float(args[0]) * float(args[1])
        total_load_kwh = float(args[0])
    else:
        grid_only_cost = sum(l * p for l, p in zip(load_kws, prices_list))
        total_load_kwh = sum(load_kws)

    savings_rs = grid_only_cost - total_grid_cost

    if grid_only_cost > 0:
        savings_percent = (savings_rs / grid_only_cost) * 100.0
    else:
        savings_percent = 0.0

    if total_load_kwh > 0:
        average_cost_rs_per_kwh_served = total_grid_cost / total_load_kwh
        grid_only_average_cost_rs_per_kwh = grid_only_cost / total_load_kwh
    else:
        average_cost_rs_per_kwh_served = 0.0
        grid_only_average_cost_rs_per_kwh = 0.0

    label = (
        "Cost figures are prototype estimates based on assumed tariffs, "
        "not billing-grade values."
    )

    return {
        "total_grid_cost_rs": round(total_grid_cost, 2),
        "grid_only_cost_rs": round(grid_only_cost, 2),
        "baseline_cost_rs": round(grid_only_cost, 2),  # backward-compatibility alias
        "savings_rs": round(savings_rs, 2),
        "savings_percent": round(savings_percent, 1),
        "average_cost_rs_per_kwh_served": round(average_cost_rs_per_kwh_served, 2),
        "grid_only_average_cost_rs_per_kwh": round(grid_only_average_cost_rs_per_kwh, 2),
        "label": label,
    }
