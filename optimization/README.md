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
│   └── scenarios/              # Per-scenario dispatch results + summary.csv
├── src/
│   ├── optimizer.py            # Main entry point + optimize_dispatch()
│   ├── network.py              # PyPSA network builder
│   ├── battery.py              # Battery validation helpers
│   ├── metrics.py              # Post-optimisation metric calculations
│   ├── utils.py                # Shared utilities (IO, scaling)
│   └── run_scenarios.py        # Five-scenario testing harness
├── tests/
│   ├── test_optimizer.py       # pytest test suite (31 tests)
│   ├── test_tod.py             # ToD tariff tests (18 tests)
│   └── test_cost_metrics.py    # Cost & savings metrics tests (7 tests)
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

**Standard run (using sample forecast):**
```bash
python src/optimizer.py
```

**Direct integration with Member 1 (AI Forecasting):**
```bash
# Uses Member 1's live forecast output directly:
python src/optimizer.py --forecasting

# Or pass any custom forecast file explicitly:
python src/optimizer.py -i ../forecasting/outputs/forecast.json
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
      "battery_kw": 90.0,
      "grid_kw": 50.0,
      "load_kw": 480.0,
      "curtailment_kw": 0.0,
      "battery_soc_kwh": 110.0
    }
  ],
  "metrics": {
    "renewable_penetration_percent": 89.6,
    "grid_dependency_percent": 10.4,
    "curtailment_percent": 0.0,
    "battery_utilization_percent": 3.2,
    "estimated_co2_avoided_kg": 302.4
  },
  "extra_metrics": {
    "total_grid_cost_rs": 400.0,
    "grid_only_cost_rs": 3840.0,
    "baseline_cost_rs": 3840.0,
    "savings_rs": 3440.0,
    "savings_percent": 89.6,
    "average_cost_rs_per_kwh_served": 0.83,
    "grid_only_average_cost_rs_per_kwh": 8.0,
    "label": "Cost figures are prototype estimates based on assumed tariffs, not billing-grade values."
  },
  "extra_hourly": [
    {
      "timestamp": "2026-10-01T00:00:00",
      "grid_price_rs_per_kwh": 8.0
    }
  ]
}
```

**Power-balance check for the example row above:**
```
solar + wind + hydro + battery_kw + grid_kw = load_kw
0 + 120 + 220 + 90 + 50 = 480  ✓
```

**Battery sign convention:**
- **Positive `battery_kw`** → battery is **discharging** (supplying energy to the bus).
- **Negative `battery_kw`** → battery is **charging** (absorbing energy from the bus).

**Extra output blocks (do not change the required contract):**

| Block | Contents |
|---|---|
| `extra_metrics` | `total_grid_cost_rs`, `grid_only_cost_rs`, `savings_rs`, `savings_percent`, `average_cost_rs_per_kwh_served`, `grid_only_average_cost_rs_per_kwh`, `label` |
| `extra_hourly` | Per-hour `grid_price_rs_per_kwh` list (same length as `dispatch`) |

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
| Grid import | 6 000–9 600 Rs/MWh (ToD) | Expensive — used only when needed; peaks at 9 600 during 17:00–24:00 |
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
| `base_energy_charge_rs_per_kwh` | 8.0 | Base import tariff before ToD multiplier (Rs/kWh) |
| `emission_factor` | 0.7 | Assumed CO₂ intensity (kg/kWh) |

### Time-of-Day (ToD) Tariff

The grid price is not flat — it follows a Maharashtra (MSEDCL-style) ToD
structure. Each hour's price = `base_energy_charge_rs_per_kwh × multiplier`.

| Slot | Hours | Season | Multiplier | Effective price |
|---|---|---|---|---|
| Normal | 00:00–09:00 | Both | 1.00 | 8.00 Rs/kWh |
| Solar | 09:00–17:00 | Apr–Sep | 0.85 | 6.80 Rs/kWh |
| Solar | 09:00–17:00 | Oct–Mar | 0.75 | 6.00 Rs/kWh |
| Peak | 17:00–24:00 | Both | 1.20 | 9.60 Rs/kWh |

> **⚠️ Prototype assumption notice**
>
> The base price (8 Rs/kWh), multipliers and slot boundaries are
> **prototype assumptions** modelled on the MERC/MSEDCL 2026 ToD tariff
> structure (normal 00–09, solar 09–17, peak 17–24, **no night rebate**).
> These values **must be verified against the official MSEDCL/MERC tariff
> order** before this module is used in any production or reporting context.
> The 20 % peak surcharge (multiplier 1.20) is a prototype assumption.

**Backward compatibility:** If the `"tod"` key is absent from
`system_config.json` the module falls back to a flat price equal to
`base_energy_charge_rs_per_kwh` (or the legacy `cost_per_kwh`/
`grid_cost_per_kwh` key). No code changes are required by callers.

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

### Cost & Savings Metrics (`extra_metrics`)

All monetary figures are calculated from actual hourly dispatch results (1-hour timesteps, $1\text{ kW} \times 1\text{ h} = 1\text{ kWh}$):

- **`total_grid_cost_rs`:** $\sum_t \text{grid\_kw}_t \times \text{price}_t$
- **`grid_only_cost_rs`:** $\sum_t \text{load\_kw}_t \times \text{price}_t$ (baseline scenario where all load is purchased from the grid at that hour's price, with zero renewables and zero battery)
- **`savings_rs`:** $\text{grid\_only\_cost\_rs} - \text{total\_grid\_cost\_rs}$
- **`savings_percent`:** $(\text{savings\_rs} / \text{grid\_only\_cost\_rs}) \times 100$ ($0.0\%$ if baseline is zero)
- **`average_cost_rs_per_kwh_served`:** $\text{total\_grid\_cost\_rs} / \text{total\_load\_kwh}$
- **`grid_only_average_cost_rs_per_kwh`:** $\text{grid\_only\_cost\_rs} / \text{total\_load\_kwh}$

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

### Scenario Summary Table (`outputs/scenarios/summary.csv`)

Running `python src/run_scenarios.py` executes all five scenarios and generates `outputs/scenarios/summary.csv` with the following columns:
1. `scenario`
2. `renewable_penetration_percent`
3. `grid_dependency_percent`
4. `curtailment_percent`
5. `battery_utilization_percent`
6. `estimated_co2_avoided_kg`
7. `total_grid_cost_rs`
8. `grid_only_cost_rs`
9. `savings_rs`
10. `savings_percent`

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

- **Dispatch Constraints:** All generators are dispatchable within their forecast limits (no unit
  commitment, no ramping constraints).
- **Hydro:** Hydro is treated as a run-of-river resource with an hourly availability cap.
- **Battery Efficiency:** Battery round-trip efficiency is modelled as symmetric
  (charge = discharge = 0.95).
- **CO₂ Estimates:** CO₂ estimates use a fixed emission factor — a prototype-grade approximation.
- **Cyclic SOC:** The cyclic SOC constraint may cause infeasibility with very low battery
  capacity. Increase `capacity_kwh` or loosen `min_soc_kwh` if this occurs.
- **Cost & Tariff Limitations:**
  Cost and savings metrics are prototype estimates based on assumed tariffs and ToD multipliers.
  They ignore:
  - Demand charges (kVA / peak kW maximum demand billing)
  - Fixed monthly charges and connection fees
  - Off-peak night rebates (if applicable)
  - Taxes, electricity duty, and regulatory surcharges
  - Battery degradation and lifetime replacement costs
  - Potential export / feed-in revenue to the grid
- This is a hackathon prototype, **not** utility billing software.

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
