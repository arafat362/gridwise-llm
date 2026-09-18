"""Validate LLM JSON before it reaches the optimizer."""

from __future__ import annotations

from typing import Any

from app.schemas import (
    DirectiveInterpretation,
    DirectiveType,
    StructuredAdjustment,
)

ALLOWED_TYPES = {item.value for item in DirectiveType}


class GuardrailError(ValueError):
    pass


def validate_and_normalize_interpretations(
    raw_items: list[dict[str, Any]],
    *,
    note_count: int,
    battery_capacity_kwh: float,
) -> list[DirectiveInterpretation]:
    if len(raw_items) != note_count:
        raise GuardrailError(
            f"expected {note_count} directive_interpretation entries, got {len(raw_items)}"
        )

    normalized: list[DirectiveInterpretation] = []
    seen_indexes: set[int] = set()

    for expected_index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise GuardrailError(f"entry {expected_index} is not an object")

        note_index = int(item.get("note_index", expected_index))
        if note_index != expected_index:
            raise GuardrailError(
                f"note_index out of order: expected {expected_index}, got {note_index}"
            )
        if note_index in seen_indexes:
            raise GuardrailError(f"duplicate note_index {note_index}")
        if note_index < 0 or note_index >= note_count:
            raise GuardrailError(f"note_index {note_index} out of range")
        seen_indexes.add(note_index)

        directive_type = str(item.get("directive_type", "")).strip()
        if directive_type not in ALLOWED_TYPES:
            raise GuardrailError(f"unsupported directive_type: {directive_type}")

        applies = bool(item.get("applies"))
        explanation = str(item.get("explanation") or "").strip() or "Interpreted by LLM."
        raw_adjustment = item.get("structured_adjustment")

        if directive_type == DirectiveType.NO_OP.value:
            if applies:
                raise GuardrailError("no_op requires applies=false")
            if raw_adjustment is not None:
                raise GuardrailError("no_op requires structured_adjustment=null")
            normalized.append(
                DirectiveInterpretation(
                    note_index=note_index,
                    applies=False,
                    directive_type=DirectiveType.NO_OP,
                    structured_adjustment=None,
                    explanation=explanation,
                )
            )
            continue

        if not applies:
            raise GuardrailError(f"{directive_type} requires applies=true")
        if not isinstance(raw_adjustment, dict):
            raise GuardrailError(f"{directive_type} requires structured_adjustment object")

        adjustment = _normalize_adjustment(
            directive_type,
            raw_adjustment,
            battery_capacity_kwh=battery_capacity_kwh,
        )
        normalized.append(
            DirectiveInterpretation(
                note_index=note_index,
                applies=True,
                directive_type=DirectiveType(directive_type),
                structured_adjustment=adjustment,
                explanation=explanation,
            )
        )

    return normalized


def _normalize_hours(raw_hours: Any) -> list[int]:
    if not isinstance(raw_hours, list) or not raw_hours:
        raise GuardrailError("hours must be a non-empty list")
    hours = sorted({int(h) for h in raw_hours})
    if any(h < 0 or h > 23 for h in hours):
        raise GuardrailError("hours must be integers from 0 through 23")
    return hours


def _normalize_adjustment(
    directive_type: str,
    raw: dict[str, Any],
    *,
    battery_capacity_kwh: float,
) -> StructuredAdjustment:
    hours = _normalize_hours(raw.get("hours"))

    if directive_type == DirectiveType.SOLAR_REDUCTION.value:
        if "factor" not in raw:
            raise GuardrailError("solar_reduction requires factor")
        factor = float(raw["factor"])
        if not (0.0 <= factor <= 1.0):
            raise GuardrailError("solar_reduction factor must be in [0, 1]")
        return StructuredAdjustment(hours=hours, factor=factor)

    if directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE.value:
        if "minimum_energy_kwh" in raw and raw["minimum_energy_kwh"] is not None:
            reserve = float(raw["minimum_energy_kwh"])
        elif "fraction_of_capacity" in raw and raw["fraction_of_capacity"] is not None:
            reserve = float(raw["fraction_of_capacity"]) * battery_capacity_kwh
        else:
            raise GuardrailError("minimum_battery_reserve requires minimum_energy_kwh")
        if reserve < 0 or reserve > battery_capacity_kwh + 1e-9:
            raise GuardrailError("minimum_energy_kwh out of battery capacity range")
        return StructuredAdjustment(hours=hours, minimum_energy_kwh=round(reserve, 6))

    if directive_type == DirectiveType.NO_CHARGE_WINDOW.value:
        return StructuredAdjustment(hours=hours)

    if directive_type == DirectiveType.NO_DISCHARGE_WINDOW.value:
        return StructuredAdjustment(hours=hours)

    if directive_type == DirectiveType.MAX_GRID_WINDOW.value:
        if "max_grid_kwh" not in raw or raw["max_grid_kwh"] is None:
            raise GuardrailError("max_grid_window requires max_grid_kwh")
        cap = float(raw["max_grid_kwh"])
        if cap < 0:
            raise GuardrailError("max_grid_kwh must be non-negative")
        return StructuredAdjustment(hours=hours, max_grid_kwh=cap)

    raise GuardrailError(f"unsupported directive_type: {directive_type}")
