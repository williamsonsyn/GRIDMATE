# GridMate — AI Forecasting Module (Version 2)

**Project:** GridMate — From Weather to Watts, Intelligently
**Module:** AI Forecasting
**Location:** Lonavala, Maharashtra, India
**Developer Role:** Member 1 — AI Forecasting Engineer

## 1. Overview

The GridMate AI Forecasting Module predicts renewable energy generation and electricity demand for a microgrid system.

It generates forecasts for four variables:

- `solar_kw` — Solar power generation
- `wind_kw` — Wind power generation
- `hydro_kw` — Hydro power generation
- `load_kw` — Electricity demand

The module uses machine learning models based on XGBoost and provides forecasts through a standardized JSON output for integration with the energy optimization module.

This is Version 2 of the forecasting implementation. The original `forecasting/` directory contains Version 1 and is maintained separately.

## 2. Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.12 | Core programming language |
| Pandas | Data processing |
| NumPy | Numerical operations |
| XGBoost | Machine learning models |
| Scikit-learn | Evaluation metrics |
| Joblib | Model serialization |
| Matplotlib | Visualization |
| Pytest | Automated testing |

## 3. Project Structure

```text
forecasting_real_data/
│
├── data/
│   ├── training_dataset.csv
│   ├── testing_dataset.csv
│   ├── solar_train.csv
│   ├── solar_test.csv
│   ├── wind_train.csv
│   ├── wind_test.csv
│   ├── hydro_train.csv
│   ├── hydro_test.csv
│   ├── load_train.csv
│   └── load_test.csv
│
├── models/
│   ├── solar_model.joblib
│   ├── wind_model.joblib
│   ├── hydro_model.joblib
│   ├── load_model.joblib
│   ├── wind_experiment_model.joblib
│   └── hydro_experiment_model.joblib
│
├── src/
│   ├── train.py
│   ├── train_experiments.py
│   └── predict.py
│
├── outputs/
│   ├── metrics.json
│   ├── experiment_metrics.json
│   ├── forecast.json
│   ├── forecast_cloudy.json
│   ├── forecast_monsoon.json
│   ├── forecast_high_wind.json
│   └── forecast_peak_demand.json
│
├── tests/
│   └── test_predict.py
│
└── README.md
```

## 4. Dataset Description

The module uses an hourly synthetic demonstration dataset representing illustrative weather, hydrological conditions, renewable generation and electricity demand for Lonavala.

Dataset characteristics:

- Original dataset: 8,760 hourly observations.
- Time period: January–December 2025.
- Features include temperature, humidity, solar irradiance, cloud cover, wind speed, wind direction, rainfall and water flow.
- Target variables include solar generation, wind generation, hydro generation and electricity load.
- Chronological train/test split: 80:20.

After the 24-hour lag feature preparation:

| Dataset | Records |
|---|---:|
| Training | 6,988 |
| Testing | 1,748 |
| Total | 8,736 |

**Data provenance disclaimer:** The dataset was generated using AI-created formulas. It is synthetic demonstration data, not verified historical measurements from Lonavala utilities or weather stations. Model metrics and forecasts must not be interpreted as validated real-world performance.

## 5. Installation and Setup

Python 3.12 is recommended.

Activate the existing project virtual environment from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required packages if they are not already installed:

```powershell
python -m pip install pandas numpy xgboost scikit-learn joblib matplotlib pytest
```

## 6. Model Training

The four baseline models are trained independently.

Run from the repository root:

```powershell
python forecasting_real_data/src/train.py
```

The script trains models for:

1. Solar generation
2. Wind generation
3. Hydro generation
4. Electricity demand

The trained models are saved in `forecasting_real_data/models/`.

Evaluation metrics are saved in:

`forecasting_real_data/outputs/metrics.json`

### 6.1 Feature Engineering Experiments

An additional experiment script evaluates cyclical transformations for wind direction and time-based features.

Run:

```powershell
python forecasting_real_data/src/train_experiments.py
```

Experimental artifacts and comparative metrics are saved separately.

The experimental wind model is available as an alternative to the baseline wind model. The hydro baseline is retained because the cyclical hydro experiment performed worse on the held-out test set.

## 7. Model Evaluation

The baseline XGBoost models were evaluated using:

- Mean Absolute Error (MAE)
- Root Mean Squared Error (RMSE)
- Coefficient of Determination (R²)

### Baseline model metrics

| Model | Dataset | MAE | RMSE | R² |
|---|---|---:|---:|---:|
| Solar | Train | 9.36 | 20.15 | 0.9772 |
| Solar | Test | 8.10 | 20.75 | 0.9762 |
| Wind | Train | 8.39 | 17.85 | 0.8223 |
| Wind | Test | 22.34 | 48.94 | 0.1520 |
| Hydro | Train | 4.24 | 7.42 | 0.9956 |
| Hydro | Test | 13.01 | 15.07 | -0.7383 |
| Load | Train | 16.04 | 20.37 | 0.9773 |
| Load | Test | 17.78 | 23.07 | 0.9704 |

