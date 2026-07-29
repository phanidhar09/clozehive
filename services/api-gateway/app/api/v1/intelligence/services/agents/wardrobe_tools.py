"""Read-only tools for the wardrobe-analyst agent.

Every tool here is a thin, *summarising* adapter over logic that already exists
elsewhere — the analytics service, the purchase-gap store, embedding search, and
the deterministic outfit builder. Two rules hold for all of them:

**Read-only.** No tool writes, and none may be given a write path later without
revisiting the agent's safety story: the model chooses when to call these, so a
mutating tool would let prompt-injected text in a garment note trigger a write.
This is why the stats tool uses ``get_readonly_snapshot`` rather than
``get_closet_analytics`` (which persists detected gaps as a side effect).

**Pre-summarised.** Handlers return small dicts, not raw rows. The loop truncates
oversized results as a backstop, but truncation mid-JSON gives the model garbage
— better to send 10 ranked items than 200 arbitrary ones.

Handlers are built per request by :func:`build_tools`, which closes over the
session and user id. The model therefore cannot address another user's data:
the user scope is bound in Python, never passed as a tool argument.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intelligence.services import purchase_gap_service
from app.api.v1.intelligence.services.agents.loop import AgentTool
from app.api.v1.platform.services.analytics_service import AnalyticsService
from app.api.v1.wardrobe.services import closet_similarity_service
from app.core import outfit_builder
from app.core.logging import get_logger
from app.models.closet import ClosetItem

logger = get_logger("wardrobe_tools")

# Ceiling on the closet pulled into the outfit-math tool. Matches the styling
# pipeline's cap so the agent's counts agree with what the rest of the app shows.
_COMPAT_CLOSET_LIMIT = 200


async def _fetch_closet(session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """Available items with the attributes compatibility scoring reads.

    Mirrors the styling pipeline's filter: archived and unavailable items
    (in-laundry / at-cleaners / lent-out) are not things the user can wear
    tomorrow, so counting outfits from them would overstate the wardrobe.
    """
    result = await session.execute(
        select(
            ClosetItem.id,
            ClosetItem.name,
            ClosetItem.category,
            ClosetItem.color,
            ClosetItem.fabric,
            ClosetItem.pattern,
            ClosetItem.season,
            ClosetItem.occasion,
            ClosetItem.wear_count,
        )
        .where(
            ClosetItem.user_id == UUID(user_id),
            ClosetItem.is_archived == False,  # noqa: E712 — SQL boolean, not Python
        )
        .limit(_COMPAT_CLOSET_LIMIT)
    )
    return [dict(row) for row in result.mappings().all()]


# ── Handlers ──────────────────────────────────────────────────────────────────


async def _get_wardrobe_stats(session: AsyncSession, user_id: str, _args: dict[str, Any]) -> dict[str, Any]:
    """Coverage + value insights: what the user owns and how hard it works."""
    snapshot = await AnalyticsService(session).get_readonly_snapshot(UUID(user_id))

    stats: dict[str, Any] = {
        "total_items": snapshot.summary.total_items,
        "strongest_category": snapshot.summary.strongest_category,
        "most_common_color": snapshot.summary.most_common_color,
        "estimated_outfits": snapshot.outfit_readiness.estimated_outfits,
        # Only the categories that need attention — "good" ones aren't actionable.
        "thin_categories": [
            {"category": c.category, "count": c.count, "recommended_minimum": c.recommended_minimum}
            for c in snapshot.category_coverage
            if c.status in {"low", "missing"}
        ],
    }

    value = snapshot.value_insights
    if value is None:
        # Empty wardrobe — say so explicitly rather than omitting the keys, so the
        # model reports "no data" instead of inferring zeros it was never given.
        stats["value_insights"] = "unavailable — no active items in this wardrobe"
        return stats

    stats.update(
        {
            "utilization_rate_pct": value.utilization_rate,
            "active_rate_90d_pct": value.active_rate_90d,
            "avg_cost_per_wear": value.avg_cost_per_wear,
            "items_priced": value.items_priced,
            "total_value": value.total_value,
            "value_unworn": value.value_unworn,
            "worst_value_items": [
                {"name": i.name, "category": i.category, "cost_per_wear": i.cost_per_wear, "wear_count": i.wear_count}
                for i in (value.worst_value_items or [])[:5]
            ],
            "forgotten_gems": [
                {"name": g.name, "category": g.category, "days_since_worn": g.days_since_worn}
                for g in (value.forgotten_gems or [])[:8]
            ],
            "most_versatile": [
                {"name": v.name, "category": v.category, "outfit_count": v.outfit_count}
                for v in (value.most_versatile or [])[:5]
            ],
        }
    )
    return stats


async def _get_purchase_gaps(session: AsyncSession, user_id: str, _args: dict[str, Any]) -> dict[str, Any]:
    """Previously detected, still-unresolved wardrobe gaps."""
    gaps = await purchase_gap_service.get_purchase_gaps(session, user_id, resolved=False, limit=15)
    return {
        "count": len(gaps),
        "gaps": [
            {
                "gap_type": g["gap_type"],
                "missing_category": g["missing_category"],
                "missing_color": g["missing_color"],
                "missing_occasion": g["missing_occasion"],
                "reason": g["reason"],
                "priority_score": g["priority_score"],
            }
            for g in gaps
        ],
    }


async def _search_closet(session: AsyncSession, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Semantic search over the user's own items."""
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required", "items": []}

    limit = args.get("limit", 8)
    limit = min(max(int(limit) if isinstance(limit, int | float | str) and str(limit).isdigit() else 8, 1), 15)

    items = await closet_similarity_service.find_similar_by_text(session, query, user_id, limit=limit)
    return {
        "query": query,
        "count": len(items),
        "items": [
            {
                "name": i.get("name"),
                "category": i.get("category"),
                "color": i.get("color"),
                "wear_count": i.get("wear_count"),
            }
            for i in items
        ],
    }


