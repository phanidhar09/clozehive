"""Festival discovery — static-first, Tavily-fallback (Phase 3 of the roadmap).

Combines the Phase 0 curated calendar with live web search for the long tail:
the static table answers instantly (and free) for major festivals it knows;
when it has nothing for a trip window, one cached Tavily search discovers
regional/local festivals and events at the destination.

Resolution order (mirrors Phase 2's dress guidelines):

  static calendar hit  >  live web discovery (Tavily, 24h cache)  >  nothing

The discovery query asks for traditional dress in the same call, so live
results need no second "what to wear" lookup. Results are keyed by
``destination + date-range`` and shared across every user heading there.

Callers treat the result as best-effort context: ``source`` is None when
neither tier found anything, and prompt blocks instruct the model to ignore
live text that doesn't clearly describe a festival during the trip.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core import web_intelligence
from app.core.logging import get_logger
from app.api.v1.intelligence.services import festival_calendar

logger = get_logger("festival_discovery")

# Live festival lookups are date-window-specific; a day is plenty of freshness.
FESTIVAL_DISCOVERY_TTL_S = 24 * 3600


async def get_trip_festivals(
    destination: str, start_date: date, end_date: date
) -> dict[str, Any]:
    """Festivals at ``destination`` during [start_date, end_date].

    Returns::

        {
          "source": "static" | "live" | None,
          "festivals": [{"name", "emoji", "date", "occasion", "dress"}],  # static tier
          "live": {"answer", "sources", "fetched_at"} | None,             # live tier
        }
    """
    result: dict[str, Any] = {"source": None, "festivals": [], "live": None}
    if not destination or not destination.strip():
        return result

    # Tier 1 — static curated calendar (free, deterministic).
    country = festival_calendar.infer_country(destination)
    static_hits = festival_calendar.festivals_in_range(country, start_date, end_date)
    if static_hits:
        result["source"] = "static"
        result["festivals"] = [
            {
                "name": fest["name"],
                "emoji": fest["emoji"],
                "date": occ_date.isoformat(),
                "occasion": fest["occasion"],
                "dress": fest["dress"],
            }
            for occ_date, fest in static_hits
        ]
        return result

    # Tier 2 — live discovery via the shared Tavily wrapper.
    query = (
        f"What festivals, public celebrations, or major cultural events take place in "
        f"{destination.strip()} between {start_date.isoformat()} and {end_date.isoformat()}? "
        "For each, give the name, the exact date, and what people traditionally wear to it."
    )
    live = await web_intelligence.cached_search(
        query,
        namespace="festivals",
        key=f"{destination}:{start_date.isoformat()}:{end_date.isoformat()}",
        ttl_seconds=FESTIVAL_DISCOVERY_TTL_S,
    )
    if live:
        result["source"] = "live"
        result["live"] = live
        logger.info("festival_live_discovery", destination=destination[:60])
    return result


def build_trip_festival_block(result: dict[str, Any]) -> str:
    """Prompt-ready festival block for packing/outfit prompts. "" when empty."""
    if result.get("source") == "static":
        lines = ["[FESTIVALS DURING THE TRIP]"]
        for f in result["festivals"]:
            lines.append(f"• {f['name']} {f['emoji']} on {f['date']} — dress: {f['dress']}")
        lines += [
            "Pack/style for these explicitly: include festival-appropriate items from "
            "the user's closet for those dates, and flag what's missing if the closet "
            "can't cover the festival look.",
            "[END FESTIVALS]",
        ]
        return "\n".join(lines)

    if result.get("source") == "live":
        live = result["live"]
        sources_line = web_intelligence.format_sources_line(live)
        lines = [
            "[FESTIVALS DURING THE TRIP — LIVE WEB RESEARCH]",
            live["answer"],
        ]
        if sources_line:
            lines.append(sources_line)
        lines += [
            "If the research above clearly names a festival or event during the trip "
            "dates, pack/style for it from the user's closet and flag missing pieces. "
            "If it does not clearly describe one, ignore this section entirely.",
            "[END FESTIVALS]",
        ]
        return "\n".join(lines)

    return ""


def nudge_festival_context(result: dict[str, Any]) -> str:
    """One short context sentence for the trip-prep nudge LLM. "" when empty."""
    if result.get("source") == "static":
        f = result["festivals"][0]
        return (
            f"{f['name']} {f['emoji']} falls during the trip on {f['date']}. "
            f"Dress guidance: {f['dress']} "
            "Suggest opening the packing plan now so they pack something festive."
        )
    if result.get("source") == "live":
        answer = result["live"]["answer"][:300]
        return (
            f"Web research about events at the destination during the trip: {answer} "
            "Only if that clearly names a festival or event during the trip, work it into "
            "the nudge; otherwise write a normal packing-prep nudge without mentioning events."
        )
    return ""
