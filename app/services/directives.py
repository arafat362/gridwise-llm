"""Turn validated directives into per-hour solar/battery/grid limits."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import DirectiveInterpretation, DirectiveType, HourInput


@dataclass(frozen=True)
class HourlyConstraints:
    effective_solar: list[float]
    min_energy_after: list[float]
    max_charge: list[float]
    max_discharge: list[float]
    max_grid: list[float | None]


def build_hourly_constraints(
    hours: list[HourInput],
    *,
    capacity_kwh: float,
    minimum_energy_kwh: float,
    max_charge_kwh_per_hour: float,
    max_discharge_kwh_per_hour: float,
    directives: list[DirectiveInterpretation],
) -> HourlyConstraints:
    hours_by_index = sorted(hours, key=lambda h: h.hour)
    effective_solar = [float(h.solar_kwh) for h in hours_by_index]
    min_energy_after = [float(minimum_energy_kwh)] * 24
    max_charge = [float(max_charge_kwh_per_hour)] * 24
    max_discharge = [float(max_discharge_kwh_per_hour)] * 24
    max_grid: list[float | None] = [None] * 24

    for directive in directives:
        if not directive.applies or directive.directive_type == DirectiveType.NO_OP:
            continue
        if directive.structured_adjustment is None:
            raise ValueError(f"directive {directive.directive_type} missing structured_adjustment")

        adj = directive.structured_adjustment
        affected = adj.hours or []

        if directive.directive_type == DirectiveType.SOLAR_REDUCTION:
            if adj.factor is None:
                raise ValueError("solar_reduction requires factor")
            for hour in affected:
                effective_solar[hour] *= adj.factor

        elif directive.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE:
            if adj.minimum_energy_kwh is None:
                raise ValueError("minimum_battery_reserve requires minimum_energy_kwh")
            reserve = float(adj.minimum_energy_kwh)
            if reserve > capacity_kwh:
                raise ValueError("minimum_battery_reserve exceeds battery capacity")
            for hour in affected:
                min_energy_after[hour] = max(min_energy_after[hour], reserve)

        elif directive.directive_type == DirectiveType.NO_CHARGE_WINDOW:
            for hour in affected:
                max_charge[hour] = 0.0

        elif directive.directive_type == DirectiveType.NO_DISCHARGE_WINDOW:
            for hour in affected:
                max_discharge[hour] = 0.0

        elif directive.directive_type == DirectiveType.MAX_GRID_WINDOW:
            if adj.max_grid_kwh is None:
                raise ValueError("max_grid_window requires max_grid_kwh")
            cap = float(adj.max_grid_kwh)
            for hour in affected:
                existing = max_grid[hour]
                max_grid[hour] = cap if existing is None else min(existing, cap)

        else:
            raise ValueError(f"unsupported directive_type: {directive.directive_type}")

    return HourlyConstraints(
        effective_solar=effective_solar,
        min_energy_after=min_energy_after,
        max_charge=max_charge,
        max_discharge=max_discharge,
        max_grid=max_grid,
    )
