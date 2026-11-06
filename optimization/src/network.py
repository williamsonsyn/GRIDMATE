"""
network.py — PyPSA network builder for GridMate.

Separates network construction from the optimisation loop so that
optimizer.py stays readable.  The optimizer calls build_network() and
receives a fully-configured pypsa.Network ready for net.optimize().
"""

import pypsa
import pandas as pd

try:
    from .battery import normalize_battery_config
except ImportError:
    from battery import normalize_battery_config


def build_network(
    df: pd.DataFrame,
    battery: dict,
    grid: dict,
) -> pypsa.Network:
    """Build and return a configured PyPSA network.

    Parameters
    ----------
    df : pd.DataFrame
        Hourly forecast with columns solar_kw, wind_kw, hydro_kw, load_kw
        (all in MW, indexed by timestamp).
    battery : dict
        Battery configuration from system_config.json (kW / kWh units).
    grid : dict
        Grid configuration from system_config.json (kW / kWh units).

    Returns
    -------
    pypsa.Network
        Network ready for net.optimize(solver_name="highs").
    """
    bat = normalize_battery_config(battery)

    bat_cap_mwh    = bat["capacity_kwh"]    / 1000.0
    bat_max_ch_mw  = bat["max_charge_kw"]   / 1000.0
    bat_max_dis_mw = bat["max_discharge_kw"] / 1000.0
    bat_init_mwh   = bat["initial_soc_kwh"] / 1000.0
    bat_min_mwh    = bat["min_soc_kwh"]     / 1000.0
    bat_max_mwh    = bat["max_soc_kwh"]     / 1000.0
    bat_power_mw   = max(bat_max_ch_mw, bat_max_dis_mw)

    grid_cap_kw = grid.get("capacity_kw") or grid.get("grid_capacity_kw", 1000.0)
    grid_cost = grid.get("cost_per_kwh") if "cost_per_kwh" in grid else grid.get("grid_cost_per_kwh", 8.0)
    grid_cap_mw = float(grid_cap_kw) / 1000.0

    net = pypsa.Network()
    net.set_snapshots(df.index)

    # Single AC bus representing the Lonavala microgrid
    net.add("Bus", "Main_Bus", carrier="AC")

    # --- Renewable generators (zero marginal cost) ---
    for src in ("solar", "wind", "hydro"):
        avail  = df[f"{src}_kw"]
        cap_mw = max(float(avail.max()), 1e-6)
        net.add(
            "Generator", src,
            bus="Main_Bus",
            carrier=src,
            p_nom=cap_mw,
            p_max_pu=avail / cap_mw,
            marginal_cost=0.0,
        )

    # --- Grid import (costly backup) ---
    net.add(
        "Generator", "Grid",
        bus="Main_Bus",
        carrier="grid",
        p_nom=grid_cap_mw,
        marginal_cost=float(grid_cost) * 1000.0,
    )

    # --- Battery storage ---
    net.add(
        "StorageUnit", "Battery",
        bus="Main_Bus",
        carrier="battery",
        p_nom=bat_power_mw,
        max_hours=bat_cap_mwh / bat_power_mw,
        p_min_pu=-(bat_max_ch_mw  / bat_power_mw),
        p_max_pu= (bat_max_dis_mw / bat_power_mw),
        state_of_charge_initial=bat_init_mwh,
        state_of_charge_min=bat_min_mwh,
        state_of_charge_max=bat_max_mwh,
        efficiency_store=bat["charge_efficiency"],
        efficiency_dispatch=bat["discharge_efficiency"],
        marginal_cost=0.01,
    )

    # Sanitize network components to register carrier carriers cleanly
    net.sanitize()

    # --- Load ---
    net.add(
        "Load", "Electricity_Demand",
        bus="Main_Bus",
        p_set=df["load_kw"],
    )

    # Cyclic SOC: battery should end where it started
    net.storage_units_t.state_of_charge_set.loc[
        df.index[-1], "Battery"
    ] = bat_init_mwh

    return net
