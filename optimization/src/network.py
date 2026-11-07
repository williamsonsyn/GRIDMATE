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
    price_series_rs_per_kwh: pd.Series = None,
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
    price_series_rs_per_kwh : pd.Series, optional
        Hourly grid price in Rs/kWh indexed by the forecast timestamps.
        When supplied, the Grid generator receives a time-varying marginal
        cost (in Rs/MWh, as PyPSA operates in MW).  When ``None``, the flat
        ``cost_per_kwh`` / ``grid_cost_per_kwh`` value from *grid* is used.

    Returns
    -------
    pypsa.Network
        Network ready for net.optimize(solver_name="highs").

    Notes
    -----
    **Battery charging from grid:**
    This model does not explicitly prevent the battery from charging using
    grid power.  The optimiser will naturally avoid this in peak hours because
    the grid marginal cost is high, but may allow it during normal/solar hours
    when the ToD price is lower and storing cheap off-peak energy is economic.
    This is acceptable prototype behaviour; a production system would add an
    explicit constraint (e.g. a link or a custom constraint) to prevent it.

    **Unit scaling:**
    PyPSA works in MW internally.  All power values in *df* must already be
    in MW.  Prices from *price_series_rs_per_kwh* (Rs/kWh) are multiplied by
    1 000 to convert to Rs/MWh before being passed to PyPSA.
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
    grid_cap_mw = float(grid_cap_kw) / 1000.0

    # Resolve grid marginal cost — time-varying (ToD) or flat
    if price_series_rs_per_kwh is not None:
        # Convert Rs/kWh → Rs/MWh for PyPSA; keep Series index aligned with snapshots
        grid_marginal_cost = price_series_rs_per_kwh * 1000.0
    else:
        # Fallback: flat scalar (Rs/kWh → Rs/MWh)
        flat_cost = (
            grid.get("cost_per_kwh")
            if "cost_per_kwh" in grid
            else grid.get("grid_cost_per_kwh", 8.0)
        )
        grid_marginal_cost = float(flat_cost) * 1000.0

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

    # --- Grid import (time-varying or flat marginal cost) ---
    # PyPSA accepts a pd.Series indexed by snapshots for marginal_cost,
    # which creates a time-varying cost stored in net.generators_t.marginal_cost.
    net.add(
        "Generator", "Grid",
        bus="Main_Bus",
        carrier="grid",
        p_nom=grid_cap_mw,
        marginal_cost=grid_marginal_cost,
    )

    # --- Battery storage ---
    # marginal_cost=0.01 Rs/MWh is a small cycling penalty that prevents the
    # solver from charge/discharge cycling purely for numerical reasons.
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
