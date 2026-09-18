"""24-hour cost minimizer (PuLP + CBC)."""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from app.schemas import (
    BatteryAction,
    BatteryConfig,
    DirectiveInterpretation,
    HourInput,
    HourlyPlanEntry,
)
from app.services.directives import HourlyConstraints, build_hourly_constraints

EPS = 1e-6


@dataclass(frozen=True)
class OptimizeResult:
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float


class OptimizationError(RuntimeError):
    pass


def optimize_schedule(
    hours: list[HourInput],
    battery: BatteryConfig,
    directives: list[DirectiveInterpretation],
) -> OptimizeResult:
    constraints = build_hourly_constraints(
        hours,
        capacity_kwh=battery.capacity_kwh,
        minimum_energy_kwh=battery.minimum_energy_kwh,
        max_charge_kwh_per_hour=battery.max_charge_kwh_per_hour,
        max_discharge_kwh_per_hour=battery.max_discharge_kwh_per_hour,
        directives=directives,
    )
    return _solve_lp(hours, battery, constraints)


def _solve_lp(
    hours: list[HourInput],
    battery: BatteryConfig,
    constraints: HourlyConstraints,
) -> OptimizeResult:
    hours_sorted = sorted(hours, key=lambda h: h.hour)
    demand = [float(h.demand_kwh) for h in hours_sorted]
    tariff = [float(h.tariff_bdt_per_kwh) for h in hours_sorted]
    initial = float(battery.initial_energy_kwh)
    capacity = float(battery.capacity_kwh)

    problem = pulp.LpProblem("gridwise_optimize", pulp.LpMinimize)

    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0) for h in range(24)]
    solar_used = [
        pulp.LpVariable(f"solar_{h}", lowBound=0, upBound=constraints.effective_solar[h])
        for h in range(24)
    ]
    charge = [
        pulp.LpVariable(f"charge_{h}", lowBound=0, upBound=constraints.max_charge[h])
        for h in range(24)
    ]
    discharge = [
        pulp.LpVariable(f"discharge_{h}", lowBound=0, upBound=constraints.max_discharge[h])
        for h in range(24)
    ]
    energy_after = [
        pulp.LpVariable(
            f"energy_{h}",
            lowBound=constraints.min_energy_after[h],
            upBound=capacity,
        )
        for h in range(24)
    ]

    for h in range(24):
        problem += (
            grid[h] + solar_used[h] + discharge[h] == demand[h] + charge[h],
            f"balance_{h}",
        )
        prev = initial if h == 0 else energy_after[h - 1]
        problem += energy_after[h] == prev + charge[h] - discharge[h], f"battery_{h}"
        if constraints.max_grid[h] is not None:
            problem += grid[h] <= constraints.max_grid[h], f"max_grid_{h}"

    problem += energy_after[23] == initial, "end_of_day_neutrality"
    problem += pulp.lpSum(grid[h] * tariff[h] for h in range(24))

    status = problem.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=20))
    if status != pulp.LpStatusOptimal:
        raise OptimizationError(f"optimizer failed with status={pulp.LpStatus[status]}")

    plan: list[HourlyPlanEntry] = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for h in range(24):
        g = _clean(pulp.value(grid[h]))
        s = _clean(pulp.value(solar_used[h]))
        c = _clean(pulp.value(charge[h]))
        d = _clean(pulp.value(discharge[h]))
        e = _clean(pulp.value(energy_after[h]))

        net = c - d
        if net > EPS:
            action = BatteryAction.CHARGE
            battery_kwh = net
        elif net < -EPS:
            action = BatteryAction.DISCHARGE
            battery_kwh = -net
        else:
            action = BatteryAction.IDLE
            battery_kwh = 0.0

        total_grid += g
        total_cost += g * tariff[h]
        peak_grid = max(peak_grid, g)

        plan.append(
            HourlyPlanEntry(
                hour=h,
                grid_kwh=round(g, 6),
                solar_used_kwh=round(s, 6),
                battery_action=action,
                battery_kwh=round(battery_kwh, 6),
                battery_energy_after_kwh=round(e, 6),
            )
        )

    if abs(plan[-1].battery_energy_after_kwh - initial) <= 0.01:
        plan[-1] = plan[-1].model_copy(update={"battery_energy_after_kwh": round(initial, 6)})

    return OptimizeResult(
        hourly_plan=plan,
        total_grid_kwh=round(total_grid, 6),
        total_cost_bdt=round(total_cost, 6),
        peak_grid_kwh=round(peak_grid, 6),
    )


def _clean(value: float | None) -> float:
    number = float(value or 0.0)
    return 0.0 if abs(number) < EPS else number
