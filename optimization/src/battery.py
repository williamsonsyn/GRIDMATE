"""
battery.py — Battery parameter helpers for GridMate.

Validates, normalises and summarizes battery configuration so that
optimizer.py and network.py receive consistent, error-checked values.
Supports both full specification names (e.g. energy_capacity_kwh)
and convenient shorthands (e.g. capacity_kwh).
"""


def normalize_battery_config(battery: dict) -> dict:
    """Normalize battery dictionary to contain both full and shorthand keys.

    Parameters
    ----------
    battery : dict
        Battery section from configuration.

    Returns
    -------
    dict
        Normalized dictionary with unified access.
    """
    cap = battery.get("capacity_kwh")
    if cap is None:
        cap = battery.get("energy_capacity_kwh", 500)

    max_ch = battery.get("max_charge_kw")
    if max_ch is None:
        max_ch = battery.get("maximum_charge_kw", 100)

    max_dis = battery.get("max_discharge_kw")
    if max_dis is None:
        max_dis = battery.get("maximum_discharge_kw", 100)

    init_soc = battery.get("initial_soc_kwh")
    if init_soc is None:
        init_soc = battery.get("initial_state_of_charge", 200)

    min_soc = battery.get("min_soc_kwh")
    if min_soc is None:
        min_soc = battery.get("minimum_state_of_charge", 50)

    max_soc = battery.get("max_soc_kwh")
    if max_soc is None:
        max_soc = battery.get("maximum_state_of_charge", 500)

    ch_eff = battery.get("charge_efficiency", 0.95)
    dis_eff = battery.get("discharge_efficiency", 0.95)

    return {
        # Shorthand keys
        "capacity_kwh": cap,
        "max_charge_kw": max_ch,
        "max_discharge_kw": max_dis,
        "initial_soc_kwh": init_soc,
        "min_soc_kwh": min_soc,
        "max_soc_kwh": max_soc,
        "charge_efficiency": ch_eff,
        "discharge_efficiency": dis_eff,
        # Full spec keys
        "energy_capacity_kwh": cap,
        "maximum_charge_kw": max_ch,
        "maximum_discharge_kw": max_dis,
        "initial_state_of_charge": init_soc,
        "minimum_state_of_charge": min_soc,
        "maximum_state_of_charge": max_soc,
    }


def validate_battery_config(battery: dict) -> None:
    """Raise ValueError if battery configuration is inconsistent.

    Parameters
    ----------
    battery : dict
        Battery section from system_config.json / DEFAULT_CONFIG.
    """
    norm = normalize_battery_config(battery)
    cap     = norm["capacity_kwh"]
    max_ch  = norm["max_charge_kw"]
    max_dis = norm["max_discharge_kw"]
    init    = norm["initial_soc_kwh"]
    lo      = norm["min_soc_kwh"]
    hi      = norm["max_soc_kwh"]
    eff_c   = norm["charge_efficiency"]
    eff_d   = norm["discharge_efficiency"]

    if cap <= 0:
        raise ValueError("capacity_kwh must be positive.")
    if max_ch <= 0 or max_dis <= 0:
        raise ValueError("max_charge_kw and max_discharge_kw must be positive.")
    if not (0 <= lo <= init <= hi <= cap):
        raise ValueError(
            "Battery SOC settings must satisfy: "
            "0 <= min_soc_kwh <= initial_soc_kwh <= max_soc_kwh <= capacity_kwh"
        )
    if not (0 < eff_c <= 1):
        raise ValueError("charge_efficiency must be in (0, 1].")
    if not (0 < eff_d <= 1):
        raise ValueError("discharge_efficiency must be in (0, 1].")


def battery_summary(battery: dict) -> str:
    """Return a human-readable summary of battery parameters."""
    norm = normalize_battery_config(battery)
    return (
        f"Battery: {norm['capacity_kwh']} kWh capacity | "
        f"Charge/Discharge: {norm['max_charge_kw']} / "
        f"{norm['max_discharge_kw']} kW | "
        f"SOC: {norm['min_soc_kwh']}–{norm['max_soc_kwh']} kWh "
        f"(init {norm['initial_soc_kwh']} kWh) | "
        f"Efficiency: {norm['charge_efficiency']*100:.0f}% / "
        f"{norm['discharge_efficiency']*100:.0f}%"
    )