async def _estimate_outfits_unlocked(session: AsyncSession, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """How many complete outfits a *hypothetical* purchase would unlock.

    Runs the same deterministic builder the shopping check uses, so the number
    the agent quotes matches what the product would say elsewhere. The agent
    supplies the candidate's attributes; the maths stays in Python.
    """
    category = str(args.get("category") or "").strip()
    if not category:
        return {"error": "category is required"}

    candidate: dict[str, Any] = {
        "id": "hypothetical",
        "name": str(args.get("name") or f"{args.get('color') or ''} {category}").strip(),
        "category": category,
        "color": str(args.get("color") or ""),
        "fabric": str(args.get("fabric") or ""),
        "pattern": str(args.get("pattern") or ""),
        "occasion": args.get("occasion") if isinstance(args.get("occasion"), list) else [],
    }

    closet = await _fetch_closet(session, user_id)
    if not closet:
        return {
            "candidate": candidate["name"],
            "completes_outfits": 0,
            "note": "No available closet items to pair with.",
        }

    completes, capped = outfit_builder.count_completable_outfits(candidate, closet)
    return {
        "candidate": candidate["name"],
        "category": category,
        "completes_outfits": completes,
        "capped": capped,
        "closet_items_considered": len(closet),
    }


# ── Individual tools ──────────────────────────────────────────────────────────
#
# Exposed one-per-function rather than only as a bundle so other agents can
# compose the subset they need — the shopping advisor reuses three of these four.
# Each builder binds the session and user id by closure; see :func:`build_tools`.


def wardrobe_stats_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="get_wardrobe_stats",
        description=(
            "Overall wardrobe health: item counts, thin/missing categories, utilization rate, "
            "cost-per-wear averages, worst-value items, forgotten gems (owned but unworn), and "
            "the most versatile pieces. Call this first for any question about what to buy, "
            "what is underused, or how the wardrobe is performing."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda args: _get_wardrobe_stats(session, user_id, args),
        result_label="Wardrobe statistics",
    )


def purchase_gaps_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="get_purchase_gaps",
        description=(
            "Wardrobe gaps already detected for this user (missing categories, colours, or "
            "occasion coverage), ranked by priority. Use to ground buying advice in gaps the "
            "product has already identified rather than inventing new ones."
        ),
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda args: _get_purchase_gaps(session, user_id, args),
        result_label="Detected purchase gaps",
    )


def search_closet_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="search_closet",
        description=(
            "Semantic search over the items this user actually owns. Use to check whether they "
            "already own something before recommending a purchase, or to inspect a category the "
            "stats flagged. Returns names, categories, colours and wear counts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language description, e.g. 'navy tailored blazer'.",
                },
                "limit": {"type": "integer", "description": "Max items to return (1-15).", "default": 8},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=lambda args: _search_closet(session, user_id, args),
        result_label="Closet search results",
    )


def outfits_unlocked_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="estimate_outfits_unlocked",
        description=(
            "Compute how many complete, wearable outfits a hypothetical new item would unlock "
            "from the items the user already owns. Use this to compare buying options — it is "
            "the deterministic buy-signal, so prefer it over guessing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "One of: tops, bottoms, dresses, outerwear, shoes, accessories.",
                },
                "color": {"type": "string", "description": "Primary colour, e.g. 'navy'."},
                "fabric": {"type": "string", "description": "Fabric/material, e.g. 'wool'."},
                "pattern": {"type": "string", "description": "Pattern, e.g. 'striped'. Omit for solid."},
                "occasion": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Occasion tags, e.g. ['work', 'formal'].",
                },
            },
            "required": ["category"],
            "additionalProperties": False,
        },
        handler=lambda args: _estimate_outfits_unlocked(session, user_id, args),
        result_label="Outfit-unlock estimate",
    )


# ── Registry ──────────────────────────────────────────────────────────────────


def build_tools(session: AsyncSession, user_id: str) -> list[AgentTool]:
    """The wardrobe analyst's full tool set, bound to one request.

    The user id is captured by closure rather than exposed as a tool parameter —
    the model can't ask for someone else's wardrobe because it has no way to name one.
    """
    return [
        wardrobe_stats_tool(session, user_id),
        purchase_gaps_tool(session, user_id),
        search_closet_tool(session, user_id),
        outfits_unlocked_tool(session, user_id),
    ]
