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
