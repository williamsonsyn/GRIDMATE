# GridMate — Member 1 Task Specification
## AI Forecasting Engineer

### Project
GridMate — **From Weather to Watts, Intelligently.**  
Prototype deadline: **10 October 2026**  
Testbed: **Lonavala, Maharashtra**

### Your role
You own the **AI Forecasting** module.

Your question is:

> Given weather, water and historical demand conditions, how much solar, wind, hydro generation and electricity demand should we expect over the next few hours?

You do **not** build the optimizer, GIS map, FastAPI backend, or React dashboard.

## 1. Responsibilities

Build forecasts for:

- Solar generation (`solar_kw`)
- Wind generation (`wind_kw`)
- Hydro generation (`hydro_kw`)
- Electricity demand/load (`load_kw`)

The module must work independently and produce a standardized `forecast.json` consumed by Member 2.

## 2. Technology

Use:

- Python 3.12
- Pandas
- NumPy
- XGBoost
- Scikit-learn where useful
- Joblib if model persistence is needed
- Matplotlib/Plotly only for model evaluation

Do not introduce unnecessary ML frameworks or deep learning.

## 3. Inputs

Support features such as:

```text
timestamp
temperature
humidity
solar_irradiance
cloud_cover
wind_speed
wind_direction
rainfall
pressure
water_flow / reservoir_level (if available)
historical_load
```

Create time features such as:

```text
hour
day_of_week
day_of_year
month
is_weekend
```

Use sensible feature sets for each target.

## 4. Data Strategy

Do not block development waiting for real data.

Create reproducible synthetic/demo data when required. Clearly label it as synthetic/demo data.

Never present synthetic values as measured Lonavala data.

Keep the pipeline modular:

```text
data loading/generation
        ↓
preprocessing
        ↓
feature engineering
        ↓
model training
        ↓
prediction
        ↓
forecast.json
```

## 5. Forecast Horizon

Use a configurable short-term horizon:

```text
6–24 hours
```

Prefer 24 hourly predictions if practical.

## 6. Models

Use separate XGBoost regression models for:

```text
solar_kw
wind_kw
hydro_kw
load_kw
```

Time-series train/test splitting must be chronological. Avoid future-data leakage.

## 7. Evaluation

Calculate at least:

```text
MAE
RMSE
R²
```

for each target.

Keep evaluation results in a machine-readable file such as `metrics.json`.

## 8. Required Output Contract

Create `forecast.json`:

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

Every record must contain:

```text
timestamp
solar_kw
wind_kw
hydro_kw
load_kw
```

Values must be numeric and non-negative.

## 9. Python Interface

Provide a clean callable interface such as:

```python
def generate_forecast(input_data, horizon=24):
    ...
```

The rest of GridMate should not need to know how XGBoost works internally.

## 10. Scenario Support

Support:

```text
normal
cloudy
heavy_monsoon
high_wind
peak_demand
```

Examples:

```text
Cloudy Day → irradiance down → solar forecast down
Heavy Monsoon → rainfall up, irradiance down → hydro up, solar down
Peak Demand → load up
```

Keep scenarios simple and deterministic.

## 11. Folder Structure

```text
forecasting/
├── data/
├── models/
├── notebooks/
├── src/
│   ├── preprocessing.py
│   ├── features.py
│   ├── train.py
│   ├── predict.py
│   ├── evaluation.py
│   └── utils.py
├── outputs/
│   ├── forecast.json
│   └── metrics.json
├── tests/
├── requirements.txt
└── README.md
```

## 12. Do NOT Build

Do not build:

- React frontend
- FastAPI backend
- MapLibre/GIS system
- PyPSA optimization
- battery dispatch
- authentication

## 13. Definition of DONE

Your module is done when:

1. Sample data loads/generates.
2. Features are created.
3. XGBoost models train.
4. Models can be saved/loaded.
5. 6–24 hourly forecasts are generated.
6. Solar, wind, hydro and load are present.
7. Metrics are generated.
8. `forecast.json` follows the exact contract.
9. Scenarios change the forecast.
10. Another developer can run it from the README.

Primary command:

```bash
python src/predict.py
```

Expected result:

```text
outputs/forecast.json
```

## 14. Integration

Your interface is:

```text
YOUR MODULE
    ↓
forecast.json
    ↓
Member 2 Optimization
```

Do not change the JSON schema without informing the team.

## 15. Git

```bash
git checkout -b feature/ai-forecasting
git add forecasting/
git commit -m "Add AI forecasting pipeline"
git push origin feature/ai-forecasting
```

Use a Pull Request into `main`.

## 16. AI Handoff Prompt

When giving this file to an AI coding assistant, say:

> Build only the Member 1 AI Forecasting module described here. Follow the folder structure, JSON contract and acceptance criteria exactly. Use Python, Pandas, NumPy and XGBoost. Use clearly labelled synthetic/demo data if real data is unavailable. Do not build the frontend, FastAPI, GIS or PyPSA optimization. Prefer a simple, runnable, modular prototype over unnecessary complexity.

## 17. Final Deliverables

```text
forecasting/
source code
sample data
model files if appropriate
forecast.json
metrics.json
tests
README.md
```
