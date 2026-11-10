from fastapi import APIRouter, HTTPException

try:
    from ..models.schemas import DispatchResponse, Scenario
    from ..services.forecasting_service import ForecastError
    from ..services.optimization_service import OptimizationError
    from ..services.scenario_service import service
except (ImportError, ValueError):
    from models.schemas import DispatchResponse, Scenario  # type: ignore[no-redef]
    from services.forecasting_service import ForecastError  # type: ignore[no-redef]
    from services.optimization_service import OptimizationError  # type: ignore[no-redef]
    from services.scenario_service import service  # type: ignore[no-redef]

router = APIRouter(tags=["dispatch"])


@router.get("/dispatch", response_model=DispatchResponse)
def get_dispatch(scenario: Scenario | None = None, date: str | None = None) -> DispatchResponse:
    try:
        return service.get_dispatch(scenario, date=date)
    except (ForecastError, OptimizationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
