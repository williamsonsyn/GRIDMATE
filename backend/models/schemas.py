"""Pydantic schemas. These mirror the API contracts in the Member 4 spec."""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

JsonDict = dict[str, Any]


class Scenario(str, Enum):
    normal = "normal"
    cloudy = "cloudy"
    heavy_monsoon = "heavy_monsoon"
    high_wind = "high_wind"
    peak_demand = "peak_demand"


class Meta(BaseModel):
    scenario: Scenario
    label: str
    forecast_source: Literal["model", "mock"]
    optimization_source: Literal["pypsa", "mock"] | None = None
    generated_at: str
    warnings: list[str] = Field(default_factory=list)


class ForecastPoint(BaseModel):
    timestamp: str
    solar_kw: float
    wind_kw: float
    hydro_kw: float
    load_kw: float


class ForecastResponse(BaseModel):
    location: str
    forecast_horizon_hours: int
    forecast: list[ForecastPoint]
    scenario: Scenario
    meta: Meta


class DispatchPoint(BaseModel):
    timestamp: str
    solar_kw: float
    wind_kw: float
    hydro_kw: float
    battery_kw: float  # > 0 discharging, < 0 charging
    grid_kw: float
    load_kw: float
    curtailment_kw: float
    battery_soc_kwh: float


class DispatchResponse(BaseModel):
    location: str
    dispatch: list[DispatchPoint]
    scenario: Scenario
    meta: Meta


class Metrics(BaseModel):
    renewable_penetration_percent: float
    grid_dependency_percent: float
    curtailment_percent: float
    battery_utilization_percent: float
    estimated_co2_avoided_kg: float


class Totals(BaseModel):
    """Energy totals derived from the dispatch (kWh, 1-hour steps)."""

    load_kwh: float
    renewable_generation_kwh: float
    grid_import_kwh: float
    curtailed_kwh: float
    battery_charged_kwh: float
    battery_discharged_kwh: float


class SystemInfo(BaseModel):
    battery_capacity_kwh: float
    battery_max_charge_kw: float
    battery_max_discharge_kw: float
    battery_min_soc_kwh: float
    grid_capacity_kw: float


class MetricsResponse(BaseModel):
    scenario: Scenario
    metrics: Metrics
    totals: Totals
    system: SystemInfo
    cost: JsonDict | None = None
    meta: Meta


class ScenarioInfo(BaseModel):
    id: Scenario
    label: str
    description: str


class ScenarioRequest(BaseModel):
    scenario: Scenario


class OptimizeRequest(BaseModel):
    scenario: Scenario | None = None


class OptimizeResponse(BaseModel):
    scenario: Scenario
    forecast: ForecastResponse
    dispatch: DispatchResponse
    metrics: MetricsResponse
    timings_ms: dict[str, float]


class AssetsResponse(BaseModel):
    assets: JsonDict
    demand_zones: JsonDict
    water_features: JsonDict
    power_lines: JsonDict
    energy_flow: JsonDict
    map_config: JsonDict
    source: Literal["digital_twin", "mock"]
    label: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    mode: str
    components: dict[str, bool]
    detail: dict[str, str] = Field(default_factory=dict)
