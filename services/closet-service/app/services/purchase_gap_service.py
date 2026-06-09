"""Purchase Gap Detection service.

Analyzes the user's closet, outfit history, and packing plans to detect
wardrobe gaps and generate prioritized purchase recommendations.
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rag import OutfitHistory, PackingMemory, PurchaseGap

logger = get_logger("purchase_gap_service")


# ── Gap detection helpers ─────────────────────────────────────────────────────

_ESSENTIAL_CATEGORIES = {
    "tops", "bottoms", "shoes", "outerwear", "accessories", "dresses",
}

_OCCASION_ESSENTIALS: dict[str, list[str]] = {
    "formal": ["shoes", "outerwear", "accessories"],
    "business casual": ["tops", "bottoms", "shoes"],
    "beach": ["shoes", "accessories"],
    "wedding": ["shoes", "accessories", "outerwear"],
}


def _detect_closet_gaps(
    closet_items: list[dict[str, Any]],
    user_id: str,
) -> list[dict[str, Any]]:
    """Detect basic structural gaps in the closet."""
    gaps: list[dict[str, Any]] = []
    category_counts: Counter = Counter()
    for item in closet_items:
        cat = (item.get("category") or "").lower()
        category_counts[cat] += 1

    for cat in _ESSENTIAL_CATEGORIES:
        if category_counts.get(cat, 0) == 0:
            gaps.append({
                "gap_type": "structural",
                "missing_category": cat,
                "reason": f"You have no {cat} in your closet — this is an essential wardrobe category.",
                "priority_score": 0.85 if cat in ("tops", "bottoms", "shoes") else 0.60,
                "suggested_attributes": {"occasion": "versatile", "season": "all-season"},
            })

    tops = category_counts.get("tops", 0)
    bottoms = category_counts.get("bottoms", 0) + category_counts.get("dresses", 0)
    if tops > 0 and bottoms > 0 and tops > bottoms * 2:
        gaps.append({
            "gap_type": "proportion",
            "missing_category": "bottoms",
            "reason": f"You have {tops} tops but only {bottoms} bottoms/dresses — balance your wardrobe.",
            "priority_score": 0.70,
            "suggested_attributes": {"color": "neutral", "occasion": "versatile"},
        })
    if bottoms > tops * 2 and tops > 0:
        gaps.append({
            "gap_type": "proportion",
            "missing_category": "tops",
            "reason": f"You have {bottoms} bottoms but only {tops} tops — add more tops to unlock more outfit combinations.",
            "priority_score": 0.70,
            "suggested_attributes": {"color": "neutral", "season": "all-season"},
        })

    return gaps


def _detect_gaps_from_missing_items(
    missing_items: list[dict[str, Any]],
    source: str,
    source_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert 'you_might_still_need' packing items into purchase gaps."""
    gaps = []
    seen: set[str] = set()
    for item in missing_items:
        name = (item.get("name") or "").strip()
        cat = (item.get("category") or "general").lower()
        key = f"{cat}_{name[:30].lower()}"
        if key in seen:
            continue
        seen.add(key)
        gaps.append({
            "gap_type": "trip_packing",
            "missing_category": cat,
            "reason": item.get("reason") or f"Missing for {source}",
            "priority_score": 0.78,
            "source_context": source_context,
            "suggested_attributes": {"occasion": "travel"},
        })
    return gaps


