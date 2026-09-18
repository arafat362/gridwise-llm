"""Call OpenRouter and get structured directive JSON back."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.config import Settings, get_settings

SYSTEM_PROMPT = """You interpret campus operator notes for a 24-hour energy schedule.

Return ONLY valid JSON with this exact top-level shape:
{
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
      "explanation": "short reason"
    }
  ]
}

Rules:
1. Emit exactly one entry per operator note, in note_index order 0..N-1.
2. Allowed directive_type values only:
   - solar_reduction
   - minimum_battery_reserve
   - no_charge_window
   - no_discharge_window
   - max_grid_window
   - no_op
3. Irrelevant / non-energy notes (sports office, cafeteria, library, seminars, deadlines, bookings)
   must use: applies=false, directive_type="no_op", structured_adjustment=null
4. Every non-no_op directive must use applies=true and a structured_adjustment object.

TIME WINDOW ALGORITHM (critical):
- Convert clock times to 24h integers (noon=12, 1 PM=13, 6 PM=18, 10 PM=22, 2 AM=2).
- Windows are start-inclusive and end-exclusive: hours = [start, start+1, ..., end-1].
- Phrases "from A until B", "from A to B", "between A and B", "A-B" all use the same rule.
- The named end time is NOT included as an active hour.
Examples:
  "1 PM to 3 PM" -> [13,14]
  "noon until 2 PM" -> [12,13]
  "2 AM until 5 AM" -> [2,3,4]
  "6 PM until 8 PM" -> [18,19]
  "6 PM until 9 PM" -> [18,19,20]
  "6 PM until 10 PM" -> [18,19,20,21]
  "7 PM until 9 PM" -> [19,20]
  "7 PM until 10 PM" -> [19,20,21]
  "11 AM until 1 PM" / "11 AM to 1 PM" -> [11,12]
  "between 11 AM and 2 PM" / "11 AM and 2 PM" -> [11,12,13]
  "from 10 AM until noon" -> [10,11]

DIRECTIVE MAPPING:
- Panel washing / cloud cover / inverter work reducing usable solar -> solar_reduction
- Keep at least X kWh or X% of capacity in battery during a window -> minimum_battery_reserve
- Charger isolated / charging circuit unavailable / do not charge / charging disabled -> no_charge_window
- Must not discharge / discharge disabled / no discharge during test -> no_discharge_window
- Grid import / intake / feeder / transformer limit / cap -> max_grid_window

NUMERIC RULES:
- Hours must be unique integers 0..23 in ascending order.
- solar_reduction.factor is the usable fraction REMAINING.
  "drop to 20%" / "20% of forecast" -> 0.2
  "roughly 25% of the forecast" -> 0.25
  "about half" / "50% of forecast" -> 0.5
  "80% reduction" -> 0.2
- minimum_battery_reserve needs hours + minimum_energy_kwh.
  If note gives % of capacity, convert with provided battery_capacity_kwh.
  Example: "50% of a 200 kWh battery" -> 100
- no_charge_window / no_discharge_window: {"hours":[...]} only
- max_grid_window: {"hours":[...], "max_grid_kwh": number}
- Do not invent demand, tariff, battery limits, or unsupported directive types.
- Do not include markdown fences.
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class OpenRouterInterpreter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        self.client = OpenAI(
            api_key=self.settings.openrouter_api_key,
            base_url=self.settings.openrouter_base_url,
            timeout=self.settings.llm_timeout_seconds,
            default_headers={
                "HTTP-Referer": self.settings.openrouter_site_url,
                "X-Title": self.settings.openrouter_app_name,
            },
        )

    def interpret_notes(
        self,
        operator_notes: list[str],
        *,
        battery_capacity_kwh: float,
        repair_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        user_payload = {
            "battery_capacity_kwh": battery_capacity_kwh,
            "operator_notes": [
                {"note_index": index, "text": note}
                for index, note in enumerate(operator_notes)
            ],
        }
        if repair_hint:
            user_payload["repair_hint"] = repair_hint

        completion = self.client.chat.completions.create(
            model=self.settings.openrouter_model,
            temperature=0,
            max_tokens=self.settings.llm_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=True),
                },
            ],
        )
        content = completion.choices[0].message.content or ""
        parsed = _extract_json(content)
        items = parsed.get("directive_interpretation")
        if not isinstance(items, list):
            raise ValueError("LLM response missing directive_interpretation list")
        return items
