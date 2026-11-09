from fastapi import APIRouter, HTTPException

from ..models.schemas import (
    ForecastResponse, OptimizeRequest, OptimizeResponse, ScenarioInfo, ScenarioRequest,
)
from ..services.forecasting_service import ForecastError
from ..services.optimization_service import OptimizationError
from ..services.scenario_service import SCENARIOS, service

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios() -> list[ScenarioInfo]:
    return SCENARIOS


@router.post("/scenario", response_model=ForecastResponse)
def set_scenario(body: ScenarioRequest) -> ForecastResponse:
    """Select a scenario and return its updated forecast (step 1 of the pipeline)."""
    try:
        return service.select_scenario(body.scenario, date=body.date)
    except ForecastError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/optimize", response_model=OptimizeResponse)
def optimize(body: OptimizeRequest | None = None) -> OptimizeResponse:
    """Run scenario -> forecast -> optimization -> dispatch -> metrics."""
    try:
        sc = body.scenario if body else None
        dt = body.date if body else None
        return service.run(sc, date=dt)
    except (ForecastError, OptimizationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
