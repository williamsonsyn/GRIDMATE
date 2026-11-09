"""GET /api/scenarios/summary — run all 5 scenarios and return a comparison table."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import Scenario, ScenarioSummaryResponse
from ..services.forecasting_service import ForecastError
from ..services.optimization_service import OptimizationError
from ..services.scenario_service import SCENARIOS, service

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios/summary", response_model=ScenarioSummaryResponse)
def get_scenarios_summary(date: str | None = None) -> ScenarioSummaryResponse:
    """Run all scenarios through the full pipeline and return a comparison matrix."""
    rows = []
    for sc_info in SCENARIOS:
        sc = Scenario(sc_info.id)
        try:
            result = service.run(sc, date=date)
            m = result.metrics.metrics
            cost = result.metrics.cost or {}
            rows.append(
                {
                    "scenario": sc.value,
                    "label": sc_info.label,
                    "renewable_penetration_percent": m.renewable_penetration_percent,
                    "grid_dependency_percent": m.grid_dependency_percent,
                    "curtailment_percent": m.curtailment_percent,
                    "battery_utilization_percent": m.battery_utilization_percent,
                    "estimated_co2_avoided_kg": m.estimated_co2_avoided_kg,
                    "total_grid_cost_rs": float(cost.get("total_grid_cost_rs", 0)),
                    "grid_only_cost_rs": float(cost.get("grid_only_cost_rs", 0)),
                    "savings_rs": float(cost.get("savings_rs", 0)),
                    "savings_percent": float(cost.get("savings_percent", 0)),
                }
            )
        except (ForecastError, OptimizationError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Pipeline failed for scenario {sc.value}: {exc}",
            ) from exc
    return ScenarioSummaryResponse(rows=rows)

