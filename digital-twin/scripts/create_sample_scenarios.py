"""
create_sample_scenarios.py
Generates validated sample dispatch JSON files for all required scenarios:
- normal.json
- cloudy.json
- heavy_monsoon.json
- high_wind.json
- peak_demand.json
- sample_dispatch.json (baseline 24-hour dispatch schedule)

All files follow the exact GRIDMATE_ARCHITECTURE.md dispatch contract:
{
  "location": "Lonavala",
  "dispatch": [...],
  "metrics": {...}
}

Battery sign convention:
battery_kw > 0 : Discharging (supplying power)
battery_kw < 0 : Charging (absorbing power)
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCENARIO_DIR = BASE_DIR / "data" / "scenarios"
DATA_DIR = BASE_DIR / "data"
SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

SIMULATION_NOTE = "Simulated prototype dispatch. Illustrative demo data."

SCENARIOS = {
    "normal": {
        "scenario_id": "normal",
        "scenario_name": "Normal Day",
        "description": "Baseline sunny conditions with balanced solar, wind, and hydro generation.",
        "row": {
            "timestamp": "2026-10-01T12:00:00",
            "solar_kw": 420.0,
            "wind_kw": 180.0,
            "hydro_kw": 250.0,
            "battery_kw": 50.0,       # discharging 50 kW
            "grid_kw": 0.0,           # grid not supplying
            "load_kw": 900.0,
            "curtailment_kw": 0.0,
            "battery_soc_kwh": 550.0
        },
        "metrics": {
            "renewable_penetration_percent": 100.0,
            "grid_dependency_percent": 0.0,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 20.0,
            "estimated_co2_avoided_kg": 738.0
        }
    },
    "cloudy": {
        "scenario_id": "cloudy",
        "scenario_name": "Cloudy Day",
        "description": "Reduced solar irradiance with battery discharge and grid support.",
        "row": {
            "timestamp": "2026-10-01T12:00:00",
            "solar_kw": 140.0,
            "wind_kw": 160.0,
            "hydro_kw": 260.0,
            "battery_kw": 180.0,      # discharging 180 kW
            "grid_kw": 160.0,         # grid supplying 160 kW
            "load_kw": 900.0,
            "curtailment_kw": 0.0,
            "battery_soc_kwh": 370.0
        },
        "metrics": {
            "renewable_penetration_percent": 82.2,
            "grid_dependency_percent": 17.8,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 72.0,
            "estimated_co2_avoided_kg": 606.8
        }
    },
    "heavy_monsoon": {
        "scenario_id": "heavy_monsoon",
        "scenario_name": "Heavy Monsoon",
        "description": "High precipitation, maximum hydro capacity (400 kW), minimal solar, battery charging, and grid import.",
        "row": {
            "timestamp": "2026-10-01T12:00:00",
            "solar_kw": 20.0,         # minimal overcast solar
            "wind_kw": 210.0,        # monsoon gusts
            "hydro_kw": 400.0,       # full 400 kW hydro capacity
            "battery_kw": -60.0,      # charging -60 kW
            "grid_kw": 330.0,        # grid active supplying 330 kW
            "load_kw": 900.0,
            "curtailment_kw": 0.0,
            "battery_soc_kwh": 760.0
        },
        "metrics": {
            "renewable_penetration_percent": 63.3,
            "grid_dependency_percent": 36.7,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 24.0,
            "estimated_co2_avoided_kg": 516.6
        }
    },
    "high_wind": {
        "scenario_id": "high_wind",
        "scenario_name": "High Wind",
        "description": "High wind velocities across Khandala ridge, battery absorbing excess renewable energy.",
        "row": {
            "timestamp": "2026-10-01T12:00:00",
            "solar_kw": 380.0,
            "wind_kw": 330.0,
            "hydro_kw": 250.0,
            "battery_kw": -60.0,      # charging -60 kW
            "grid_kw": 0.0,           # grid not supplying
            "load_kw": 900.0,
            "curtailment_kw": 0.0,
            "battery_soc_kwh": 820.0
        },
        "metrics": {
            "renewable_penetration_percent": 100.0,
            "grid_dependency_percent": 0.0,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 24.0,
            "estimated_co2_avoided_kg": 787.2
        }
    },
    "peak_demand": {
        "scenario_id": "peak_demand",
        "scenario_name": "Peak Demand",
        "description": "High evening tourism & residential demand requiring full battery output and grid import.",
        "row": {
            "timestamp": "2026-10-01T19:00:00",
            "solar_kw": 0.0,          # zero solar at night
            "wind_kw": 150.0,
            "hydro_kw": 350.0,
            "battery_kw": 250.0,      # discharging 250 kW (full discharge capacity)
            "grid_kw": 500.0,         # grid supplying 500 kW
            "load_kw": 1250.0,
            "curtailment_kw": 0.0,
            "battery_soc_kwh": 200.0
        },
        "metrics": {
            "renewable_penetration_percent": 40.0,
            "grid_dependency_percent": 40.0,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 100.0,
            "estimated_co2_avoided_kg": 410.0
        }
    }
}


def create_scenario_file(scenario_id, spec):
    row = spec["row"]
    # Physical balance check
    balance = (row["solar_kw"] + row["wind_kw"] + row["hydro_kw"] + row["battery_kw"] + row["grid_kw"]) - (row["load_kw"] + row["curtailment_kw"])
    assert abs(balance) < 1e-4, f"Energy balance violated in {scenario_id}: balance error={balance}"
    assert 0 <= row["battery_soc_kwh"] <= 1000.0, f"SOC out of bounds in {scenario_id}"

    payload = {
        "location": "Lonavala",
        "scenario_id": spec["scenario_id"],
        "scenario_name": spec["scenario_name"],
        "description": spec["description"],
        "is_synthetic": True,
        "data_source": "synthetic_demo",
        "note": SIMULATION_NOTE,
        "battery_convention": "battery_kw > 0 is discharging, battery_kw < 0 is charging",
        "dispatch": [row],
        "metrics": spec["metrics"]
    }
    out_path = SCENARIO_DIR / f"{scenario_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Created scenario file: {out_path.name}")
    return payload


def create_24h_sample_dispatch():
    """Creates a realistic multi-step 24-hour sample dispatch file for general testing and visualization.

    Profile characteristics:
    - Solar daytime curve peaking near midday (max 540 kW <= 600 kW nameplate), strictly 0 from 19:00 to 05:00.
    - Wind variable across 24 hours (140 to 220 kW <= 350 kW nameplate).
    - Hydro steady baseload (250 kW <= 400 kW nameplate).
    - Load curve with dual peaks: morning commercial peak (~910 kW) and evening tourism/residential peak (~1150 kW).
    - Battery charges on midday surplus renewable generation (hours 10:00 to 14:00, up to -230 kW),
      and discharges at high power during evening peak (hours 16:00 to 19:00, up to +240 kW <= 250 kW nameplate).
    - Battery SOC stays strictly between 120 kWh and 950 kWh (within 0 - 1000 kWh capacity).
    - Grid intertie smoothly covers any deficit gap.
    - Strict physical energy conservation holds for every hour.
    """
    solar_profile = [
        0.0,   # 00:00 - night
        0.0,   # 01:00 - night
        0.0,   # 02:00 - night
        0.0,   # 03:00 - night
        0.0,   # 04:00 - night
        0.0,   # 05:00 - night (MUST BE 0)
        30.0,  # 06:00 - sunrise
        130.0, # 07:00
        260.0, # 08:00
        390.0, # 09:00
        470.0, # 10:00
        520.0, # 11:00
        540.0, # 12:00 - midday solar peak
        510.0, # 13:00
        440.0, # 14:00
        340.0, # 15:00
        210.0, # 16:00
        90.0,  # 17:00
        10.0,  # 18:00 - sunset dusk
        0.0,   # 19:00 - night (MUST BE 0)
        0.0,   # 20:00 - night
        0.0,   # 21:00 - night
        0.0,   # 22:00 - night
        0.0    # 23:00 - night
    ]

    wind_profile = [
        160.0, 150.0, 140.0, 140.0, 150.0, 160.0,
        170.0, 180.0, 190.0, 200.0, 210.0, 220.0,
        220.0, 210.0, 200.0, 190.0, 180.0, 170.0,
        180.0, 190.0, 190.0, 180.0, 170.0, 160.0
    ]

    hydro_profile = [250.0] * 24

    load_profile = [
        500.0, 470.0, 450.0, 440.0, 460.0, 520.0,  # overnight base
        680.0, 820.0, 890.0, 910.0, 850.0, 780.0,  # morning ramp & peak
        760.0, 770.0, 800.0, 840.0, 920.0, 1020.0, # midday & afternoon ramp
        1120.0, 1150.0, 1060.0, 920.0, 760.0, 620.0# evening peak & late wind-down
    ]

    soc = 450.0  # initial kWh (capacity 1000 kWh)
    dispatch_rows = []

    total_load = sum(load_profile)
    total_grid = 0.0
    total_renewables_gen = 0.0

    for h in range(24):
        sol = solar_profile[h]
        wnd = wind_profile[h]
        hyd = hydro_profile[h]
        ld = load_profile[h]

        renewables = sol + wnd + hyd
        net = renewables - ld

        # Battery limits: max power 250 kW (nameplate 250 kW), SOC limits [120, 950] kWh
        if net > 0:
            # Surplus: charge battery
            max_charge = min(250.0, max(0.0, 950.0 - soc))
            charge = min(net, max_charge)
            bat = -charge  # negative = charging
            soc += charge
            curt = round(net - charge, 1)
            grid = 0.0
        else:
            # Deficit: discharge battery up to 240 kW
            deficit = -net
            max_discharge = min(240.0, max(0.0, soc - 120.0))
            discharge = min(deficit, max_discharge)
            bat = discharge  # positive = discharging
            soc -= discharge
            curt = 0.0
            grid = round(deficit - discharge, 1)

        ts = f"2026-10-01T{h:02d}:00:00"
        row = {
            "timestamp": ts,
            "solar_kw": round(sol, 1),
            "wind_kw": round(wnd, 1),
            "hydro_kw": round(hyd, 1),
            "battery_kw": round(bat, 1),
            "grid_kw": round(grid, 1),
            "load_kw": round(ld, 1),
            "curtailment_kw": round(curt, 1),
            "battery_soc_kwh": round(soc, 1)
        }

        # Energy conservation check
        bal = (row["solar_kw"] + row["wind_kw"] + row["hydro_kw"] + row["battery_kw"] + row["grid_kw"]) - (row["load_kw"] + row["curtailment_kw"])
        assert abs(bal) < 1e-4, f"Hour {h} balance error: {bal}"
        assert 0.0 <= row["battery_soc_kwh"] <= 1000.0, f"Hour {h} SOC out of bounds"

        total_grid += row["grid_kw"]
        total_renewables_gen += (row["solar_kw"] + row["wind_kw"] + row["hydro_kw"])
        dispatch_rows.append(row)

    re_pct = round(min(100.0, max(0.0, (total_load - total_grid) / total_load * 100.0)), 1)
    grid_pct = round(min(100.0, max(0.0, (total_grid / total_load) * 100.0)), 1)

    payload = {
        "location": "Lonavala",
        "scenario_id": "normal",
        "scenario_name": "Normal Day (24-Hour Profile) (Simulated)",
        "is_synthetic": True,
        "data_source": "synthetic_demo",
        "note": SIMULATION_NOTE,
        "battery_convention": "battery_kw > 0 is discharging, battery_kw < 0 is charging",
        "dispatch": dispatch_rows,
        "metrics": {
            "renewable_penetration_percent": re_pct,
            "grid_dependency_percent": grid_pct,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 48.0,
            "estimated_co2_avoided_kg": round(total_renewables_gen * 0.82, 1)
        }
    }
    out_path = DATA_DIR / "sample_dispatch.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Created 24h sample dispatch: {out_path.name}")


def main():
    print("=== STEP 4: Creating sample dispatch files and scenario files ===")
    for scenario_id, spec in SCENARIOS.items():
        create_scenario_file(scenario_id, spec)
    create_24h_sample_dispatch()
    print("Step 4 completed successfully.")


if __name__ == "__main__":
    main()
