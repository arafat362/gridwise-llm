"""Find the public sample JSON (repo data/ first)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [
    ROOT / "data" / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json",
    ROOT.parent / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json",
]


def sample_cases_path() -> Path:
    for path in CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Missing sample pack at data/BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
    )