async def detect_and_save_gaps(
    session: AsyncSession,
    user_id: str,
    closet_items: list[dict[str, Any]],
    missing_packing_items: list[dict[str, Any]] | None = None,
    trip_context: dict[str, Any] | None = None,
    outfit_missing_pieces: list[str] | None = None,
    occasion: str | None = None,
) -> list[PurchaseGap]:
    """Detect gaps and upsert into purchase_gaps table. Returns saved records."""
    uid = uuid.UUID(user_id)
    all_gaps: list[dict[str, Any]] = []

    all_gaps.extend(_detect_closet_gaps(closet_items, user_id))

    if missing_packing_items:
        context = trip_context or {}
        all_gaps.extend(
            _detect_gaps_from_missing_items(
                missing_packing_items,
                source=context.get("destination", "trip"),
                source_context=context,
            )
        )

    if outfit_missing_pieces:
        for piece in outfit_missing_pieces:
            all_gaps.append({
                "gap_type": "outfit",
                "missing_category": piece.lower(),
                "missing_occasion": occasion,
                "reason": f"Missing {piece} to complete your {occasion or 'outfit'} look.",
                "priority_score": 0.72,
                "source_context": {"occasion": occasion},
                "suggested_attributes": {"occasion": occasion or "versatile"},
            })

    saved: list[PurchaseGap] = []
    for gap in all_gaps:
        existing = await session.execute(
            select(PurchaseGap).where(
                PurchaseGap.user_id == uid,
                PurchaseGap.missing_category == gap["missing_category"],
                PurchaseGap.gap_type == gap["gap_type"],
                PurchaseGap.resolved == False,  # noqa: E712
            )
        )
        if existing.scalars().first():
            continue

        record = PurchaseGap(
            user_id=uid,
            gap_type=gap["gap_type"],
            missing_category=gap["missing_category"],
            missing_color=gap.get("missing_color"),
            missing_season=gap.get("missing_season"),
            missing_occasion=gap.get("missing_occasion"),
            reason=gap["reason"],
            priority_score=gap.get("priority_score", 0.5),
            source_context=gap.get("source_context"),
            suggested_attributes=gap.get("suggested_attributes"),
        )
        session.add(record)
        saved.append(record)

    if saved:
        await session.flush()
        logger.info("purchase_gaps_saved", user_id=user_id, count=len(saved))

    return saved


async def get_purchase_gaps(
    session: AsyncSession,
    user_id: str,
    resolved: bool = False,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return the user's purchase gaps ordered by priority score."""
    result = await session.execute(
        select(PurchaseGap)
        .where(
            PurchaseGap.user_id == uuid.UUID(user_id),
            PurchaseGap.resolved == resolved,
        )
        .order_by(desc(PurchaseGap.priority_score), desc(PurchaseGap.created_at))
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "gap_type": r.gap_type,
            "missing_category": r.missing_category,
            "missing_color": r.missing_color,
            "missing_season": r.missing_season,
            "missing_occasion": r.missing_occasion,
            "reason": r.reason,
            "priority_score": float(r.priority_score),
            "source_context": r.source_context,
            "suggested_attributes": r.suggested_attributes,
            "resolved": r.resolved,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


async def resolve_purchase_gap(
    session: AsyncSession,
    gap_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """Mark a purchase gap as resolved."""
    record = await session.get(PurchaseGap, uuid.UUID(gap_id))
    if not record or str(record.user_id) != user_id:
        return None
    record.resolved = True
    await session.flush()
    logger.info("purchase_gap_resolved", gap_id=gap_id, user_id=user_id)
    return {"id": str(record.id), "resolved": True}


async def delete_purchase_gap(
    session: AsyncSession,
    gap_id: str,
    user_id: str,
) -> bool:
    """Permanently delete a purchase gap. Returns True if a row was removed."""
    record = await session.get(PurchaseGap, uuid.UUID(gap_id))
    if not record or str(record.user_id) != user_id:
        return False
    await session.delete(record)
    await session.flush()
    logger.info("purchase_gap_deleted", gap_id=gap_id, user_id=user_id)
    return True


async def get_gap_summary_for_prompt(
    session: AsyncSession,
    user_id: str,
    limit: int = 5,
) -> str:
    """Return a formatted string of top purchase gaps for LLM prompt injection."""
    gaps = await get_purchase_gaps(session, user_id, resolved=False, limit=limit)
    if not gaps:
        return ""
    lines = ["[Wardrobe Gaps — items to consider purchasing]"]
    for g in gaps:
        lines.append(
            f"• Missing {g['missing_category']} ({g['gap_type']}): {g['reason'][:120]}"
        )
    return "\n".join(lines)
