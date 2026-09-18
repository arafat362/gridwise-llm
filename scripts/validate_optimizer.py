"""Optimizer check using ground-truth directives (no LLM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas import DirectiveInterpretation, OptimizeEnergyRequest
from app.services.pipeline import build_response
from app.services.validate import replay_plan

from scripts.paths import sample_cases_path

SAMPLES = sample_cases_path()
TOL = 0.01


def main() -> int:
    if not SAMPLES.exists():
        print(f"Sample pack not found: {SAMPLES}", file=sys.stderr)
        return 1

    pack = json.loads(SAMPLES.read_text(encoding="utf-8"))
    failed = 0

    for case in pack["cases"]:
        request = OptimizeEnergyRequest.model_validate(case["input"])
        interpretations = [
            DirectiveInterpretation.model_validate(item)
            for item in case["expected_output"]["directive_interpretation"]
        ]
        response = build_response(request, interpretations)
        issues = replay_plan(
            request.hours,
            request.battery,
            interpretations,
            response.hourly_plan,
            total_grid_kwh=response.total_grid_kwh,
            total_cost_bdt=response.total_cost_bdt,
            peak_grid_kwh=response.peak_grid_kwh,
        )

        expected_cost = float(case["expected_output"]["total_cost_bdt"])
        cost_delta = response.total_cost_bdt - expected_cost
        cost_ok = abs(cost_delta) <= TOL or response.total_cost_bdt <= expected_cost + TOL

        status = "PASS"
        if issues or not cost_ok:
            status = "FAIL"
            failed += 1

        print(
            f"{status} {case['id']}: cost={response.total_cost_bdt:.4f} "
            f"(ref={expected_cost:.4f}, delta={cost_delta:+.4f}) "
            f"grid={response.total_grid_kwh:.4f} peak={response.peak_grid_kwh:.4f}"
        )
        for issue in issues:
            where = f"h{issue.hour}" if issue.hour is not None else "plan"
            print(f"  - [{where}] {issue.message}")
        if not issues and not cost_ok:
            print("  - cost not within tolerance of reference optimum")

    print()
    if failed:
        print(f"{failed}/{len(pack['cases'])} cases failed")
        return 1

    print(f"All {len(pack['cases'])} public samples passed optimizer checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
