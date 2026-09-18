"""Contest request/response models."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class DirectiveType(str, Enum):
    SOLAR_REDUCTION = "solar_reduction"
    MINIMUM_BATTERY_RESERVE = "minimum_battery_reserve"
    NO_CHARGE_WINDOW = "no_charge_window"
    NO_DISCHARGE_WINDOW = "no_discharge_window"
    MAX_GRID_WINDOW = "max_grid_window"
    NO_OP = "no_op"


class BatteryAction(str, Enum):
    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"


HourInt = Annotated[int, Field(ge=0, le=23)]
NonNegative = Annotated[float, Field(ge=0)]


class HourInput(BaseModel):
    hour: HourInt
    demand_kwh: NonNegative
    solar_kwh: NonNegative
    tariff_bdt_per_kwh: NonNegative


class BatteryConfig(BaseModel):
    capacity_kwh: NonNegative
    initial_energy_kwh: NonNegative
    minimum_energy_kwh: NonNegative
    max_charge_kwh_per_hour: NonNegative
    max_discharge_kwh_per_hour: NonNegative

    @model_validator(mode="after")
    def check_battery_bounds(self) -> BatteryConfig:
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError("initial_energy_kwh cannot be below minimum_energy_kwh")
        return self


class OptimizeEnergyRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    operator_notes: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=3)
    hours: list[HourInput] = Field(min_length=24, max_length=24)
    battery: BatteryConfig

    @model_validator(mode="after")
    def check_hours_cover_day(self) -> OptimizeEnergyRequest:
        hour_values = [h.hour for h in self.hours]
        if sorted(hour_values) != list(range(24)) or len(set(hour_values)) != 24:
            raise ValueError("hours must contain exactly one entry for each hour 0 through 23")
        return self


class StructuredAdjustment(BaseModel):
    """Fields depend on directive_type; unused ones stay null."""

    hours: list[HourInt] | None = None
    factor: float | None = None
    minimum_energy_kwh: NonNegative | None = None
    max_grid_kwh: NonNegative | None = None

    @field_validator("hours")
    @classmethod
    def hours_unique_ascending(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if len(value) != len(set(value)):
            raise ValueError("hours must be unique")
        if value != sorted(value):
            raise ValueError("hours must be in ascending order")
        return value

    @field_validator("factor")
    @classmethod
    def factor_in_unit_interval(cls, value: float | None) -> float | None:
        if value is not None and not (0.0 <= value <= 1.0):
            raise ValueError("factor must be between 0 and 1 inclusive")
        return value


class DirectiveInterpretation(BaseModel):
    note_index: Annotated[int, Field(ge=0)]
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: StructuredAdjustment | None
    explanation: str

    @model_validator(mode="after")
    def check_applies_semantics(self) -> DirectiveInterpretation:
        if self.directive_type == DirectiveType.NO_OP:
            if self.applies is not False:
                raise ValueError("no_op requires applies=false")
            if self.structured_adjustment is not None:
                raise ValueError("no_op requires structured_adjustment=null")
        elif not self.applies:
            raise ValueError("non-no_op directives require applies=true")
        elif self.structured_adjustment is None:
            raise ValueError("non-no_op directives require structured_adjustment")
        return self


class HourlyPlanEntry(BaseModel):
    hour: HourInt
    grid_kwh: NonNegative
    solar_used_kwh: NonNegative
    battery_action: BatteryAction
    battery_kwh: NonNegative
    battery_energy_after_kwh: NonNegative

    @model_validator(mode="after")
    def check_idle_battery_kwh(self) -> HourlyPlanEntry:
        if self.battery_action == BatteryAction.IDLE and self.battery_kwh != 0:
            raise ValueError("battery_kwh must be 0 when battery_action is idle")
        return self


class OptimizeEnergyResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: NonNegative
    total_cost_bdt: NonNegative
    peak_grid_kwh: NonNegative
    plan_summary: str

    @model_validator(mode="after")
    def check_plan_hours(self) -> OptimizeEnergyResponse:
        hour_values = [h.hour for h in self.hourly_plan]
        if sorted(hour_values) != list(range(24)) or len(set(hour_values)) != 24:
            raise ValueError("hourly_plan must contain exactly one entry for each hour 0 through 23")
        return self


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
