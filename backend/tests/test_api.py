"""API tests. Most use mock mode for speed; the `real` tests run the true modules."""
import collections
import pathlib

import pytest

from backend import config
from backend.services import optimization_service

SCENARIOS = ["normal", "cloudy", "heavy_monsoon", "high_wind", "peak_demand"]
FORECAST_KEYS = {"timestamp", "solar_kw", "wind_kw", "hydro_kw", "load_kw"}
DISPATCH_KEYS = FORECAST_KEYS | {"battery_kw", "grid_kw", "curtailment_kw", "battery_soc_kwh"}
METRIC_KEYS = {
    "renewable_penetration_percent", "grid_dependency_percent", "curtailment_percent",
    "battery_utilization_percent", "estimated_co2_avoided_kg",
}


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] in {"ok", "degraded"}
    assert set(body["components"]) == {"forecasting", "optimization", "digital_twin"}


def test_scenarios_listed(client):
    ids = [s["id"] for s in client.get("/api/scenarios").json()]
    assert ids == SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_forecast_contract_mock(client, mock_mode, scenario):
    r = client.get("/api/forecast", params={"scenario": scenario})
    assert r.status_code == 200
    body = r.json()
    assert body["location"] == "Lonavala"
    assert body["forecast_horizon_hours"] == 24 == len(body["forecast"])
    assert set(body["forecast"][0]) == FORECAST_KEYS
    assert "Simulation Result" in body["meta"]["label"]
    assert body["meta"]["forecast_source"] == "mock"


def test_dispatch_balance_mock(client, mock_mode):
    rows = client.get("/api/dispatch").json()["dispatch"]
    assert len(rows) == 24 and set(rows[0]) == DISPATCH_KEYS
    for r in rows:
        supply = r["solar_kw"] + r["wind_kw"] + r["hydro_kw"] + r["battery_kw"] + r["grid_kw"]
        assert supply == pytest.approx(r["load_kw"] + r["curtailment_kw"], abs=0.1)


def test_metrics_shape_mock(client, mock_mode):
    body = client.get("/api/metrics").json()
    assert set(body["metrics"]) == METRIC_KEYS
    assert body["system"]["battery_capacity_kwh"] > 0
    assert body["totals"]["load_kwh"] > 0


def test_invalid_scenario_rejected(client):
    assert client.post("/api/scenario", json={"scenario": "tornado"}).status_code == 422
    assert client.get("/api/forecast", params={"scenario": "tornado"}).status_code == 422
    assert client.post("/api/optimize", json={"scenario": "tornado"}).status_code == 422


def test_scenario_selection_persists(client, mock_mode):
    client.post("/api/scenario", json={"scenario": "high_wind"})
    assert client.get("/api/forecast").json()["scenario"] == "high_wind"
    assert client.get("/api/dispatch").json()["scenario"] == "high_wind"


def test_optimize_without_body_uses_current(client, mock_mode):
    client.post("/api/scenario", json={"scenario": "cloudy"})
    body = client.post("/api/optimize").json()
    assert body["scenario"] == "cloudy"
    assert set(body["timings_ms"]) == {"forecast", "optimization"}


def test_scenarios_change_results_mock(client, mock_mode):
    def re(s):
        return client.post("/api/optimize", json={"scenario": s}).json()["metrics"]["metrics"]
    assert re("high_wind")["renewable_penetration_percent"] > re("cloudy")["renewable_penetration_percent"]


def test_mock_assets(client, mock_mode):
    body = client.get("/api/assets").json()
    assert body["source"] == "mock" and len(body["assets"]["features"]) >= 6


def test_auto_mode_falls_back_with_warning(client, monkeypatch):
    def boom(_forecast):
        raise RuntimeError("solver exploded")
    monkeypatch.setattr(optimization_service, "run_real_optimization", boom)
    monkeypatch.setattr(config, "MODE", "auto")
    body = client.get("/api/dispatch").json()
    assert body["meta"]["optimization_source"] == "mock"
    assert any("solver exploded" in w for w in body["meta"]["warnings"])


def test_real_mode_failure_is_503(client, monkeypatch):
    def boom(_forecast):
        raise RuntimeError("solver exploded")
    monkeypatch.setattr(optimization_service, "run_real_optimization", boom)
    monkeypatch.setattr(config, "MODE", "real")
    r = client.get("/api/dispatch")
    assert r.status_code == 503 and "solver exploded" in r.json()["detail"]


def test_empty_forecast_rejected():
    with pytest.raises(optimization_service.OptimizationError):
        optimization_service.optimize({"forecast": []}, "normal")


def test_no_machine_specific_paths():
    bad = ("C:\\", "/home/", "/Users/")
    for f in pathlib.Path(config.REPO_ROOT, "backend").rglob("*.py"):
        if f.parent.name == "tests":
            continue
        text = f.read_text()
        assert not any(b in text for b in bad), f


# ---------------- real module integration (slower) ----------------

@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.setattr(config, "MODE", "real")
    service_reset = __import__("backend.services.scenario_service", fromlist=["service"]).service
    service_reset.reset()


@pytest.mark.real
def test_real_pipeline_energy_balance(client, real_mode):
    body = client.post("/api/optimize", json={"scenario": "normal"}).json()
    assert body["forecast"]["meta"]["forecast_source"] == "model"
    assert body["dispatch"]["meta"]["optimization_source"] == "pypsa"
    for r in body["dispatch"]["dispatch"]:
        supply = r["solar_kw"] + r["wind_kw"] + r["hydro_kw"] + r["battery_kw"] + r["grid_kw"]
        assert supply == pytest.approx(r["load_kw"] + r["curtailment_kw"], abs=0.1)
        assert r["grid_kw"] <= body["metrics"]["system"]["grid_capacity_kw"] + 0.01


@pytest.mark.real
def test_real_scenarios_change_forecast_and_metrics(client, real_mode):
    normal = client.post("/api/optimize", json={"scenario": "normal"}).json()
    wind = client.post("/api/optimize", json={"scenario": "high_wind"}).json()
    monsoon = client.post("/api/optimize", json={"scenario": "heavy_monsoon"}).json()
    avg = lambda b, k: sum(p[k] for p in b["forecast"]["forecast"]) / 24
    assert avg(wind, "wind_kw") > 5 * avg(normal, "wind_kw")
    assert max(p["solar_kw"] for p in monsoon["forecast"]["forecast"]) < max(
        p["solar_kw"] for p in normal["forecast"]["forecast"])
    assert (wind["metrics"]["metrics"]["renewable_penetration_percent"]
            > normal["metrics"]["metrics"]["renewable_penetration_percent"])


@pytest.mark.real
def test_real_assets(client, real_mode):
    body = client.get("/api/assets").json()
    assert body["source"] == "digital_twin"
    types = collections.Counter(f["properties"]["type"] for f in body["assets"]["features"])
    assert types == {"wind": 4, "hydro": 3, "solar": 2, "battery": 1, "grid": 1, "demand": 1}


@pytest.mark.real
def test_real_peak_demand_reports_status(client, monkeypatch):
    """Peak demand must never silently fail: either solved by PyPSA or clearly flagged."""
    monkeypatch.setattr(config, "MODE", "auto")
    body = client.post("/api/optimize", json={"scenario": "peak_demand"}).json()
    meta = body["dispatch"]["meta"]
    assert meta["optimization_source"] == "pypsa" or meta["warnings"]
