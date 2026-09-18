"""Pull whole-hour windows out of operator notes."""

from __future__ import annotations

import re

_TIME_TOKEN = r"(?:\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)|noon|midnight)"

_CLOCK = re.compile(
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)",
    re.IGNORECASE,
)

_WINDOW_PATTERNS = [
    re.compile(
        rf"(?:from|between)\s+(?P<start>{_TIME_TOKEN})\s+(?:until|to|and|-|–|—)\s+(?P<end>{_TIME_TOKEN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<start>{_TIME_TOKEN})\s*(?:until|to|-|–|—)\s*(?P<end>{_TIME_TOKEN})",
        re.IGNORECASE,
    ),
]


def parse_clock_token(token: str) -> int | None:
    token = token.strip().strip(".,;:)")
    lowered = token.lower()
    if lowered == "noon":
        return 12
    if lowered == "midnight":
        return 0
    match = _CLOCK.search(token)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    ampm = match.group("ampm").lower().replace(".", "")
    if minute != 0 or hour < 1 or hour > 12:
        return None
    if ampm.startswith("p") and hour != 12:
        hour += 12
    if ampm.startswith("a") and hour == 12:
        hour = 0
    return hour


def extract_hours_from_note(note: str) -> list[int] | None:
    """Start inclusive, end exclusive. e.g. 1 PM to 3 PM -> [13, 14]."""
    for pattern in _WINDOW_PATTERNS:
        match = pattern.search(note)
        if not match:
            continue
        start = parse_clock_token(match.group("start"))
        end = parse_clock_token(match.group("end"))
        if start is None or end is None or start == end:
            continue
        if start < end:
            hours = list(range(start, end))
        else:
            hours = list(range(start, 24)) + list(range(0, end))
        if hours and all(0 <= h <= 23 for h in hours):
            return hours
    return None


_ENERGY_HINT = re.compile(
    r"\b(solar|battery|charger|charging|discharge|grid|feeder|transformer|"
    r"inverter|reserve|panel|pv|import|intake|kwh)\b",
    re.IGNORECASE,
)


def note_looks_energy_related(note: str) -> bool:
    return bool(_ENERGY_HINT.search(note))
