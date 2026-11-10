from fastapi import APIRouter, HTTPException

try:
    from ..models.schemas import AssetsResponse, MetricsResponse, Scenario
    from ..services import assets_service
    from ..services.forecasting_service import ForecastError
    from ..services.optimization_service import OptimizationError
    from ..services.scenario_service import service
    from .. import config
except (ImportError, ValueError):
    from models.schemas import AssetsResponse, MetricsResponse, Scenario  # type: ignore[no-redef]
    from services import assets_service  # type: ignore[no-redef]
    from services.forecasting_service import ForecastError  # type: ignore[no-redef]
    from services.optimization_service import OptimizationError  # type: ignore[no-redef]
    from services.scenario_service import service  # type: ignore[no-redef]
    import config  # type: ignore[no-redef]

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(scenario: Scenario | None = None, date: str | None = None) -> MetricsResponse:
    try:
        return service.get_metrics(scenario, date=date)
    except (ForecastError, OptimizationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/assets", response_model=AssetsResponse)
def get_assets() -> AssetsResponse:
    try:
        layers, source = assets_service.get_assets()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Digital twin data unavailable: {exc}") from exc
    return AssetsResponse(**layers, source=source, label=config.DATA_LABEL)  # type: ignore[arg-type]
