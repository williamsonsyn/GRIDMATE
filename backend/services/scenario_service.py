"""Scenario service: orchestrates scenario -> forecast -> optimization -> metrics."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import RLock
from typing import Any

from .. import config
from ..models.schemas import (
    DispatchResponse, ForecastResponse, Meta, Metrics, MetricsResponse,
    OptimizeResponse, Scenario, ScenarioInfo, SystemInfo, Totals,
)
from . import forecasting_service, optimization_service

JsonDict = dict[str, Any]

SCENARIOS: list[ScenarioInfo] = [
    ScenarioInfo(id=Scenario.normal, label="Normal Day",
                 description="Typical weather and demand."),
    ScenarioInfo(id=Scenario.cloudy, label="Cloudy Day",
                 description="Heavy cloud cover reduces solar output."),
    ScenarioInfo(id=Scenario.heavy_monsoon, label="Heavy Monsoon",
                 description="Low solar, high rainfall and stronger hydro flow."),
    ScenarioInfo(id=Scenario.high_wind, label="High Wind",
                 description="Strong ridge winds increase wind generation."),
    ScenarioInfo(id=Scenario.peak_demand, label="Peak Demand",
                 description="Evening demand surge stresses battery and grid."),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compute_totals(rows: list[JsonDict]) -> Totals:
    """Derive energy totals from the dispatch itself (1-hour steps -> kWh)."""
    return Totals(
        load_kwh=round(sum(r["load_kw"] for r in rows), 2),
        renewable_generation_kwh=round(sum(r["solar_kw"] + r["wind_kw"] + r["hydro_kw"] for r in rows), 2),
        grid_import_kwh=round(sum(r["grid_kw"] for r in rows), 2),
        curtailed_kwh=round(sum(r["curtailment_kw"] for r in rows), 2),
        battery_charged_kwh=round(sum(-r["battery_kw"] for r in rows if r["battery_kw"] < 0), 2),
        battery_discharged_kwh=round(sum(r["battery_kw"] for r in rows if r["battery_kw"] > 0), 2),
    )


class ScenarioService:
    """Holds the currently selected scenario and caches deterministic results."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._current = Scenario.normal
        self._forecasts: dict[Scenario, tuple[JsonDict, str, list[str]]] = {}
        self._results: dict[Scenario, tuple[JsonDict, str, list[str]]] = {}

    @property
    def current(self) -> Scenario:
        return self._current

    def reset(self) -> None:
        with self._lock:
            self._current = Scenario.normal
            self._forecasts.clear()
            self._results.clear()

    def _meta(self, scenario: Scenario, f_src: str, o_src: str | None, warnings: list[str]) -> Meta:
        return Meta(
            scenario=scenario, label=config.DATA_LABEL,
            forecast_source=f_src,  # type: ignore[arg-type]
            optimization_source=o_src,  # type: ignore[arg-type]
            generated_at=_now(), warnings=warnings,
        )

    # --- forecast -------------------------------------------------------
    def _forecast(self, scenario: Scenario) -> tuple[JsonDict, str, list[str]]:
        with self._lock:
            if scenario not in self._forecasts:
                self._forecasts[scenario] = forecasting_service.get_forecast(scenario.value)
            return self._forecasts[scenario]

    def get_forecast(self, scenario: Scenario | None = None) -> ForecastResponse:
        sc = scenario or self._current
        data, src, warns = self._forecast(sc)
        return ForecastResponse(**data, scenario=sc, meta=self._meta(sc, src, None, warns))

    def select_scenario(self, scenario: Scenario) -> ForecastResponse:
        """Set the active scenario and return its (updated) forecast."""
        with self._lock:
            self._current = scenario
        return self.get_forecast(scenario)

    # --- optimization ---------------------------------------------------
    def _result(self, scenario: Scenario) -> tuple[JsonDict, str, list[str]]:
        with self._lock:
            if scenario not in self._results:
                forecast, _, f_warns = self._forecast(scenario)
                result, src, o_warns = optimization_service.optimize(forecast, scenario.value)
                self._results[scenario] = (result, src, f_warns + o_warns)
            return self._results[scenario]

    def get_dispatch(self, scenario: Scenario | None = None) -> DispatchResponse:
        sc = scenario or self._current
        result, o_src, warns = self._result(sc)
        _, f_src, _ = self._forecast(sc)
        return DispatchResponse(
            location=result["location"], dispatch=result["dispatch"], scenario=sc,
            meta=self._meta(sc, f_src, o_src, warns),
        )

    def get_metrics(self, scenario: Scenario | None = None) -> MetricsResponse:
        sc = scenario or self._current
        result, o_src, warns = self._result(sc)
        _, f_src, _ = self._forecast(sc)
        return MetricsResponse(
            scenario=sc,
            metrics=Metrics(**result["metrics"]),
            totals=compute_totals(result["dispatch"]),
            system=SystemInfo(**optimization_service.get_system_info()),
            cost=result.get("cost"),
            meta=self._meta(sc, f_src, o_src, warns),
        )

    def run(self, scenario: Scenario | None = None) -> OptimizeResponse:
        """Full pipeline: scenario -> forecast -> optimization -> dispatch -> metrics."""
        sc = scenario or self._current
        with self._lock:
            self._current = sc
            t0 = time.perf_counter()
            forecast = self.get_forecast(sc)
            t1 = time.perf_counter()
            dispatch = self.get_dispatch(sc)
            metrics = self.get_metrics(sc)
            t2 = time.perf_counter()
        return OptimizeResponse(
            scenario=sc, forecast=forecast, dispatch=dispatch, metrics=metrics,
            timings_ms={"forecast": round((t1 - t0) * 1000, 1),
                        "optimization": round((t2 - t1) * 1000, 1)},
        )


service = ScenarioService()
