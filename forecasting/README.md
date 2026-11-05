# GridMate — AI Forecasting Module (Member 1)

> **"From Weather to Watts, Intelligently."**  
> **Testbed:** Lonavala, Maharashtra (~18.75°N, 73.40°E)  
> **Module Owner:** Member 1 — AI Forecasting Engineer  
> **Runtime:** Python 3.12  

---

## 1. Project Overview & Member 1 Responsibilities

**GridMate** is an AI-powered renewable-energy forecasting, optimization, and intelligent-dispatch prototype developed for the hill-station testbed of **Lonavala, Maharashtra**. 

As **Member 1 (AI Forecasting Engineer)**, this module answers the core question:
> *"Given weather, water, and historical demand conditions, how much solar, wind, hydro generation and electricity demand should we expect over the next 6 to 24 hours?"*

### Primary Responsibilities:
- Produce reproducible synthetic meteorological and electrical load datasets tailored to Lonavala's Western Ghats geography.
- Build clean, leak-free preprocessing and feature engineering pipelines.
- Train four independent **XGBoost regression models** (`solar_kw`, `wind_kw`, `hydro_kw`, `load_kw`).
- Implement an autoregressive, recursive roll-forward loop for multi-step electricity load forecasting without lookahead bias.
- Support 5 deterministic weather/demand scenarios (`normal`, `cloudy`, `heavy_monsoon`, `high_wind`, `peak_demand`).
- Output predictions strictly matching the shared `forecast.json` contract consumed by Member 2 (Optimization).

---

## 2. Architecture & Forecasting Pipeline

The forecasting module is the first stage in the GridMate system pipeline:

```text
┌──────────────────────────────────────────────────────────┐
│                    INPUT DATA                            │
│                                                          │
│ Weather │ Water/Rainfall │ Geography │ Electricity Load  │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ MEMBER 1 — AI FORECASTING (This Module)                  │
│                                                          │
│ Preprocessing ──► Features ──► XGBoost Models (x4)       │
│                                                          │
│ Solar Forecast │ Wind Forecast │ Hydro Forecast │ Load   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           │ outputs/forecast.json
                           ▼
┌──────────────────────────────────────────────────────────┐
│ MEMBER 2 — ENERGY OPTIMIZATION (PyPSA + HiGHS)           │
└──────────────────────────────────────────────────────────┘
```

### Module Dataflow:
1. **Data Loading (`data/`):** Generates and loads hourly observations.
2. **Preprocessing (`src/preprocessing.py`):** Schema validation, continuity verification (`1h` interval), domain constraints, and safe boolean type guards.
3. **Feature Engineering (`src/features.py`):** Extracts calendar indicators (`hour`, `day_of_week`, `day_of_year`, `month`, `is_weekend`) and strictly backward lags ($t-1, t-24$).
4. **Training (`src/train.py`):** Chronological 80:20 train/test split, fitting four independent XGBoost regressors without lookahead bias.
5. **Inference & Simulation (`src/predict.py`, `src/utils.py`):** Autoregressive recursive load prediction and scenario perturbations producing `outputs/forecast.json`.

---

## 3. Folder Structure

