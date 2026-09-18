"""Check a returned plan hour-by-hour against the rules."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas import (
    BatteryAction,
    BatteryConfig,
    DirectiveInterpretation,
    HourInput,
    HourlyPlanEntry,
)
from app.services.directives import build_hourly_constraints

TOL = 0.01


@dataclass
class ValidationIssue:
    hour: int | None
    message: str


def replay_plan(
    hours: list[HourInput],
    battery: BatteryConfig,
    directives: list[DirectiveInterpretation],
    plan: list[HourlyPlanEntry],
    *,
    total_grid_kwh: float,
    total_cost_bdt: float,
    peak_grid_kwh: float,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    hours_sorted = sorted(hours, key=lambda h: h.hour)
    plan_sorted = sorted(plan, key=lambda h: h.hour)

    if [h.hour for h in plan_sorted] != list(range(24)):
        issues.append(ValidationIssue(None, "hourly_plan must cover hours 0..23 exactly once"))
        return issues

    constraints = build_hourly_constraints(
        hours_sorted,
        capacity_kwh=battery.capacity_kwh,
        minimum_energy_kwh=battery.minimum_energy_kwh,
        max_charge_kwh_per_hour=battery.max_charge_kwh_per_hour,
        max_discharge_kwh_per_hour=battery.max_discharge_kwh_per_hour,
        directives=directives,
    )

    energy = float(battery.initial_energy_kwh)
    calc_grid = 0.0
    calc_cost = 0.0
    calc_peak = 0.0

    for hour_input, entry in zip(hours_sorted, plan_sorted, strict=True):
        h = hour_input.hour
        charge = entry.battery_kwh if entry.battery_action == BatteryAction.CHARGE else 0.0
        discharge = entry.battery_kwh if entry.battery_action == BatteryAction.DISCHARGE else 0.0

        if entry.battery_action == BatteryAction.IDLE and entry.battery_kwh > TOL:
            issues.append(ValidationIssue(h, "idle requires battery_kwh == 0"))
        if charge - constraints.max_charge[h] > TOL:
            issues.append(ValidationIssue(h, "charge exceeds max_charge / no_charge_window"))
        if discharge - constraints.max_discharge[h] > TOL:
            issues.append(ValidationIssue(h, "discharge exceeds max_discharge / no_discharge_window"))
        if entry.solar_used_kwh - constraints.effective_solar[h] > TOL:
            issues.append(ValidationIssue(h, "solar_used exceeds effective solar"))
        if constraints.max_grid[h] is not None and entry.grid_kwh - constraints.max_grid[h] > TOL:
            issues.append(ValidationIssue(h, "grid_kwh exceeds max_grid_window"))

        balance_lhs = entry.grid_kwh + entry.solar_used_kwh + discharge
        balance_rhs = hour_input.demand_kwh + charge
        if abs(balance_lhs - balance_rhs) > TOL:
            issues.append(
                ValidationIssue(h, f"energy balance failed: {balance_lhs:.4f} != {balance_rhs:.4f}")
            )

        energy_after = energy + charge - discharge
        if abs(energy_after - entry.battery_energy_after_kwh) > TOL:
            issues.append(
                ValidationIssue(
                    h,
                    f"battery transition mismatch: expected {energy_after:.4f}, got {entry.battery_energy_after_kwh:.4f}",
                )
            )
        if entry.battery_energy_after_kwh + TOL < constraints.min_energy_after[h]:
            issues.append(ValidationIssue(h, "battery below minimum reserve"))
        if entry.battery_energy_after_kwh - battery.capacity_kwh > TOL:
            issues.append(ValidationIssue(h, "battery above capacity"))

        energy = entry.battery_energy_after_kwh
        calc_grid += entry.grid_kwh
        calc_cost += entry.grid_kwh * hour_input.tariff_bdt_per_kwh
        calc_peak = max(calc_peak, entry.grid_kwh)

    if abs(energy - battery.initial_energy_kwh) > TOL:
        issues.append(
            ValidationIssue(
                23,
                f"end-of-day neutrality failed: {energy:.4f} != {battery.initial_energy_kwh:.4f}",
            )
        )
    if abs(calc_grid - total_grid_kwh) > TOL:
        issues.append(ValidationIssue(None, "total_grid_kwh does not match hourly_plan"))
    if abs(calc_cost - total_cost_bdt) > TOL:
        issues.append(ValidationIssue(None, "total_cost_bdt does not match hourly_plan"))
    if abs(calc_peak - peak_grid_kwh) > TOL:
        issues.append(ValidationIssue(None, "peak_grid_kwh does not match hourly_plan"))

    return issues
