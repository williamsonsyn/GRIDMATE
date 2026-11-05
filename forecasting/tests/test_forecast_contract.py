"""
test_forecast_contract.py
=========================
Automated tests for the shared forecast.json contract schema and serialization.
"""

from datetime import datetime
import json
import pytest

from forecasting.src.predict import generate_forecast
from forecasting.src.utils import validate_forecast_contract, LOCATION_NAME


@pytest.mark.parametrize("horizon", [6, 12, 24])
def test_forecast_horizons_and_contract(horizon):
    """Verify that 6, 12, and 24-hour horizons strictly satisfy the shared contract."""
    payload = generate_forecast(horizon=horizon, scenario="normal", save_output=False)

    # Validate top-level keys
    assert set(payload.keys()) == {"location", "forecast_horizon_hours", "forecast"}
    assert payload["location"] == LOCATION_NAME
    assert payload["forecast_horizon_hours"] == horizon

    forecast = payload["forecast"]
    assert isinstance(forecast, list)
    assert len(forecast) == horizon

    # Validate record keys and values
    expected_record_keys = {"timestamp", "solar_kw", "wind_kw", "hydro_kw", "load_kw"}
    timestamps = []

    for idx, record in enumerate(forecast):
        assert set(record.keys()) == expected_record_keys
        # Check numeric, finite, non-negative
        for key in ["solar_kw", "wind_kw", "hydro_kw", "load_kw"]:
            val = record[key]
            assert isinstance(val, (int, float))
            assert val >= 0.0

        # Check ISO-8601 timestamp
        dt = datetime.fromisoformat(record["timestamp"])
        timestamps.append(dt)

    # Check consecutive 1-hour spacing
    for i in range(1, len(timestamps)):
        delta = timestamps[i] - timestamps[i - 1]
        assert delta.total_seconds() == 3600


def test_invalid_horizon_raises_error():
    """Verify horizons outside 6-24 hours raise ValueError."""
    with pytest.raises(ValueError, match="Forecast horizon must be between 6 and 24"):
        generate_forecast(horizon=5, save_output=False)

    with pytest.raises(ValueError, match="Forecast horizon must be between 6 and 24"):
        generate_forecast(horizon=48, save_output=False)


def test_json_serialization_validity():
    """Verify the generated forecast is valid, round-trip JSON serializable."""
    payload = generate_forecast(horizon=24, scenario="normal", save_output=False)

    # Serialize
    json_str = json.dumps(payload, indent=2)
    assert isinstance(json_str, str)

    # Deserialize
    recovered = json.loads(json_str)
    assert recovered == payload

    # Validate contract
    validate_forecast_contract(recovered, horizon=24)


def test_contract_validator_catches_violations():
    """Verify validate_forecast_contract rejects illegal fields, types, or negative numbers."""
    valid_payload = generate_forecast(horizon=6, scenario="normal", save_output=False)

    # 1. Extra top-level metadata key
    bad_top = valid_payload.copy()
    bad_top["extra_metadata"] = "not_allowed"
    with pytest.raises(ValueError, match="forecast.json contract violation"):
        validate_forecast_contract(bad_top, horizon=6)

    # 2. Negative power target
    bad_power = json.loads(json.dumps(valid_payload))
    bad_power["forecast"][0]["solar_kw"] = -5.0
    with pytest.raises(ValueError, match="is negative"):
        validate_forecast_contract(bad_power, horizon=6)

    # 3. Wrong location
    bad_loc = valid_payload.copy()
    bad_loc["location"] = "Mumbai"
    with pytest.raises(ValueError, match="forecast.json location violation"):
        validate_forecast_contract(bad_loc, horizon=6)

