# GridMate — Energy Optimization & Smart Dispatch

**From Weather to Watts, Intelligently.**  
Member 2 Module | Testbed: Lonavala, Maharashtra | Prototype: 10 October 2026

---

## Overview

This module answers the question:

> Given predicted renewable generation and electricity demand, what feasible mix
> of **solar, wind, hydro, battery and grid** power should be used for each hour?

It uses **PyPSA** to formulate a linear programme and **HiGHS** to solve it.
The result is a per-hour dispatch plan written to `outputs/dispatch.json`.

---

## Folder Structure

```
optimization/
├── config/
│   └── system_config.json      # Battery and grid parameters
├── data/
│   └── sample_forecast.json    # 24-hour Lonavala sample forecast
├── outputs/
│   ├── dispatch.json           # Main dispatch result
│   └── scenarios/              # Per-scenario dispatch results
├── src/
│   ├── optimizer.py            # Main entry point + optimize_dispatch()
│   ├── network.py              # PyPSA network builder
│   ├── battery.py              # Battery validation helpers
│   ├── metrics.py              # Post-optimisation metric calculations
│   ├── utils.py                # Shared utilities (IO, scaling)
│   └── run_scenarios.py        # Five-scenario testing harness
├── tests/
│   └── test_optimizer.py       # pytest test suite
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the optimizer

```bash
# From the optimization/ directory
python src/optimizer.py
```

Expected output: `outputs/dispatch.json`

### 3. Run all five scenarios

```bash
python src/run_scenarios.py
```

Expected output: `outputs/scenarios/{normal,cloudy,heavy_monsoon,high_wind,peak_demand}.json`

### 4. Run tests

```bash
python -m pytest tests/ -v
```

---

## Input Contract

`data/sample_forecast.json` follows this schema:

```json
{
  "location": "Lonavala",
  "forecast_horizon_hours": 24,
  "forecast": [
    {
      "timestamp": "2026-10-01T00:00:00",
      "solar_kw": 0.0,
      "wind_kw": 120.0,
      "hydro_kw": 220.0,
      "load_kw": 480.0
    }
  ]
}
```

Member 1 (Forecast Engineer) produces this file.  
The optimizer works with the sample data until the real forecast is available.

---

## Output Contract

`outputs/dispatch.json` follows this schema:

```json
{
  "location": "Lonavala",
  "dispatch": [
    {
      "timestamp": "2026-10-01T00:00:00",
      "solar_kw": 0.0,
      "wind_kw": 120.0,
      "hydro_kw": 220.0,
      "battery_kw": 50.0,
      "grid_kw": 0.0,
      "load_kw": 480.0,
      "curtailment_kw": 0.0,
      "battery_soc_kwh": 250.0
    }
  ],
  "metrics": {
    "renewable_penetration_percent": 94.4,
    "grid_dependency_percent": 5.6,
    "curtailment_percent": 0.0,
    "battery_utilization_percent": 3.2,
    "estimated_co2_avoided_kg": 1200.0
  }
}
```

Member 4 (Backend/Dashboard) consumes this file. No PyPSA imports are needed.

---

## Python Interface

```python
from src.optimizer import optimize_dispatch

with open("data/sample_forecast.json") as f:
    forecast_data = json.load(f)

result = optimize_dispatch(forecast_data)
# result is a dict following the output contract
# dispatch.json is also written automatically
```

---

## System Model

```
Solar ──┐
Wind ───┤
Hydro ──┤──► Main_Bus ──► Electricity_Demand (Load)
Battery ┤       ▲
Grid ───┘       │
                └── (cyclic energy balance enforced by HiGHS)