These metrics are specific to the synthetic demonstration dataset and its chronological split.

### Experimental results

The cyclical wind experiment improved held-out test R² from 0.1520 to approximately 0.2678.

The cyclical hydro experiment degraded held-out test R² from -0.7383 to approximately -4.9384.

Therefore, the experimental wind model is available as a candidate, while the hydro baseline remains the selected model.

## 8. Forecast Generation

The prediction engine is implemented in:

`forecasting_real_data/src/predict.py`

It supports forecast horizons of 6, 12 and 24 hours.

### Normal forecast

```powershell
python forecasting_real_data/src/predict.py --scenario normal --horizon 24 --wind-model experiment
```

### Cloudy scenario

```powershell
python forecasting_real_data/src/predict.py --scenario cloudy --horizon 12 --wind-model experiment
```

### Heavy monsoon scenario

```powershell
python forecasting_real_data/src/predict.py --scenario heavy_monsoon --horizon 6 --wind-model experiment
```

### High wind scenario

```powershell
python forecasting_real_data/src/predict.py --scenario high_wind --horizon 12 --wind-model experiment
```

### Peak demand scenario

```powershell
python forecasting_real_data/src/predict.py --scenario peak_demand --horizon 24 --wind-model experiment
```

For the complete list of available command-line options:

```powershell
python forecasting_real_data/src/predict.py --help
```

### Available scenarios

| Scenario | Description |
|---|---|
| `normal` | Standard demonstration conditions |
| `cloudy` | Reduced solar irradiance and increased cloud cover |
| `heavy_monsoon` | Heavy rainfall, high humidity and increased water flow |
| `high_wind` | Increased wind speed for a wind-generation stress scenario |
| `peak_demand` | Increased electricity demand |

The prediction engine supports baseline and experimental wind model selection.

The default demonstration weather inputs are derived deterministically from historical synthetic data. They are not live weather forecasts.

For actual future-weather input, the prediction interface also supports a custom weather DataFrame containing the required timestamp and weather/hydrology features. Refer to the validation implemented in `src/predict.py`.

## 9. Forecasting Methodology

The module uses separate XGBoost regression models for each energy variable.

Important inference features include:

- Weather variables
- Calendar features
- Historical load lag-1
- Historical load lag-24
- Selected weather lag features

The electricity demand model uses recursive forecasting.

For each future hour, the previous predicted load is fed into the next prediction as the lag-1 feature. The lag-24 feature is taken from the appropriate historical observation for the supported forecast horizon.

The pipeline also includes physical output guards, including non-negative generation and nighttime solar generation handling.

## 10. JSON Output Contract

Forecast results are exported as JSON for integration with Member 2's energy optimization module.

The top-level structure contains exactly:

- `location`
- `forecast_horizon_hours`
- `forecast`

Each forecast record contains:

- `timestamp`
- `solar_kw`
- `wind_kw`
- `hydro_kw`
- `load_kw`

Example structure:

```json
{
  "location": "Lonavala",
  "forecast_horizon_hours": 24,
  "forecast": [
    {
      "timestamp": "2026-01-01T00:00:00",
      "solar_kw": 0.0,
      "wind_kw": 4.0,
      "hydro_kw": 104.79,
      "load_kw": 549.97
    }
  ]
}
```

The example values are illustrative. Actual output files contain the complete forecast horizon.

The generated demonstration files are stored in `forecasting_real_data/outputs/`.

## 11. Automated Testing

Version 2 has an automated pytest suite covering:

- Forecast horizons
- All five scenarios
- Baseline and experimental wind models
- JSON schema and timestamp continuity
- Non-negative and finite outputs
- Input validation and leakage prevention
- Recursive load forecasting
- Peak-demand scenario mechanics
- Output file persistence
- Deterministic demonstration inputs

Run Version 2 tests:

```powershell
python -m pytest forecasting_real_data/tests/ -v
```

Run both Version 1 and Version 2 test suites:

```powershell
python -m pytest forecasting/tests/ forecasting_real_data/tests/ -v
```

The combined test suite has successfully passed **100 tests** in the development environment.

## 12. Known Limitations

1. The dataset is synthetic and does not represent verified real-world Lonavala observations.
2. Wind generalization remains limited on the held-out test set.
3. Hydro performance is weak on the held-out test set.
4. The cyclical hydro experiment did not improve performance.
5. Default forecast weather inputs are demonstration inputs rather than live meteorological forecasts.
6. The evaluation metrics are based on the provided chronological holdout and should not be interpreted as real-world operational accuracy.
7. High-wind scenarios may involve extrapolation beyond the training feature range.

Further improvement requires validated historical weather, renewable generation, hydrological and electricity-demand observations, followed by retraining and real-world validation.

## 13. Version Information

**Module:** GridMate AI Forecasting
**Version:** 2
**Branch:** `feature/ai-forecasting-real-data`
**Primary Location:** Lonavala, Maharashtra
**Status:** Forecasting implementation and combined automated tests completed.

---

*GridMate — From Weather to Watts, Intelligently.*
