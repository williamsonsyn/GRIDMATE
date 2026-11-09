from fastapi import APIRouter, HTTPException

from ..models.schemas import ForecastResponse, Scenario
from ..services.forecasting_service import ForecastError
from ..services.scenario_service import service

router = APIRouter(tags=["forecast"])


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(scenario: Scenario | None = None) -> ForecastResponse:
    try:
        return service.get_forecast(scenario)
    except ForecastError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
