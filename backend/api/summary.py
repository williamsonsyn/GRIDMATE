"""GET /api/scenarios/compare and /api/scenarios/summary — run all scenarios and return comparison."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import Scenario, ScenarioSummaryResponse
from ..services import optimization_service
from ..services.forecasting_service import ForecastError
from ..services.optimization_service import OptimizationError
from ..services.scenario_service import service

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios/compare", response_model=ScenarioSummaryResponse)
@router.get("/scenarios/run-all", response_model=ScenarioSummaryResponse)
@router.get("/scenarios/summary", response_model=ScenarioSummaryResponse)
def get_scenarios_summary(date: str | None = None) -> ScenarioSummaryResponse:
    """Run all scenarios from optimization/src/run_scenarios.py and return them together."""
    try:
        base_forecast = None
        if date:
            forecast_data, _, _, _ = service._forecast(Scenario.normal, date)
            base_forecast = forecast_data
        rows = optimization_service.run_all_scenarios(base_forecast=base_forecast)
        return ScenarioSummaryResponse(rows=rows)
    except (ForecastError, OptimizationError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to run scenarios: {exc}",
        ) from exc

