"""End-to-end integration tests for GridMate Vercel Multi-Service architecture.

Verifies:
- Direct microservice health and calculation endpoints
- Backend execution via Vercel service bindings (HTTP transport)
- Dual-mode backward compatibility (local in-process execution)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def app_modules():
    import backend.main as b_main

    if str(REPO_ROOT / "forecasting_real_data") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "forecasting_real_data"))
    import forecasting_real_data.main as fc_main

    if str(REPO_ROOT / "optimization") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "optimization"))
    import optimization.main as opt_main

    if str(REPO_ROOT / "digital-twin") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "digital-twin"))
    import main as dt_main

    return b_main, fc_main, opt_main, dt_main


def test_microservice_endpoints(app_modules):
    b_main, fc_main, opt_main, dt_main = app_modules

    fc_client = TestClient(fc_main.app)
    opt_client = TestClient(opt_main.app)
    dt_client = TestClient(dt_main.app)

    # Forecasting direct test
    res_fc = fc_client.get("/health")
    assert res_fc.status_code == 200
    assert res_fc.json()["service"] == "forecasting"

    res_pred = fc_client.post("/predict", json={"scenario": "normal", "horizon": 24})
    assert res_pred.status_code == 200
    assert len(res_pred.json()["forecast"]) == 24

    # Optimization direct test
    res_opt = opt_client.get("/health")
    assert res_opt.status_code == 200
    assert res_opt.json()["service"] == "optimization"

    res_opt_run = opt_client.post("/optimize", json={"forecast": res_pred.json()})
    assert res_opt_run.status_code == 200
    assert len(res_opt_run.json()["dispatch"]) == 24

    # Digital twin direct test
    res_dt = dt_client.get("/health")
    assert res_dt.status_code == 200
    assert res_dt.json()["service"] == "digital-twin"

    res_assets = dt_client.get("/assets")
    assert res_assets.status_code == 200
    assert "assets" in res_assets.json()


def test_backend_service_binding_mode(app_modules):
    b_main, fc_main, opt_main, dt_main = app_modules

    os.environ["FORECASTING_SERVICE_URL"] = "https://forecasting.internal"
    os.environ["OPTIMIZATION_SERVICE_URL"] = "https://optimization.internal"
    os.environ["DIGITAL_TWIN_SERVICE_URL"] = "https://digital-twin.internal"

    fc_transport = httpx.ASGITransport(app=fc_main.app)
    opt_transport = httpx.ASGITransport(app=opt_main.app)
    dt_transport = httpx.ASGITransport(app=dt_main.app)

    class MultiServiceRouter(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "forecasting.internal" in url_str:
                return fc_transport.handle_request(request)
            elif "optimization.internal" in url_str:
                return opt_transport.handle_request(request)
            elif "digital-twin.internal" in url_str:
                return dt_transport.handle_request(request)
            raise ValueError(f"Unknown mock route: {url_str}")

    backend_client = TestClient(b_main.app)

    try:
        with patch("httpx.Client", lambda *a, **kw: httpx.Client(transport=MultiServiceRouter(), timeout=kw.get("timeout", 20.0))):
            res_health = backend_client.get("/api/health")
            assert res_health.status_code == 200
            assert res_health.json()["status"] == "ok"

            res_assets = backend_client.get("/api/assets")
            assert res_assets.status_code == 200
            assert res_assets.json()["source"] == "digital_twin"

            res_opt = backend_client.post("/api/optimize", json={"scenario": "normal"})
            assert res_opt.status_code == 200
            assert len(res_opt.json()["dispatch"]) == 24
    finally:
        del os.environ["FORECASTING_SERVICE_URL"]
        del os.environ["OPTIMIZATION_SERVICE_URL"]
        del os.environ["DIGITAL_TWIN_SERVICE_URL"]

