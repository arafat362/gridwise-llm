"""Wire note interpretation into the optimizer and build the API response."""

from __future__ import annotations

from app.schemas import (
    DirectiveInterpretation,
    DirectiveType,
    OptimizeEnergyRequest,
    OptimizeEnergyResponse,
)
from app.services.interpret import interpret_operator_notes
from app.services.optimizer import optimize_schedule


def build_response(
    request: OptimizeEnergyRequest,
    interpretations: list[DirectiveInterpretation],
) -> OptimizeEnergyResponse:
    result = optimize_schedule(request.hours, request.battery, interpretations)
    active = [
        d.directive_type.value
        for d in interpretations
        if d.applies and d.directive_type != DirectiveType.NO_OP
    ]
    summary = (
        "Minimized grid cost under battery limits"
        + (f" with directives: {', '.join(active)}." if active else ".")
    )
    return OptimizeEnergyResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=interpretations,
        hourly_plan=result.hourly_plan,
        total_grid_kwh=result.total_grid_kwh,
        total_cost_bdt=result.total_cost_bdt,
        peak_grid_kwh=result.peak_grid_kwh,
        plan_summary=summary,
    )


def build_optimize_response(request: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
    interpretations = interpret_operator_notes(request)
    return build_response(request, interpretations)