```text
forecasting/
├── data/
│   ├── generate_data.py                    # 1-year synthetic dataset generator (seed=42)
│   └── synthetic_lonavala_energy_data.csv   # 8,760 hourly records (15 contract columns)
├── models/
│   ├── solar_model.joblib                  # Serialized XGBoost solar generation model
│   ├── wind_model.joblib                   # Serialized XGBoost wind generation model
│   ├── hydro_model.joblib                  # Serialized XGBoost hydro generation model
│   └── load_model.joblib                   # Serialized XGBoost electricity demand model
├── outputs/
│   ├── forecast.json                       # Shared JSON contract for Member 2
│   └── metrics.json                        # Out-of-sample evaluation metrics
├── src/
│   ├── preprocessing.py                    # Data loading, schema validation, domain checks
│   ├── features.py                         # Calendar and past-observation lag engineering
│   ├── train.py                            # Chronological 80:20 split and training orchestration
│   ├── evaluation.py                       # MAE, RMSE, and R² calculation
│   ├── predict.py                          # Recursive inference engine and CLI
│   └── utils.py                            # Scenario modifiers and contract schema validation
├── tests/
│   ├── conftest.py                         # Pytest path and import configuration
│   ├── test_preprocessing.py               # Preprocessing and integrity tests
│   ├── test_features.py                    # Feature creation, immutability, and lag tests
│   ├── test_training.py                    # Model loading, split ordering, and metric tests
│   ├── test_forecast_contract.py           # Contract schema and horizon tests
│   └── test_scenarios.py                   # Scenarios, directionality, and recursive load tests
├── requirements.txt                        # Python 3.12 dependencies
└── README.md                               # Comprehensive documentation
```

---

## 4. Python 3.12 Setup & Virtual Environment (Windows)

Ensure Python 3.12 is installed on your system. From the repository root (`GRIDMATE`):

```powershell
# Check Python version
python --version
# Expected: Python 3.12.x

# Create virtual environment if not already present
python -m venv .venv

# Activate the virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1
```

*(If script execution is restricted in PowerShell, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once).*

---

## 5. Dependency Installation

With your virtual environment activated, install the required packages:

```powershell
# From repository root or forecasting/ directory:
pip install -r forecasting/requirements.txt
```

Core libraries installed:
- `pandas` ($\ge 2.2.0$) & `numpy` ($\ge 1.26.0$) — Data manipulation and time series array operations.
- `scipy` ($\ge 1.12.0$) & `scikit-learn` ($\ge 1.4.0$) — Chronological evaluation and regression metrics.
- `xgboost` ($\ge 2.0.0$) — Gradient boosted decision tree regressors.
- `joblib` ($\ge 1.3.0$) — Model persistence and serialization.
- `matplotlib` ($\ge 3.8.0$) — Diagnostic evaluation plotting.
- `pytest` ($\ge 8.0.0$) — Test automation framework.

---

## 6. Synthetic Dataset & Authenticity Disclaimer

> ### IMPORTANT AUTHENTICITY NOTICE
> All data used and generated by this module is **SYNTHETIC DEMO DATA** created for offline prototype development and demonstration. It must **NEVER** be presented as real measured meteorological or utility data from Lonavala, Maharashtra.

### Dataset Overview (`data/synthetic_lonavala_energy_data.csv`):
- **Observations:** 8,760 hourly rows (1 full non-leap year: `2025-10-01 00:00:00` to `2026-09-30 23:00:00`).
- **Reproducibility:** Generated using a fixed NumPy seed (`seed = 42`).
- **Geography & Climate Modeling:**
  - **Solar Irradiance:** Diurnal bell curves peaking around solar noon (~850–950 W/m²), strictly 0 at night, attenuated by cloud cover.
  - **Monsoon Dynamics:** Intense South-West monsoon rainfall (June–September) reflecting Western Ghats orographic precipitation.
  - **Wind:** Weibull-distributed wind speeds with stronger winds during monsoon months.
  - **Hydro:** Water flow proxy with a 72-hour rainfall retention decay simulating reservoir inflow.
  - **Demand:** Dual diurnal peaks (morning 09:00, evening 20:00), weekend tourist surges (+15%), and summer cooling loads.

To regenerate the dataset from scratch:
```powershell
python forecasting/data/generate_data.py
```

---

## 7. Data Preprocessing & Feature Engineering

### Preprocessing (`src/preprocessing.py`)
Loaded via `load_and_preprocess_data()`:
- **Schema Validation:** Verifies all 15 required contract columns are present and rejects unexpected columns.
- **Continuity Verification:** Guarantees that timestamps form a strictly continuous, 1-hour interval sequence with zero duplicates.
- **Type Safety & Bounds:** Rejects `NaN`, $+\infty$, $-\infty$, and non-numeric strings. Enforces non-negative power bounds ($P \ge 0.0\text{ kW}$) and atmospheric limits.
- **Safe Boolean Check:** Rejects invalid representations and ensures `is_synthetic` contains only `True`.