```

Energy balance enforced at every timestep:

```
solar + wind + hydro + battery_discharge + grid_import
= load + battery_charge + curtailment
```

Curtailment is the renewable energy that cannot be used or stored.

---

## Optimization Objective

The objective function is a **weighted cost minimization**:

| Component | Marginal cost | Rationale |
|---|---|---|
| Solar / Wind / Hydro | 0 Rs/MWh | Free — solver always prefers renewables |
| Grid import | 8,000 Rs/MWh | Expensive — used only when needed |
| Battery cycling | 10 Rs/MWh | Small — prevents unnecessary charge/discharge |

> **These weights are prototype assumptions, not universally optimal values.**
> A production system would use real LCOE, grid tariffs and ancillary costs.

**Priority order:**
1. Demand satisfaction (hard constraint — HiGHS feasibility)
2. Renewable utilisation (zero marginal cost → used first)
3. Grid reduction (high marginal cost → minimised)
4. Sensible battery operation (small cycling cost → prevents waste)
5. Curtailment reduction (consequence of priorities 2–4)

---

## Battery Configuration (`config/system_config.json`)

| Parameter | Default | Description |
|---|---|---|
| `capacity_kwh` | 500 | Total energy capacity |
| `max_charge_kw` | 100 | Maximum charge power |
| `max_discharge_kw` | 100 | Maximum discharge power |
| `initial_soc_kwh` | 200 | State of charge at hour 0 |
| `min_soc_kwh` | 50 | Minimum allowed SOC |
| `max_soc_kwh` | 500 | Maximum allowed SOC |
| `charge_efficiency` | 0.95 | Round-trip charge efficiency |
| `discharge_efficiency` | 0.95 | Round-trip discharge efficiency |

**Battery strategy:**  
The optimizer charges the battery when renewable generation exceeds demand
(zero-cost energy available) and discharges it when demand exceeds generation
(avoids costly grid import). A cyclic SOC constraint ensures the battery
ends the 24-hour window at the same level it started.

---

## Grid Configuration

| Parameter | Default | Description |
|---|---|---|
| `capacity_kw` | 1000 | Maximum import power |
| `cost_per_kwh` | 8 | Import tariff (Rs/kWh) |
| `emission_factor` | 0.7 | Assumed CO₂ intensity (kg/kWh) |

---

## Metrics Definitions

### Renewable penetration
```
non-grid energy supplied to load
─────────────────────────────── × 100
         total load
```

> Prototype simplification: all non-grid energy is treated as renewable.
> Battery may store a mix of renewable and grid energy in reality.

### Grid dependency
```
grid energy supplied
──────────────────── × 100
     total load
```

### Curtailment
```
curtailed renewable energy
────────────────────────── × 100
available renewable energy
```

### Battery utilisation
```
(charge throughput + discharge throughput)
────────────────────────────────────────── × 100
   2 × capacity_kwh × number_of_hours
```

Maximum throughput assumes the battery is fully cycled every hour.

### Estimated CO₂ avoided *(ESTIMATE)*
```
non-grid energy × emission_factor
```
Uses the assumed Maharashtra grid emission factor (0.7 kg CO₂/kWh).  
Actual values vary by time, season and marginal generator.

---

## Scenarios

| Scenario | Solar | Wind | Hydro | Load |
|---|---|---|---|---|
| `normal` | ×1.0 | ×1.0 | ×1.0 | ×1.0 |
| `cloudy` | ×0.3 | ×0.85 | ×1.0 | ×1.0 |
| `heavy_monsoon` | ×0.2 | ×1.1 | ×1.2 | ×1.05 |
| `high_wind` | ×1.0 | ×1.6 | ×1.0 | ×1.0 |
| `peak_demand` | ×1.0 | ×1.0 | ×1.0 | ×1.3 |

The optimizer receives changed forecast data — it does not implement weather
logic itself.

---

## Integration

```
Member 1 (Forecast)
       ↓  forecast.json
Member 2 (Optimizer)   ← this module
       ↓  dispatch.json
Member 4 (Backend / Dashboard)
```

---

## Assumptions & Limitations

- All generators are dispatchable within their forecast limits (no unit
  commitment, no ramping constraints).
- Hydro is treated as a run-of-river resource with an hourly availability cap.
- Battery round-trip efficiency is modelled as symmetric
  (charge = discharge = 0.95).
- CO₂ estimates use a fixed emission factor — a prototype-grade approximation.
- The cyclic SOC constraint may cause infeasibility with very low battery
  capacity. Increase `capacity_kwh` or loosen `min_soc_kwh` if this occurs.
- This is a prototype, **not** utility-grade grid software.

---

## Technology

| Library | Purpose |
|---|---|
| **PyPSA** | Power-system linear programme formulation |
| **HiGHS** | Open-source LP solver |
| **pandas** | Time-series data handling |
| **NumPy** | Numerical operations |
| **pytest** | Test suite |

Python 3.12+

---

## Git

```bash
git checkout -b feature/energy-optimization
git add optimization/
git commit -m "Add PyPSA dispatch optimization"
git push origin feature/energy-optimization
```
