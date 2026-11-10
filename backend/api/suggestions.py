"""GET /api/suggestions — resource capacity usage and PyPSA-derived grid reduction suggestions."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.schemas import Scenario, SuggestionsResponse
from ..services import suggestions_service

router = APIRouter(tags=["suggestions"])


@router.get("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    scenario: Scenario = Scenario.normal,
    date: str | None = None,
) -> SuggestionsResponse:
    """Return resource headroom usage and top ranked capacity expansion suggestions to reduce grid use."""
    try:
        data = suggestions_service.get_suggestions(scenario=scenario, date=date)
        return SuggestionsResponse(**data)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to generate suggestions: {exc}",
        ) from exc

