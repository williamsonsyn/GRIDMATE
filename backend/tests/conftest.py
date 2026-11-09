import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app
from backend.services.scenario_service import service


@pytest.fixture(autouse=True)
def _fresh_service():
    service.reset()
    yield
    service.reset()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setattr(config, "MODE", "mock")
    service.reset()
