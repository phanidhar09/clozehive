"""Purchase Gap Detection service.

Analyzes the user's closet, outfit history, and packing plans to detect
wardrobe gaps and generate prioritized purchase recommendations.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rag import PurchaseGap

logger = get_logger("purchase_gap_service")


# ── Gap detection helpers ─────────────────────────────────────────────────────

_ESSENTIAL_CATEGORIES = {
    "tops",
    "bottoms",
    "shoes",
    "outerwear",
    "accessories",
    "dresses",
}

_OCCASION_ESSENTIALS: dict[str, list[str]] = {
    "formal": ["shoes", "outerwear", "accessories"],
    "business casual": ["tops", "bottoms", "shoes"],
    "beach": ["shoes", "accessories"],
    "wedding": ["shoes", "accessories", "outerwear"],
}

# Recognized wardrobe terms used to ground LLM ``missing_pieces``. Exact
# aliases map 1:1; longer phrases that *contain* an alias (e.g. "brown suede
# Chelsea boots") keep the full specific label while still resolving a category.
_PIECE_CATEGORY_ALIASES: dict[str, str] = {
    # tops
    "top": "tops",
    "tops": "tops",
    "shirt": "tops",
    "blouse": "tops",
    "tee": "tops",
    "t-shirt": "tops",
    "tshirt": "tops",
    "sweater": "tops",
    "knit": "tops",
    "polo": "tops",
    "oxford": "tops",
    "turtleneck": "tops",
    "hoodie": "tops",
    # bottoms
    "bottom": "bottoms",
    "bottoms": "bottoms",
    "pants": "bottoms",
    "trousers": "bottoms",
    "jeans": "bottoms",
    "skirt": "bottoms",
    "shorts": "bottoms",
    "chinos": "bottoms",
    # shoes / footwear
    "shoe": "shoes",
    "shoes": "shoes",
    "footwear": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "heels": "shoes",
    "sandals": "shoes",
    "loafers": "shoes",
    "oxfords": "shoes",
    "trainers": "shoes",
    # outerwear
    "outerwear": "outerwear",
    "jacket": "outerwear",
    "coat": "outerwear",
    "blazer": "outerwear",
    "cardigan": "outerwear",
    "overcoat": "outerwear",
    "trench": "outerwear",
    # accessories
    "accessory": "accessories",
    "accessories": "accessories",
    "belt": "accessories",
    "hat": "accessories",
    "scarf": "accessories",
    "bag": "accessories",
    "jewelry": "accessories",
    "watch": "accessories",
    "tie": "accessories",
    "sunglasses": "accessories",
    "gloves": "accessories",
    "socks": "accessories",
    # dresses / one-pieces
    "dress": "dresses",
    "dresses": "dresses",
    "gown": "dresses",
    "jumpsuit": "dresses",
}

# Concrete starter pieces for empty essential categories — never "versatile".
# Each entry names a particular item and the outfit type it unlocks.
_STRUCTURAL_STARTERS: dict[str, dict[str, str]] = {
    "tops": {
        "item": "crisp white or light-blue button-down shirt",
        "outfit_type": "work / business casual",
        "color": "white",
    },
    "bottoms": {
        "item": "dark straight-leg trousers or well-fitting jeans",
        "outfit_type": "everyday / work",
        "color": "navy or black",
    },
    "shoes": {
        "item": "clean white leather sneakers or brown loafers",
        "outfit_type": "everyday casual",
        "color": "white or brown",
    },
    "outerwear": {
        "item": "navy blazer or camel lightweight trench",
        "outfit_type": "work / smart casual",
        "color": "navy or camel",
    },
    "accessories": {
        "item": "simple leather belt or everyday crossbody bag",
        "outfit_type": "everyday outfits",
        "color": "brown or black",
    },
    "dresses": {
        "item": "solid midi wrap or shirt dress",
        "outfit_type": "day-to-evening",
        "color": "navy or black",
    },
}

# When the LLM only returns a bare category (e.g. "shoes"), pick a concrete
# shopping suggestion for the outfit occasion being built.
_OCCASION_ITEM_HINTS: dict[str, dict[str, str]] = {
    "formal": {
        "tops": "crisp white dress shirt",
        "bottoms": "tailored black or charcoal dress trousers",
        "shoes": "black leather oxfords or polished loafers",
        "outerwear": "structured navy or black blazer",
        "accessories": "slim leather belt and simple dress watch",
        "dresses": "elegant midi or cocktail dress",
    },
    "business": {
        "tops": "light-blue or white oxford shirt",
        "bottoms": "navy chinos or tailored trousers",
        "shoes": "brown or black leather loafers",
        "outerwear": "navy blazer",
        "accessories": "leather belt matching your shoes",
        "dresses": "tailored sheath or shirt dress",
    },
    "business casual": {
        "tops": "light-blue or white oxford shirt",
        "bottoms": "navy chinos or tailored trousers",
        "shoes": "brown or black leather loafers",
        "outerwear": "navy blazer",
        "accessories": "leather belt matching your shoes",
        "dresses": "tailored sheath or shirt dress",
    },
    "work": {
        "tops": "polished button-down or fine-knit sweater",
        "bottoms": "dark trousers or smart jeans",
        "shoes": "leather loafers or clean minimal sneakers",
        "outerwear": "blazer or structured coat",
        "accessories": "leather belt",
        "dresses": "smart midi dress",
    },
    "date": {
        "tops": "fitted dark knit or silk blouse",
        "bottoms": "dark well-cut jeans or trousers",
        "shoes": "leather Chelsea boots or heeled sandals",
        "outerwear": "leather jacket or tailored coat",
        "accessories": "statement belt or simple jewelry",
        "dresses": "flattering midi dress",
    },
    "wedding": {
        "tops": "dress shirt suitable for a suit",
        "bottoms": "suit trousers or formal bottoms",
        "shoes": "polished dress shoes",
        "outerwear": "suit jacket or dressy blazer",
        "accessories": "dress belt and pocket square or jewelry",
        "dresses": "occasion-appropriate cocktail or formal dress",
    },
    "beach": {
        "tops": "breathable linen or resort shirt",
        "bottoms": "shorts or lightweight trousers",
        "shoes": "sandals or espadrilles",
        "outerwear": "light overshirt or cover-up",
        "accessories": "sun hat or tote bag",
        "dresses": "sundress or resort dress",
    },
    "casual": {
        "tops": "well-fitting tee or casual button-up",
        "bottoms": "dark jeans or chinos",
        "shoes": "white sneakers",
        "outerwear": "denim or bomber jacket",
        "accessories": "everyday belt or cap",
        "dresses": "casual day dress",
    },
    "travel": {
        "tops": "wrinkle-resistant knit or travel shirt",
        "bottoms": "comfortable stretch trousers",
        "shoes": "cushioned walking sneakers",
        "outerwear": "packable layer or soft-shell jacket",
        "accessories": "crossbody bag or packing belt",
        "dresses": "easy jersey travel dress",
    },
}

_GENERIC_ITEM_HINTS: dict[str, str] = {
    "tops": "crisp button-down or fine-knit top",
    "bottoms": "dark straight-leg trousers or jeans",
    "shoes": "clean leather sneakers or loafers",
    "outerwear": "structured blazer or light coat",
    "accessories": "leather belt or simple bag",
    "dresses": "solid midi dress",
}

_ALIAS_KEYS_BY_LEN = sorted(_PIECE_CATEGORY_ALIASES.keys(), key=len, reverse=True)


def _normalize_outfit_type(occasion: str | None) -> str | None:
    """Human label for the outfit type a gap unlocks."""
    if not occasion:
        return None
    label = re.sub(r"\s+", " ", occasion.strip().lower())
    if not label or label in {"versatile", "all", "any", "general", "all-season"}:
        return None
    return label


def _specific_item_for(category: str, occasion: str | None, label: str | None = None) -> str:
    """Prefer a concrete shopping phrase over a bare category name."""
    raw = (label or "").strip().lower()
    raw = re.sub(r"^(?:a|an|the)\s+", "", raw)
    # Already a specific phrase (more than a bare alias) — keep it.
    if raw and raw not in _PIECE_CATEGORY_ALIASES and len(raw.split()) >= 2:
        return raw

    occ = _normalize_outfit_type(occasion)
    if occ:
        for key, table in _OCCASION_ITEM_HINTS.items():
            if key in occ or occ in key:
                hint = table.get(category)
                if hint:
                    return hint
    return _GENERIC_ITEM_HINTS.get(category) or raw or category


def _normalize_missing_piece(piece: str) -> tuple[str, str] | None:
    """Ground an LLM ``missing_pieces`` value to a category + shopping label.

    Accepts both bare slots (``"belt"``) and particular items
    (``"brown suede Chelsea boots"``) when they contain a recognized wardrobe
    term. Returns ``(canonical_category, display_label)`` or ``None`` when the
    phrase has no grounded category (invented slots like ``"unicorn cape"``).
    """
    label = (piece or "").strip().lower()
    label = re.sub(r"^(?:a|an|the)\s+", "", label)
    if not label:
        return None

    exact = _PIECE_CATEGORY_ALIASES.get(label)
    if exact is not None:
        return exact, label

    for alias in _ALIAS_KEYS_BY_LEN:
        if re.search(rf"\b{re.escape(alias)}\b", label):
            return _PIECE_CATEGORY_ALIASES[alias], label
    return None


def _dominant_closet_outfit_type(closet_items: list[dict[str, Any]]) -> str | None:
    """Most common occasion tag in the closet — used to name structural gaps."""
    counts: Counter[str] = Counter()
    for item in closet_items:
        occasions = item.get("occasion") or []
        if isinstance(occasions, str):
            occasions = [occasions]
        for occ in occasions:
            normalized = _normalize_outfit_type(str(occ))
            if normalized:
                counts[normalized] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _detect_closet_gaps(
    closet_items: list[dict[str, Any]],
    user_id: str,
) -> list[dict[str, Any]]:
    """Detect structural gaps and attach particular items + outfit types."""
    del user_id  # reserved for future personalization hooks
    gaps: list[dict[str, Any]] = []
    category_counts: Counter = Counter()
    for item in closet_items:
        cat = (item.get("category") or "").lower()
        category_counts[cat] += 1

    closet_outfit_type = _dominant_closet_outfit_type(closet_items)

    for cat in _ESSENTIAL_CATEGORIES:
        if category_counts.get(cat, 0) == 0:
            starter = _STRUCTURAL_STARTERS.get(cat, {})
            outfit_type = closet_outfit_type or starter.get("outfit_type") or "everyday outfits"
            item = _specific_item_for(cat, outfit_type, starter.get("item"))
            color = starter.get("color")
            gaps.append(
                {
                    "gap_type": "structural",
                    "missing_category": cat,
                    "missing_color": color,
                    "missing_occasion": outfit_type,
                    "reason": (
                        f"You're missing a {item} for {outfit_type} outfits — "
                        f"you have no {cat} in your closet yet."
                    ),
                    "priority_score": 0.85 if cat in ("tops", "bottoms", "shoes") else 0.60,
                    "source_context": {"outfit_type": outfit_type},
                    "suggested_attributes": {
                        "item": item,
                        "outfit_type": outfit_type,
                        **({"color": color} if color else {}),
                    },
                }
            )

    tops = category_counts.get("tops", 0)
    bottoms = category_counts.get("bottoms", 0) + category_counts.get("dresses", 0)
    if tops > 0 and bottoms > 0 and tops > bottoms * 2:
        outfit_type = closet_outfit_type or "everyday / work"
        item = _specific_item_for("bottoms", outfit_type)
        gaps.append(
            {
                "gap_type": "proportion",
                "missing_category": "bottoms",
                "missing_occasion": outfit_type,
                "reason": (
                    f"You have {tops} tops but only {bottoms} bottoms/dresses — "
                    f"add {item} to unlock more {outfit_type} outfits."
                ),
                "priority_score": 0.70,
                "source_context": {"outfit_type": outfit_type},
                "suggested_attributes": {
                    "item": item,
                    "outfit_type": outfit_type,
                    "color": "navy or black",
                },
            }
        )
    if bottoms > tops * 2 and tops > 0:
        outfit_type = closet_outfit_type or "everyday / work"
        item = _specific_item_for("tops", outfit_type)
        gaps.append(
            {
                "gap_type": "proportion",
                "missing_category": "tops",
                "missing_occasion": outfit_type,
                "reason": (
                    f"You have {bottoms} bottoms but only {tops} tops — "
                    f"add {item} for more {outfit_type} outfit combinations."
                ),
                "priority_score": 0.70,
                "source_context": {"outfit_type": outfit_type},
                "suggested_attributes": {
                    "item": item,
                    "outfit_type": outfit_type,
                    "color": "white or navy",
                },
            }
        )

    return gaps


def _detect_gaps_from_missing_items(
    missing_items: list[dict[str, Any]],
    source: str,
    source_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert 'you_might_still_need' packing items into purchase gaps."""
    gaps = []
    seen: set[str] = set()
    purpose = _normalize_outfit_type(
        str(source_context.get("purpose") or source_context.get("occasion") or "")
    )
    outfit_type = purpose or f"travel to {source}"
    for item in missing_items:
        name = (item.get("name") or "").strip()
        cat = (item.get("category") or "general").lower()
        key = f"{cat}_{name[:30].lower()}"
        if key in seen:
            continue
        seen.add(key)
        specific = name or _specific_item_for(cat, "travel")
        gaps.append(
            {
                "gap_type": "trip_packing",
                "missing_category": cat,
                "missing_occasion": outfit_type,
                "reason": item.get("reason")
                or f"Pack {specific} for your {outfit_type} trip to {source}.",
                "priority_score": 0.78,
                "source_context": {**source_context, "outfit_type": outfit_type},
                "suggested_attributes": {
                    "item": specific,
                    "outfit_type": outfit_type,
                    "occasion": "travel",
                },
            }
        )
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
        seen_outfit: set[str] = set()
        outfit_type = _normalize_outfit_type(occasion) or "this outfit"
        for piece in outfit_missing_pieces:
            normalized = _normalize_missing_piece(piece)
            if normalized is None:
                logger.info(
                    "purchase_gap_piece_rejected",
                    user_id=user_id,
                    piece=str(piece)[:40],
                )
                continue
            category, label = normalized
            item = _specific_item_for(category, occasion, label)
            dedupe_key = f"{category}|{item}|{outfit_type}"
            if dedupe_key in seen_outfit:
                continue
            seen_outfit.add(dedupe_key)
            all_gaps.append(
                {
                    "gap_type": "outfit",
                    "missing_category": category,
                    "missing_occasion": outfit_type if outfit_type != "this outfit" else occasion,
                    "reason": (
                        f"Add {item} to complete your {outfit_type} outfits — "
                        f"it's the missing piece for this look."
                    ),
                    "priority_score": 0.72,
                    "source_context": {
                        "occasion": occasion,
                        "outfit_type": outfit_type,
                        "missing_piece": label,
                    },
                    "suggested_attributes": {
                        "item": item,
                        "outfit_type": outfit_type,
                        **({"occasion": occasion} if occasion else {}),
                    },
                }
            )

    saved: list[PurchaseGap] = []
    for gap in all_gaps:
        existing_q = select(PurchaseGap).where(
            PurchaseGap.user_id == uid,
            PurchaseGap.missing_category == gap["missing_category"],
            PurchaseGap.gap_type == gap["gap_type"],
            PurchaseGap.resolved == False,  # noqa: E712
        )
        # Allow the same category twice when it serves a different outfit type
        # (e.g. casual sneakers vs formal oxfords).
        occasion_key = gap.get("missing_occasion")
        if occasion_key:
            existing_q = existing_q.where(PurchaseGap.missing_occasion == occasion_key)
        existing = await session.execute(existing_q)
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
    lines = ["[Wardrobe Gaps — particular items to consider purchasing]"]
    for g in gaps:
        attrs = g.get("suggested_attributes") or {}
        item = attrs.get("item") if isinstance(attrs, dict) else None
        outfit_type = (
            (attrs.get("outfit_type") if isinstance(attrs, dict) else None)
            or g.get("missing_occasion")
        )
        label = item or g["missing_category"]
        outfit_bit = f" for {outfit_type} outfits" if outfit_type else ""
        lines.append(
            f"• {label}{outfit_bit} ({g['gap_type']}): {g['reason'][:120]}"
        )
    return "\n".join(lines)
