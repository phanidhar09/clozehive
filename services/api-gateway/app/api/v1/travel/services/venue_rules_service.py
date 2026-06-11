"""Venue & event dress rules — live lookups for declared trip contexts (Phase 4).

When a trip's activities name something with an *enforced* dress code — a
conference, a gala, an embassy appointment, a business-class flight, a fine
dining reservation — the current published rule is fetched live via the shared
Tavily wrapper and injected into the packing prompt as a MANDATORY constraint.
How mandatory rules rank against weather, festivals, and personal style is
arbitrated centrally by ``app.core.constraint_priority`` — this block does not
carry its own ranking text.

Cost control:
- Only specific, rule-worthy activities trigger a lookup. Generic preset
  activities ("Business Meeting", "Wedding / Formal", "Beach / Pool"…) carry
  no venue to research — searching "dress code for Business Meeting" returns
  noise — so they are skipped; their formality field already guides the AI.
- At most ``MAX_LOOKUPS_PER_TRIP`` searches per packing generation.
- Results cached ~10 days per (context, destination) — venue policies shift
  more often than cultural norms (30d) but not daily.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core import web_intelligence
from app.core.llm_safety import sanitize_user_text
from app.core.logging import get_logger

logger = get_logger("venue_rules")

VENUE_RULES_TTL_S = 10 * 24 * 3600
MAX_LOOKUPS_PER_TRIP = 2

# Activity names that match one of these fragments name a context with an
# enforced/published dress code worth researching.
_RULE_WORTHY_KEYWORDS = (
    "conference",
    "congress",
    "summit",
    "expo",
    "convention",
    "symposium",
    "gala",
    "opera",
    "ballet",
    "theatre",
    "theater",
    "embassy",
    "consulate",
    "visa",
    "interview",
    "michelin",
    "fine dining",
    "tasting menu",
    "business class",
    "first class",
    "lounge",
    "casino",
    "yacht",
    "country club",
    "golf club",
    "members club",
    "graduation",
    "ceremony",
    "award",
)

# Generic preset activity names (frontend ACTIVITY_PRESETS) — no venue to
# research, the activity's formality field already covers them.
_GENERIC_PRESET_NAMES = {
    "beach / pool",
    "brunch / café",
    "dinner / date night",
    "nightlife / club",
    "sightseeing / walking",
    "business meeting",
    "wedding / formal",
    "hiking / outdoor",
    "gym / fitness",
    "shopping",
    "boat / cruise",
    "photoshoot",
    "cultural / museum",
    "theme park",
    "airport travel",
    "spa / pool day",
}


def select_rule_worthy_contexts(activities: list[dict[str, Any]] | None) -> list[str]:
    """Activity names that warrant a live dress-rule lookup (deduped, capped)."""
    contexts: list[str] = []
    seen: set[str] = set()
    for act in activities or []:
        name = sanitize_user_text(str(act.get("name") or ""), field="activity").strip()
        lowered = name.lower()
        if not name or lowered in _GENERIC_PRESET_NAMES or lowered in seen:
            continue
        if any(kw in lowered for kw in _RULE_WORTHY_KEYWORDS):
            seen.add(lowered)
            contexts.append(name)
            if len(contexts) >= MAX_LOOKUPS_PER_TRIP:
                break
    return contexts


async def get_venue_rules(
    activities: list[dict[str, Any]] | None,
    destination: str,
    trip_start: date,
) -> list[dict[str, Any]]:
    """Live dress rules for the trip's rule-worthy contexts.

    Returns ``[{"context", "answer", "sources"}]`` — empty when nothing is
    rule-worthy or the web layer is unavailable.
    """
    contexts = select_rule_worthy_contexts(activities)
    if not contexts:
        return []

    rules: list[dict[str, Any]] = []
    for context in contexts:
        query = (
            f"What is the current dress code for {context}"
            f"{' in ' + destination.strip() if destination and destination.strip() else ''} "
            f"as of {trip_start.year}? Specific clothing requirements and restrictions "
            "(what is required, what is not allowed)."
        )
        result = await web_intelligence.cached_search(
            query,
            namespace="venue-rules",
            key=f"{context}:{destination}",
            ttl_seconds=VENUE_RULES_TTL_S,
        )
        if result:
            rules.append(
                {
                    "context": context,
                    "answer": result["answer"],
                    "sources": result.get("sources") or [],
                }
            )
            logger.info("venue_rule_fetched", context=context[:60])
    return rules


def build_venue_rules_block(rules: list[dict[str, Any]]) -> str:
    """Prompt-ready MANDATORY-constraint block. "" when there are no rules."""
    if not rules:
        return ""
    lines = ["[VENUE & EVENT DRESS RULES — LIVE WEB RESEARCH]"]
    for r in rules:
        lines.append(f"• {r['context']}: {r['answer']}")
        sources_line = web_intelligence.format_sources_line(r)
        if sources_line:
            lines.append(f"  {sources_line}")
    lines += [
        "Treat any clear requirement above as MANDATORY for the day(s) of that "
        "activity (see the constraint priority section for how it ranks against "
        "other context). Flag any packed item that would violate a rule and "
        "substitute a compliant piece from the closet, or list the gap if the "
        "closet has none. If the research does not state a clear dress rule for "
        "a context, ignore it.",
        "[END VENUE & EVENT DRESS RULES]",
    ]
    return "\n".join(lines)
