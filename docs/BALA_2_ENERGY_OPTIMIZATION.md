# GridMate — Member 2 Task Specification
## Energy Optimization & Smart Dispatch Engineer

### Project
GridMate — **From Weather to Watts, Intelligently.**  
Prototype deadline: **10 October 2026**  
Testbed: **Lonavala, Maharashtra**

### Your role
You own the **Energy Optimization and Smart Dispatch** module.

Your question is:

> Given predicted renewable generation and electricity demand, what feasible mix of solar, wind, hydro, battery and grid power should be used for each hour?

## 1. Responsibilities

Build the optimization engine for:

```text
Solar
Wind
Hydro
Battery
Grid
Load
```

The optimizer should:

- satisfy demand
- maximize renewable utilization
- reduce grid dependency
- reduce renewable curtailment
- use the battery intelligently
- consider operating cost
- consider estimated CO₂ emissions

This is a hackathon prototype, not utility-grade grid software.

## 2. Technology

Use:

- Python 3.12
- PyPSA
- HiGHS
- Pandas
- NumPy

PyPSA is the primary power-system optimization framework. HiGHS is the default open-source solver.

## 3. Development Independence

Do not wait for Member 1.

Create `sample_forecast.json` using the agreed contract and make the optimizer work with it first.

## 4. Input Contract

```json
{
  "location": "Lonavala",
  "forecast_horizon_hours": 24,
  "forecast": [
    {
      "timestamp": "2026-10-01T12:00:00",
      "solar_kw": 420.0,
      "wind_kw": 180.0,
      "hydro_kw": 250.0,
      "load_kw": 900.0
    }
  ]
}
```

## 5. System Model

Represent:

```text
Solar generator
Wind generator
Hydro generator
Battery storage
Grid/import source
Load
```

At each timestep enforce the energy balance:

```text
generation + battery discharge + grid import
=
load + battery charge + curtailment
```

Do not dispatch more renewable power than the forecast/available generation.

## 6. Battery

Use configurable parameters:

```text
energy_capacity_kwh
maximum_charge_kw
maximum_discharge_kw
initial_state_of_charge
minimum_state_of_charge
maximum_state_of_charge
charge_efficiency
discharge_efficiency
```

Values are prototype assumptions unless backed by a real specification.

Battery should:

```text
charge when renewable energy is abundant
discharge when renewable energy is insufficient
```

## 7. Grid

Configure:

```text
grid_capacity_kw
grid_cost_per_kwh
grid_emission_factor
```

Grid is the backup/import source.

## 8. Optimization Objectives

Prioritize:

1. Demand satisfaction
2. Renewable utilization
3. Grid reduction
4. Sensible battery operation
5. Curtailment reduction
6. Cost
7. Estimated CO₂ reduction

Document objective weights/assumptions.

Do not claim the chosen weights are universally optimal.

## 9. Curtailment

Track renewable energy that cannot be used or stored.

At minimum calculate:

```text
total_curtailment
curtailment_percent
```

Per-source curtailment is optional.

## 10. Required Output Contract

Create `dispatch.json`:

```json
{
  "location": "Lonavala",
  "dispatch": [
    {
      "timestamp": "2026-10-01T12:00:00",
      "solar_kw": 420.0,
      "wind_kw": 180.0,
      "hydro_kw": 250.0,
      "battery_kw": 50.0,
      "grid_kw": 0.0,
      "load_kw": 900.0,
      "curtailment_kw": 0.0,
      "battery_soc_kwh": 150.0
    }
  ],
  "metrics": {
    "renewable_penetration_percent": 94.4,
    "grid_dependency_percent": 0.0,
    "curtailment_percent": 0.0,
    "battery_utilization_percent": 16.7,
    "estimated_co2_avoided_kg": 0.0
  }
}
```

Calculate metrics from actual simulation results.

## 11. Metrics

### Renewable penetration

```text
renewable energy supplied to load
--------------------------------- × 100
total load
```

### Grid dependency

```text
grid energy supplied
-------------------- × 100
total load
```

### Curtailment

```text
curtailed renewable energy
-------------------------- × 100
available renewable energy
```

### Battery utilization

Choose and document a consistent definition based on battery throughput/capacity.

### Estimated CO₂ avoided

Use the assumed grid emission factor and clearly label the result as an estimate.

## 12. Scenario Support

The optimizer must work when forecasts change for:

```text
normal
cloudy
heavy_monsoon
high_wind
peak_demand
```

The optimizer should receive changed forecast data rather than implementing weather logic itself.

## 13. Folder Structure

```text
optimization/
├── data/
│   └── sample_forecast.json
├── src/
│   ├── optimizer.py
│   ├── network.py
│   ├── battery.py
│   ├── metrics.py
│   └── utils.py
├── outputs/
│   └── dispatch.json
├── config/
│   └── system_config.json
├── tests/
├── requirements.txt
└── README.md
```

## 14. Python Interface

Provide:

```python
def optimize_dispatch(forecast_data):
    ...
```

Return structured dispatch data and/or write `dispatch.json`.

The frontend must not need PyPSA internals.

## 15. Do NOT Build

Do not build:

- React UI
- FastAPI API
- MapLibre/GIS
- XGBoost forecasting
- authentication
- presentation

## 16. Definition of DONE

1. Sample forecast loads.
2. PyPSA network is created.
3. HiGHS solves it.
4. Demand is satisfied when system constraints permit.
5. Battery charge/discharge works.
6. Grid backup works.
7. Curtailment is calculated.
8. Multi-hour dispatch works.
9. Metrics are calculated.
10. `dispatch.json` follows the exact contract.
11. Changed forecast/scenario inputs produce changed dispatch.
12. README explains setup and assumptions.

Primary command:

```bash
python src/optimizer.py
```

Expected:

```text
outputs/dispatch.json
```

## 17. Integration

```text
Member 1
forecast.json
      ↓
YOUR OPTIMIZER
      ↓
dispatch.json
      ↓
Member 4 Backend/Dashboard
```

Member 4 should consume `dispatch.json` without importing PyPSA internals.

## 18. Git

```bash
git checkout -b feature/energy-optimization
git add optimization/
git commit -m "Add PyPSA dispatch optimization"
git push origin feature/energy-optimization
```

Use a Pull Request into `main`.

## 19. AI Handoff Prompt

When giving this file to an AI coding assistant, say:

> Build only the Member 2 Energy Optimization and Smart Dispatch module described here. Use PyPSA and HiGHS. Follow the folder structure, interfaces and JSON contract exactly. Start with reproducible sample forecast data. Do not build React, FastAPI, GIS or AI forecasting. Keep the optimization model understandable and prototype-ready.

## 20. Final Deliverables

```text
optimization/
source code
sample_forecast.json
system_config.json
dispatch.json
metrics
tests
README.md
```