### Feature Engineering (`src/features.py`)
Executed via `create_features(df, drop_na=True)`:
- **Calendar & Diurnal Features:**
  - `hour` ($0–23$), `day_of_week` ($0–6$), `day_of_year` ($1–366$), `month` ($1–12$), `is_weekend` ($0/1$).
- **Past-Observation Lags (No Lookahead Leakage):**
  - `historical_load_lag_1` ($t - 1\text{h}$)
  - `historical_load_lag_24` ($t - 24\text{h}$, previous day's same-hour load)
  - `solar_irradiance_lag_1` ($t - 1\text{h}$)
  - `wind_speed_lag_1` ($t - 1\text{h}$)
  - `water_flow_lag_1` ($t - 1\text{h}$)
- **Immutability:** Operates on an internal copy; never mutates the input DataFrame.
- **Leakage-Free NaN Handling:** Drops the first 24 unpopulated lag rows rather than backward-filling.

---

## 8. Four Independent XGBoost Models

Each target is modeled by an independent `xgboost.XGBRegressor` using domain-isolated feature sets:

| Model Target | Capacity / Baseline | Input Feature Columns |
| :--- | :---: | :--- |
| **`solar_kw`** | 500 kW rated farm | `solar_irradiance`, `solar_irradiance_lag_1`, `cloud_cover`, `temperature`, `humidity`, `hour`, `month`, `day_of_year` |
| **`wind_kw`** | 250 kW rated farm | `wind_speed`, `wind_speed_lag_1`, `wind_direction`, `pressure`, `temperature`, `hour`, `month` |
| **`hydro_kw`** | 300 kW rated plant | `water_flow`, `water_flow_lag_1`, `rainfall`, `month`, `day_of_year` |
| **`load_kw`** | ~450 kW base, 1100 kW peak | `historical_load_lag_1`, `historical_load_lag_24`, `temperature`, `humidity`, `hour`, `day_of_week`, `month`, `is_weekend` |

*Target Isolation:* No model target appears in its own feature set.

---

## 9. Chronological Split & Evaluation Metrics

To avoid time-series leakage, data is partitioned chronologically (80% Train, 20% Test):
- **Training Set (80%):** $6,988$ hours (`2025-10-02 00:00:00` to `2026-07-20 03:00:00`).
- **Test Set (20%):** $1,748$ hours (`2026-07-20 04:00:00` to `2026-09-30 23:00:00`).
- Strict temporal condition enforced: $\max(T_{\text{train}}) < \min(T_{\text{test}})$.

### Benchmark Results on Synthetic Chronological Holdout:

| Target Model | Test Samples | MAE | RMSE | $R^2$ Score |
| :--- | :---: | :---: | :---: | :---: |
| **`solar_kw`** | 1,748 | **$1.49\text{ kW}$** | **$2.87\text{ kW}$** | **$0.9984$** |
| **`wind_kw`** | 1,748 | **$3.31\text{ kW}$** | **$5.97\text{ kW}$** | **$0.9896$** |
| **`hydro_kw`** | 1,748 | **$2.52\text{ kW}$** | **$3.19\text{ kW}$** | **$0.9527$** |
| **`load_kw`** | 1,748 | **$12.68\text{ kW}$** | **$15.88\text{ kW}$** | **$0.9821$** |

Results are stored in [`outputs/metrics.json`](file:///c:/GitHub/GRIDMATE/forecasting/outputs/metrics.json).

---

## 10. How to Train Models

To retrain the models and regenerate `metrics.json`:

```powershell
# From repository root:
python forecasting/src/train.py

# OR from within the forecasting/ directory:
cd forecasting
python src/train.py
```

This will:
1. Load and validate `synthetic_lonavala_energy_data.csv`.
2. Generate all lag and temporal features.
3. Perform the 80:20 chronological split.
4. Fit the 4 XGBoost regressors with `random_state=42`.
5. Save model artifacts into `forecasting/models/`.
6. Write out-of-sample metrics to `forecasting/outputs/metrics.json`.

---

## 11. How to Generate Forecasts (6, 12, 24 Hours)

### Via Command-Line Interface (CLI):

```powershell
# Generate default 24-hour baseline forecast:
python forecasting/src/predict.py --scenario normal --horizon 24

# Generate 12-hour forecast:
python forecasting/src/predict.py --scenario normal --horizon 12

# Generate 6-hour forecast:
python forecasting/src/predict.py --scenario normal --horizon 6

# Specify a custom output file destination:
python forecasting/src/predict.py --scenario normal --horizon 24 --output forecasting/outputs/forecast.json
```

### Via Python API:

```python
from forecasting.src.predict import generate_forecast

# Generate a 24-hour forecast under the "normal" scenario
forecast_payload = generate_forecast(horizon=24, scenario="normal")

print(f"Location: {forecast_payload['location']}")
print(f"Horizon: {forecast_payload['forecast_horizon_hours']} hours")
print(f"First hour forecast: {forecast_payload['forecast'][0]}")
```

---

## 12. How to Run the Five Scenarios

GridMate supports 5 standardized scenario identifiers:

```powershell
# 1. Normal Day (Baseline conditions)
python forecasting/src/predict.py --scenario normal --horizon 24

# 2. Cloudy Day (Solar drops by ~73% due to high cloud cover)
python forecasting/src/predict.py --scenario cloudy --horizon 24

# 3. Heavy Monsoon (Torrential rain; Hydro surges by ~76%, Solar collapses)
python forecasting/src/predict.py --scenario heavy_monsoon --horizon 24

# 4. High Wind (Sustained winds > 12 m/s; Wind surges to near-rated 225 kW)
python forecasting/src/predict.py --scenario high_wind --horizon 24

# 5. Peak Demand (Hotter weather + elevated demand; Load surges by ~37%)
python forecasting/src/predict.py --scenario peak_demand --horizon 24
```

### Scenario Impact Summary:
- **`normal`:** Baseline 24-hour profile (Solar mean: 122.1 kW, Wind: 9.5 kW, Hydro: 155.3 kW, Load: 567.4 kW).
- **`cloudy`:** Cloud cover raised to 0.88, reducing average solar to 32.7 kW.
- **`heavy_monsoon`:** Heavy precipitation (18.5 mm/hr) and water runoff (85 m³/s), surging hydro to 273.6 kW.
- **`high_wind`:** High wind speed (12.8 m/s), increasing wind generation to 225.6 kW.
- **`peak_demand`:** High cooling demand, increasing average load to 780.3 kW (peak: 970.8 kW).

---

## 13. Output Formats & Contract Schemas

### A. Forecast Contract: [`outputs/forecast.json`](file:///c:/GitHub/GRIDMATE/forecasting/outputs/forecast.json)
This file is the primary deliverable consumed by **Member 2 (Optimization)**:

```json
{
  "location": "Lonavala",
  "forecast_horizon_hours": 24,
  "forecast": [
    {
      "timestamp": "2026-10-01T00:00:00",
      "solar_kw": 0.0,
      "wind_kw": 6.4,
      "hydro_kw": 199.4,
      "load_kw": 457.5
    },
    {
      "timestamp": "2026-10-01T01:00:00",
      "solar_kw": 0.0,
      "wind_kw": 8.6,
      "hydro_kw": 153.4,
      "load_kw": 459.6
    }
  ]
}
```

#### Contract Rules:
- **Top-level keys:** Strictly `location`, `forecast_horizon_hours`, and `forecast`.
- **Record keys:** Strictly `timestamp`, `solar_kw`, `wind_kw`, `hydro_kw`, and `load_kw`.
- **Units:** All power values in kilowatts (**kW**), numeric, and strictly non-negative ($\ge 0.0$).
- **Timestamps:** Standard ISO-8601 strings in unbroken 1-hour increments.

### B. Evaluation Report: [`outputs/metrics.json`](file:///c:/GitHub/GRIDMATE/forecasting/outputs/metrics.json)
```json
{
  "metadata": {
    "project": "GridMate",
    "module": "forecasting",
    "location": "Lonavala, Maharashtra",
    "data_type": "Synthetic Demo Data (Illustrative prototype results - Not measured utility data)",
    "is_synthetic": true,
    "train_test_split": "80:20 Chronological",
    "train_samples": 6988,
    "test_samples": 1748
  },
  "targets": {
    "solar_kw": { "mae": 1.4888, "rmse": 2.8671, "r2": 0.9984 },
    "wind_kw": { "mae": 3.3141, "rmse": 5.9659, "r2": 0.9896 },
    "hydro_kw": { "mae": 2.5249, "rmse": 3.1911, "r2": 0.9527 },
    "load_kw": { "mae": 12.679, "rmse": 15.8814, "r2": 0.9821 }
  }
}
```

---

## 14. How to Run the Automated Test Suite

The test suite contains 32 comprehensive unit and integration tests covering preprocessing, feature engineering, models, contract schemas, scenarios, edge cases, and recursive prediction.

```powershell
# Run the complete test suite from repository root:
python -m pytest forecasting/tests/ -v

# Run a specific test module:
python -m pytest forecasting/tests/test_forecast_contract.py -v
python -m pytest forecasting/tests/test_scenarios.py -v
```

Expected output:
```text
============================= 32 passed in ~13s =============================
```

---

## 15. Known Limitations

1. **Synthetic Demonstration Data:**
   - The models are trained on simulated data reflecting Western Ghats climatic patterns. These results benchmark module capabilities and do not represent utility-grade field accuracy.
2. **Weather Forecast Uncertainty (Oracle Weather):**
   - Offline renewable evaluation assumes perfect future weather inputs. In live field deployment, Numerical Weather Prediction (NWP) forecasts carry inherent atmospheric forecast errors.
3. **Autoregressive Compounding in Multi-Hour Load:**
   - Multi-step recursive forecasting rolls predictions forward. Small prediction variances at $h=1$ compound over the 24-hour horizon.
4. **Hydrological Lag Simplicity:**
   - Hydro inflow is modeled as a 72-hour smoothed rainfall proxy. Utility-grade hydro dispatch would incorporate reservoir head level and dam sluice dynamics.

---

## 16. Integration with Member 2 (Energy Optimization)

Member 2's optimization engine (`optimization/`) consumes `forecasting/outputs/forecast.json` to configure the PyPSA power network and solve for optimal battery dispatch, grid import, and curtailment via HiGHS.

### Handoff Protocol:
1. **File Location:** [`forecasting/outputs/forecast.json`](file:///c:/GitHub/GRIDMATE/forecasting/outputs/forecast.json).
2. **Consumption in Python (Member 2):**
   ```python
   import json
   from pathlib import Path

   forecast_path = Path("forecasting/outputs/forecast.json")
   with open(forecast_path, "r", encoding="utf-8") as f:
       data = json.load(f)

   # Member 2 extracts generation profiles and load
   records = data["forecast"]
   solar_profile = [r["solar_kw"] for r in records]
   wind_profile  = [r["wind_kw"] for r in records]
   hydro_profile = [r["hydro_kw"] for r in records]
   load_profile  = [r["load_kw"] for r in records]
   ```
3. **Integration Rule:** The keys (`solar_kw`, `wind_kw`, `hydro_kw`, `load_kw`) and JSON structure are frozen per the master architecture contract and must not be altered independently.

