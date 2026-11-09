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
        self._current_date: str | None = None
        self._forecasts: dict[str, tuple[JsonDict, str, list[str], str | None]] = {}
        self._results: dict[str, tuple[JsonDict, str, list[str]]] = {}

    @property
    def current(self) -> Scenario:
        return self._current

    @property
    def current_date(self) -> str | None:
        return self._current_date

    def reset(self) -> None:
        with self._lock:
            self._current = Scenario.normal
            self._current_date = None
            self._forecasts.clear()
            self._results.clear()

    def _key(self, scenario: Scenario, date: str | None = None) -> str:
        return f"{scenario.value}::{date or 'baseline'}"

    def _meta(
        self,
        scenario: Scenario,
        f_src: str,
        o_src: str | None,
        warnings: list[str],
        date: str | None = None,
        note: str | None = None,
    ) -> Meta:
        return Meta(
            scenario=scenario,
            label=config.DATA_LABEL,
            forecast_source=f_src,  # type: ignore[arg-type]
            optimization_source=o_src,  # type: ignore[arg-type]
            generated_at=_now(),
            warnings=warnings,
            date=date,
            note=note,
        )

    # --- forecast -------------------------------------------------------
    def _forecast(
        self, scenario: Scenario, date: str | None = None
    ) -> tuple[JsonDict, str, list[str], str | None]:
        with self._lock:
            key = self._key(scenario, date)
            if key not in self._forecasts:
                if date:
                    self._forecasts[key] = forecasting_service.get_forecast_for_date(
                        date, scenario.value
                    )
                else:
                    data, src, warns = forecasting_service.get_forecast(scenario.value)
                    self._forecasts[key] = (data, src, warns, None)
            return self._forecasts[key]

    def get_forecast(
        self, scenario: Scenario | None = None, date: str | None = None
    ) -> ForecastResponse:
        sc = scenario or self._current
        dt = date if date is not None else self._current_date
        data, src, warns, note = self._forecast(sc, dt)
        return ForecastResponse(
            **data,
            scenario=sc,
            date=dt,
            note=note,
            meta=self._meta(sc, src, None, warns, date=dt, note=note),
        )

    def select_scenario(
        self, scenario: Scenario, date: str | None = None
    ) -> ForecastResponse:
        """Set the active scenario and date and return its (updated) forecast."""
        with self._lock:
            self._current = scenario
            self._current_date = date
        return self.get_forecast(scenario, date)

    # --- optimization ---------------------------------------------------
    def _result(
        self, scenario: Scenario, date: str | None = None
    ) -> tuple[JsonDict, str, list[str]]:
        with self._lock:
            key = self._key(scenario, date)
            if key not in self._results:
                forecast, _, f_warns, _ = self._forecast(scenario, date)
                result, src, o_warns = optimization_service.optimize(forecast, scenario.value)
                self._results[key] = (result, src, f_warns + o_warns)
            return self._results[key]

    def get_dispatch(
        self, scenario: Scenario | None = None, date: str | None = None
    ) -> DispatchResponse:
        sc = scenario or self._current
        dt = date if date is not None else self._current_date
        result, o_src, warns = self._result(sc, dt)
        _, f_src, _, note = self._forecast(sc, dt)
        return DispatchResponse(
            location=result["location"],
            dispatch=result["dispatch"],
            scenario=sc,
            meta=self._meta(sc, f_src, o_src, warns, date=dt, note=note),
        )

    def get_metrics(
        self, scenario: Scenario | None = None, date: str | None = None
    ) -> MetricsResponse:
        sc = scenario or self._current
        dt = date if date is not None else self._current_date
        result, o_src, warns = self._result(sc, dt)
        _, f_src, _, note = self._forecast(sc, dt)
        return MetricsResponse(
            scenario=sc,
            metrics=Metrics(**result["metrics"]),
            totals=compute_totals(result["dispatch"]),
            system=SystemInfo(**optimization_service.get_system_info()),
            cost=result.get("cost"),
            meta=self._meta(sc, f_src, o_src, warns, date=dt, note=note),
        )

    def run(
        self, scenario: Scenario | None = None, date: str | None = None
    ) -> OptimizeResponse:
        """Full pipeline: scenario (+ date) -> forecast -> optimization -> dispatch -> metrics."""
        sc = scenario or self._current
        dt = date if date is not None else self._current_date
        with self._lock:
            self._current = sc
            self._current_date = dt
            t0 = time.perf_counter()
            forecast = self.get_forecast(sc, dt)
            t1 = time.perf_counter()
            dispatch = self.get_dispatch(sc, dt)
            metrics = self.get_metrics(sc, dt)
            t2 = time.perf_counter()
        return OptimizeResponse(
            scenario=sc,
            forecast=forecast,
            dispatch=dispatch,
            metrics=metrics,
            timings_ms={
                "forecast": round((t1 - t0) * 1000, 1),
                "optimization": round((t2 - t1) * 1000, 1),
            },
        )


service = ScenarioService()
