from fastapi import APIRouter, HTTPException

from ..models.schemas import DispatchResponse, Scenario
from ..services.forecasting_service import ForecastError
from ..services.optimization_service import OptimizationError
from ..services.scenario_service import service

router = APIRouter(tags=["dispatch"])


@router.get("/dispatch", response_model=DispatchResponse)
def get_dispatch(scenario: Scenario | None = None) -> DispatchResponse:
    try:
        return service.get_dispatch(scenario)
    except (ForecastError, OptimizationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
