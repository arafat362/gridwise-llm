"""LLM interpretation with validation retries."""

from __future__ import annotations

from app.config import get_settings
from app.schemas import DirectiveInterpretation, DirectiveType, OptimizeEnergyRequest
from app.services.guardrails import validate_and_normalize_interpretations
from app.services.llm import OpenRouterInterpreter
from app.services.time_windows import extract_hours_from_note, note_looks_energy_related


class InterpretationError(RuntimeError):
    pass


def interpret_operator_notes(request: OptimizeEnergyRequest) -> list[DirectiveInterpretation]:
    settings = get_settings()
    interpreter = OpenRouterInterpreter(settings)
    repair_hint: str | None = None
    last_error: Exception | None = None

    attempts = 1 + max(0, settings.llm_max_retries)
    for _ in range(attempts):
        try:
            raw_items = interpreter.interpret_notes(
                request.operator_notes,
                battery_capacity_kwh=request.battery.capacity_kwh,
                repair_hint=repair_hint,
            )
            raw_items = _apply_hour_overrides(raw_items, request.operator_notes)
            interpretations = validate_and_normalize_interpretations(
                raw_items,
                note_count=len(request.operator_notes),
                battery_capacity_kwh=request.battery.capacity_kwh,
            )
            false_noop = _false_noop_indexes(interpretations, request.operator_notes)
            if false_noop:
                raise ValueError(
                    "energy-related notes were marked no_op at indexes "
                    f"{false_noop}; map them to a supported energy directive"
                )
            return interpretations
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            repair_hint = (
                f"Previous output failed validation: {exc}. "
                "Return corrected JSON only. Reminder: windows are start-inclusive and "
                "end-exclusive (6 PM until 9 PM -> [18,19,20]; 6 PM until 10 PM -> "
                "[18,19,20,21]; between 11 AM and 2 PM -> [11,12,13]). "
                "Isolating/disabling a battery charger is no_charge_window, not no_op."
            )

    raise InterpretationError(f"failed to interpret operator notes: {last_error}")


def _apply_hour_overrides(raw_items: list[dict], operator_notes: list[str]) -> list[dict]:
    # Prefer clock windows parsed from the note when unambiguous.
    patched: list[dict] = []
    for item, note in zip(raw_items, operator_notes, strict=False):
        item = dict(item)
        if str(item.get("directive_type", "")) == DirectiveType.NO_OP.value:
            patched.append(item)
            continue
        hours = extract_hours_from_note(note)
        adjustment = item.get("structured_adjustment")
        if hours is not None and isinstance(adjustment, dict):
            adjustment = dict(adjustment)
            adjustment["hours"] = hours
            item["structured_adjustment"] = adjustment
        patched.append(item)
    return patched


def _false_noop_indexes(
    interpretations: list[DirectiveInterpretation],
    operator_notes: list[str],
) -> list[int]:
    bad: list[int] = []
    for item, note in zip(interpretations, operator_notes, strict=True):
        if item.directive_type == DirectiveType.NO_OP and note_looks_energy_related(note):
            bad.append(item.note_index)
    return bad
