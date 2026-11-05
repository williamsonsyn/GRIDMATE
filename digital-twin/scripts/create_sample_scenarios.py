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
    """Creates a multi-step 24-hour sample dispatch file for general testing."""
    hours = 24
    dispatch_rows = []
    solar_profile = [0, 0, 0, 0, 0, 10, 80, 200, 350, 420, 460, 480, 450, 390, 290, 150, 40, 5, 0, 0, 0, 0, 0, 0]
    load_profile = [520, 480, 460, 450, 470, 550, 680, 800, 880, 900, 920, 910, 890, 870, 860, 880, 950, 1100, 1200, 1150, 1020, 880, 720, 600]

    soc = 500.0  # initial kWh (capacity 1000 kWh)
    for h in range(hours):
        sol = float(solar_profile[h])
        wnd = 180.0 + (20.0 if 12 <= h <= 18 else -10.0)
        hyd = 250.0
        ld = float(load_profile[h])
        renewables = sol + wnd + hyd
        net = renewables - ld

        if net > 0:
            # surplus renewable: charge battery up to 100 kW or capacity 900 kWh
            charge = min(net, 100.0, max(0.0, 900.0 - soc))
            bat = -charge
            grid = 0.0
            curt = max(0.0, net - charge)
            soc += charge
        else:
            # deficit: discharge battery up to 150 kW
            deficit = -net
            discharge = min(deficit, 150.0, max(0.0, soc - 100.0))
            bat = discharge
            soc -= discharge
            grid = max(0.0, deficit - discharge)
            curt = 0.0

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
        bal = (row["solar_kw"] + row["wind_kw"] + row["hydro_kw"] + row["battery_kw"] + row["grid_kw"]) - (row["load_kw"] + row["curtailment_kw"])
        assert abs(bal) < 0.1, f"Hour {h} balance error: {bal}"
        dispatch_rows.append(row)

    payload = {
        "location": "Lonavala",
        "scenario_id": "normal",
        "scenario_name": "Normal Day (24-Hour Profile)",
        "is_synthetic": True,
        "data_source": "synthetic_demo",
        "note": SIMULATION_NOTE,
        "battery_convention": "battery_kw > 0 is discharging, battery_kw < 0 is charging",
        "dispatch": dispatch_rows,
        "metrics": {
            "renewable_penetration_percent": 94.4,
            "grid_dependency_percent": 5.6,
            "curtailment_percent": 0.0,
            "battery_utilization_percent": 34.2,
            "estimated_co2_avoided_kg": 15420.0
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
