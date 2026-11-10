from fastapi import APIRouter, HTTPException

try:
    from ..models.schemas import ForecastResponse, Scenario
    from ..services.forecasting_service import ForecastError
    from ..services.scenario_service import service
except (ImportError, ValueError):
    from models.schemas import ForecastResponse, Scenario  # type: ignore[no-redef]
    from services.forecasting_service import ForecastError  # type: ignore[no-redef]
    from services.scenario_service import service  # type: ignore[no-redef]

router = APIRouter(tags=["forecast"])


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    scenario: Scenario | None = None, date: str | None = None
) -> ForecastResponse:
    try:
        return service.get_forecast(scenario, date=date)
    except ForecastError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/forecast/date", response_model=ForecastResponse)
def get_forecast_by_date(
    date: str, scenario: Scenario | None = None
) -> ForecastResponse:
    try:
        return service.get_forecast(scenario, date=date)
    except ForecastError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
