"""Prompt-block formatters for the packing AI calls (pure, no LLM)."""

from __future__ import annotations

import json
from typing import Any

from app.core.llm_safety import sanitize_user_text

def _format_closet_for_prompt(closet_items: list[dict[str, Any]]) -> str:
    formatted = []
    for item in closet_items:
        entry: dict[str, Any] = {
            "id": item.get("id"),
            "name": item.get("name"),
            "category": item.get("category"),
        }
        for field in ("color", "brand", "fabric", "pattern", "season", "size", "notes"):
            val = item.get(field)
            if val:
                entry[field] = val
        occasions = item.get("occasion") or item.get("occasions")
        if occasions:
            entry["occasions"] = occasions
        formatted.append(entry)
    return json.dumps(formatted, ensure_ascii=False)


def _format_activities_for_prompt(activities: list[dict[str, Any]]) -> str:
    if not activities:
        return "No specific activities listed — use trip purpose and notes to guide outfit choices."
    lines = []
    for i, act in enumerate(activities, 1):
        # Sanitise every user-supplied field before embedding in the prompt.
        safe_name = sanitize_user_text(act.get("name", "Activity"), field="activity")
        line = f"  {i}. {safe_name}"
        if act.get("day_number"):
            line += f" — Day {act['day_number']}"
        if act.get("date"):
            line += f" ({act['date']})"
        if act.get("time_of_day"):
            line += f", {act['time_of_day'].replace('_', ' ')}"
        if act.get("formality"):
            line += f", dress code: {act['formality'].replace('_', ' ')}"
        if act.get("is_fixed"):
            line += " ⚠️ [BOOKED — must plan outfit]"
        if act.get("notes"):
            safe_notes = sanitize_user_text(act["notes"], field="activity", max_len=200)
            line += f" | Notes: {safe_notes}"
        lines.append(line)
    return "\n".join(lines)


def _per_day_weather_table(weather_days: list[dict[str, Any]]) -> str:
    if not weather_days:
        return ""
    lines = ["Per-day weather forecast:"]
    for i, wd in enumerate(weather_days[:14], 1):
        lines.append(
            f"  Day {i} ({wd.get('date', '?')}): {wd.get('condition', '?')} | "
            f"High {wd.get('temp_high', '?')}°C / Low {wd.get('temp_low', '?')}°C"
        )
    return "\n".join(lines)

