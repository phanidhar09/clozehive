"""Read-only tools for the shopping advisor agent.

The anchor tool is :func:`_get_check_result`, which loads the **already-computed**
deterministic verdict for one shopping check. That ordering is the whole design:
the score, the duplicate detection, and the factor breakdown are computed by
``shopping_check_service.analyze_shopping_item`` — a linear, unit-tested pipeline
— and the agent only reads the result. The model never re-scores anything, so an
advisor turn can't disagree with the rating the user is looking at on screen.

The remaining tools are shared with the wardrobe analyst (closet search, outfit
maths, detected gaps) plus fashion-knowledge retrieval for styling questions.

Ownership: the check id arrives as a tool argument (the model reads it from the
question context), so every load is filtered by ``user_id`` in SQL. A model that
invents or is fed someone else's check id gets "not found", not another user's data.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.intelligence.services.agents.loop import AgentTool
from app.api.v1.intelligence.services.agents.wardrobe_tools import (
    outfits_unlocked_tool,
    purchase_gaps_tool,
    search_closet_tool,
)
from app.api.v1.intelligence.services.fashion_rag_service import search_fashion_knowledge
from app.core.logging import get_logger

logger = get_logger("shopping_tools")

# How many matched items from the stored check to surface. The check persists up
# to 5 duplicates + 6 pairings; the model needs the shape, not the full list.
_MAX_MATCHED = 8


async def _get_check_result(session: AsyncSession, user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Load the stored deterministic verdict for one of this user's checks."""
    check_id = str(args.get("check_id") or "").strip()
    if not check_id:
        return {"error": "check_id is required"}

    sql = text("""
        SELECT id, item_analysis, matched_items, buy_score, closet_boost_pct,
               reasoning, input_type, source_url, purchase_decision, created_at
        FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    try:
        result = await session.execute(sql, {"cid": check_id, "uid": user_id})
    except Exception as exc:  # noqa: BLE001 — a malformed uuid is model input, not a bug
        logger.warning("shopping_check_lookup_failed", error=str(exc))
        return {"error": "That check could not be found."}

    row = result.mappings().first()
    if not row:
        return {"error": "That check could not be found."}

    from app.api.v1.intelligence.services.shopping_check_service import rating_color, to_ten_point

    analysis = row["item_analysis"] or {}
    matched = row["matched_items"] or []
    duplicates = [m for m in matched if m.get("is_duplicate")]
    pairings = [m for m in matched if not m.get("is_duplicate")]
    score = row["buy_score"]

    return {
        "check_id": str(row["id"]),
        "item": {
            "name": analysis.get("name"),
            "category": analysis.get("category"),
            "color": analysis.get("primary_color") or analysis.get("color"),
            "brand": analysis.get("brand") or analysis.get("source_brand"),
            "price": analysis.get("source_price"),
            "occasion_tags": analysis.get("occasion_tags") or [],
            "season_tags": analysis.get("season_tags") or [],
        },
        # The authoritative verdict. Present it; never recompute it.
        "rating_out_of_10": to_ten_point(score) if score is not None else None,
        "rating_color": rating_color(score) if score is not None else None,
        "closet_boost_pct": row["closet_boost_pct"],
        "reasoning": row["reasoning"],
        "already_owns_similar": [
            {"name": d.get("name"), "category": d.get("category"), "color": d.get("color")}
            for d in duplicates[:_MAX_MATCHED]
        ],
        "pairs_with_owned": [
            {"name": p.get("name"), "category": p.get("category"), "color": p.get("color")}
            for p in pairings[:_MAX_MATCHED]
        ],
        "pairs_with_count": len(pairings),
        "purchase_decision": row["purchase_decision"],
    }


async def _search_fashion_knowledge(session: AsyncSession, _user_id: str, args: dict[str, Any]) -> dict[str, Any]:
    """Retrieve curated styling rules for a question the check doesn't answer."""
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required", "documents": []}

    docs = await search_fashion_knowledge(session, query, limit=3)
    return {
        "query": query,
        "count": len(docs),
        "documents": [{"title": d["title"], "content": d["content"][:600]} for d in docs],
    }


# ── Registry ──────────────────────────────────────────────────────────────────


def check_result_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="get_check_result",
        description=(
            "Load the stored verdict for a shopping check: the item's attributes, its "
            "0-10 rating and colour, what the user already owns that is similar, what it "
            "pairs with, and the reasoning. ALWAYS call this first — the rating is "
            "authoritative and everything you say must be consistent with it."
        ),
        parameters={
            "type": "object",
            "properties": {"check_id": {"type": "string", "description": "The id of the check being discussed."}},
            "required": ["check_id"],
            "additionalProperties": False,
        },
        handler=lambda args: _get_check_result(session, user_id, args),
        result_label="Shopping check verdict",
    )


def fashion_knowledge_tool(session: AsyncSession, user_id: str) -> AgentTool:
    return AgentTool(
        name="search_fashion_knowledge",
        description=(
            "Retrieve curated styling guidance (colour, formality, proportion, occasion rules). "
            "Use for styling questions the check data alone cannot answer, e.g. how to wear the "
            "item or whether a colour works for the user."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up, e.g. 'styling a camel overcoat'."}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=lambda args: _search_fashion_knowledge(session, user_id, args),
        result_label="Fashion knowledge",
    )


def build_tools(session: AsyncSession, user_id: str) -> list[AgentTool]:
    """The shopping advisor's tool set, bound to one request.

    Three of these are shared verbatim with the wardrobe analyst — the same
    closet questions come up whether the user is auditing their wardrobe or
    weighing one purchase, and duplicated tools would drift apart.
    """
    return [
        check_result_tool(session, user_id),
        search_closet_tool(session, user_id),
        outfits_unlocked_tool(session, user_id),
        purchase_gaps_tool(session, user_id),
        fashion_knowledge_tool(session, user_id),
    ]
