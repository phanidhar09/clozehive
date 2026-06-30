"""Mine learned fashion knowledge from real usage (wear events + saved outfits).

This is the most defensible knowledge ClozeHive owns: what users *actually* wear and
keep, not generic blog advice. It aggregates at the **attribute level** (category role,
colour family, formality) across the whole community — never per-user, never item or
name level — and only emits insights once there is enough data to generalise (minimum
distinct users + minimum outfits), so it can't leak an individual or overfit to noise.

Output is one or more ``category="learned"`` documents (``source: "user_data"``) added to
the same ``fashion_knowledge_documents`` table the curated corpus uses, so the stylist
retrieves them through the existing RAG path. Unlike the curated seed, learned docs are
*refreshed* (delete-and-rebuild by category) because the underlying behaviour drifts.

The aggregation core (:func:`summarize_pairings`) is pure and unit-tested; the DB read
(:func:`collect_outfit_attribute_sets`) and KB write (:func:`refresh_learned_knowledge`)
are thin wrappers around it.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import outfit_compatibility as compat
from app.core.logging import get_logger
from app.models.closet import ClosetItem, Outfit, WearEvent
from app.models.rag import FashionKnowledgeDocument, OutfitHistory

logger = get_logger("knowledge_mining_service")

# Don't emit "learned" knowledge until the signal generalises — guards privacy
# (no single user is identifiable in an aggregate) and quality (no overfitting to noise).
_MIN_OUTFITS = 15
_MIN_USERS = 3
# An AI recommendation counts as "successful" — and therefore a positive signal — if the
# user saved it, wore it, or it scored highly. These are the outfits worth learning from.
_GOOD_SCORE = 75


def is_successful_history(was_saved: bool, was_worn: bool, matching_score: int | None) -> bool:
    """Whether an OutfitHistory row is a positive signal worth mining."""
    return bool(was_saved) or bool(was_worn) or (matching_score is not None and matching_score >= _GOOD_SCORE)

_LEARNED_CATEGORY = "learned"
_LEARNED_TITLE = "Learned Wardrobe Patterns (Community Usage)"

# Natural garment order so reported pairings read "top+bottom", not alphabetical "bottom+top".
_ROLE_ORDER = {"top": 0, "bottom": 1, "onepiece": 2, "layer": 3, "shoe": 4, "accessory": 5}


def _order_roles(a: str, b: str) -> tuple[str, str]:
    return (a, b) if _ROLE_ORDER.get(a, 9) <= _ROLE_ORDER.get(b, 9) else (b, a)


def _formality_band(level: float) -> str:
    if level < 1.6:
        return "casual"
    if level < 2.7:
        return "smart casual"
    return "dressy"


def summarize_pairings(
    outfits: list[list[dict[str, Any]]],
    num_users: int,
    *,
    min_outfits: int = _MIN_OUTFITS,
    min_users: int = _MIN_USERS,
) -> dict[str, Any] | None:
    """Aggregate worn/saved outfits into a single learned-knowledge document.

    ``outfits`` is a list of outfits, each a list of item attribute dicts
    (``category``, ``color``/``primary_color``). Returns a seed-shaped document dict
    (``title``/``category``/``content``/``tags``/``source`` …) or ``None`` when there
    isn't enough data to generalise safely.
    """
    usable = [o for o in outfits if len(o) >= 2]
    if len(usable) < min_outfits or num_users < min_users:
        return None

    role_pairs: Counter[tuple[str, str]] = Counter()
    color_combo: Counter[str] = Counter()  # neutral-neutral | neutral-accent | accent-accent
    role_counts: Counter[str] = Counter()
    color_family: Counter[str] = Counter()
    formality_bands: Counter[str] = Counter()
    neutral_anchored = 0

    for outfit in usable:
        roles = [compat.category_role(it.get("category")) for it in outfit]
        kinds = [compat.color_profile(it.get("primary_color") or it.get("color"))[0] for it in outfit]
        levels = [compat.formality_level(it) for it in outfit]

        for r in roles:
            if r != "other":
                role_counts[r] += 1
        for it in outfit:
            fam = (str(it.get("primary_color") or it.get("color") or "")).strip().lower()
            if fam:
                color_family[fam] += 1
        if levels:
            formality_bands[_formality_band(sum(levels) / len(levels))] += 1
        if any(k == "neutral" for k in kinds):
            neutral_anchored += 1

        # Unordered attribute pairs within the outfit.
        for i in range(len(outfit)):
            for j in range(i + 1, len(outfit)):
                if "other" not in (roles[i], roles[j]) and roles[i] != roles[j]:
                    role_pairs[_order_roles(roles[i], roles[j])] += 1
                ki, kj = kinds[i], kinds[j]
                if "unknown" not in (ki, kj):
                    if ki == "neutral" and kj == "neutral":
                        color_combo["neutral-neutral"] += 1
                    elif ki == "neutral" or kj == "neutral":
                        color_combo["neutral-accent"] += 1
                    else:
                        color_combo["accent-accent"] += 1

    n = len(usable)
    top_role_pairs = role_pairs.most_common(3)
    top_roles = role_counts.most_common(3)
    top_colors = color_family.most_common(5)
    top_band = formality_bands.most_common(1)
    neutral_pct = round(100 * neutral_anchored / n)
    combo_total = sum(color_combo.values()) or 1
    accent_accent_pct = round(100 * color_combo.get("accent-accent", 0) / combo_total)

    parts = [
        f"Learned from {n} recently worn and saved outfits across {num_users} users "
        f"(aggregated, anonymised — refreshed periodically)."
    ]
    if top_role_pairs:
        pairs_str = ", ".join(f"{a}+{b}" for (a, b), _ in top_role_pairs)
        parts.append(f"Most-worn garment pairings: {pairs_str}.")
    if top_roles:
        parts.append("Most-worn categories: " + ", ".join(f"{r}" for r, _ in top_roles) + ".")
    if top_colors:
        parts.append("Most-worn colours: " + ", ".join(c for c, _ in top_colors) + ".")
    parts.append(
        f"{neutral_pct}% of worn outfits include at least one neutral, and only {accent_accent_pct}% "
        f"pair two saturated colours — community usage favours a neutral base with a single colour accent."
    )
    if top_band:
        parts.append(f"The most common real-world formality is {top_band[0][0]}.")
    parts.append(
        "Recommendation grounded in actual wear: anchor looks on a neutral and add one accent colour "
        "for combinations users keep and re-wear."
    )

    return {
        "title": _LEARNED_TITLE,
        "category": _LEARNED_CATEGORY,
        "season": None,
        "occasion": None,
        "tags": ["learned", "community", "usage", "neutral base", "pairings"],
        "gender": "unisex",
        "region": None,
        "source": "user_data",
        "content": " ".join(parts),
    }


async def collect_outfit_attribute_sets(session: AsyncSession) -> tuple[list[list[dict[str, Any]]], int]:
    """Build attribute-only outfit sets from worn (wear_events) + saved (outfits) data.

    Returns ``(outfits, num_distinct_users)`` where each outfit is a list of item
    attribute dicts. No user IDs, item IDs, or names leave this function.
    """
    # Map every non-archived closet item to its styling attributes.
    item_rows = await session.execute(
        select(
            ClosetItem.id,
            ClosetItem.user_id,
            ClosetItem.category,
            ClosetItem.color,
            ClosetItem.fabric,
            ClosetItem.occasion,
        ).where(ClosetItem.is_archived == False)  # noqa: E712
    )
    attrs: dict[UUID, dict[str, Any]] = {}
    for row in item_rows:
        attrs[row.id] = {
            "category": row.category,
            "color": row.color or "",
            "primary_color": row.color or "",
            "fabric": row.fabric or "",
            "occasion": row.occasion or [],
        }

    outfits: list[list[dict[str, Any]]] = []
    users: set[UUID] = set()

    # Worn-together: wear events grouped by their outfit_id.
    worn_rows = await session.execute(
        select(WearEvent.user_id, WearEvent.outfit_id, WearEvent.item_id).where(WearEvent.outfit_id.isnot(None))
    )
    grouped: dict[tuple[UUID, UUID], list[UUID]] = {}
    for user_id, outfit_id, item_id in worn_rows:
        grouped.setdefault((user_id, outfit_id), []).append(item_id)
    for (user_id, _oid), item_ids in grouped.items():
        items = [attrs[i] for i in item_ids if i in attrs]
        if len(items) >= 2:
            outfits.append(items)
            users.add(user_id)

    def _resolve(item_ids: list[Any] | None) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for raw in item_ids or []:
            try:
                parsed.append(attrs[UUID(str(raw))])
            except (ValueError, KeyError):
                continue
        return parsed

    # Saved outfits — an explicit keep signal.
    saved_rows = await session.execute(select(Outfit.user_id, Outfit.item_ids))
    for user_id, item_ids in saved_rows:
        items = _resolve(item_ids)
        if len(items) >= 2:
            outfits.append(items)
            users.add(user_id)

    # Successful AI recommendations (saved / worn / high-scored) — the rating+feedback signal.
    history_rows = await session.execute(
        select(
            OutfitHistory.user_id,
            OutfitHistory.selected_item_ids,
            OutfitHistory.was_saved,
            OutfitHistory.was_worn,
            OutfitHistory.matching_score,
        )
    )
    for user_id, item_ids, was_saved, was_worn, score in history_rows:
        if not is_successful_history(was_saved, was_worn, score):
            continue
        items = _resolve(item_ids)
        if len(items) >= 2:
            outfits.append(items)
            users.add(user_id)

    return outfits, len(users)


async def refresh_learned_knowledge(session: AsyncSession) -> int:
    """Rebuild the learned-knowledge document from current usage. Returns docs written (0 or 1).

    Safe to run on a schedule. Deletes prior ``category="learned"`` docs and re-creates
    from fresh aggregates; emits nothing (and clears stale docs) when data is too thin.
    """
    from app.core.embedding_service import generate_text_embedding

    outfits, num_users = await collect_outfit_attribute_sets(session)
    doc = summarize_pairings(outfits, num_users)

    # Clear previous learned docs so the refresh can't accumulate stale versions.
    existing = await session.execute(
        select(FashionKnowledgeDocument).where(FashionKnowledgeDocument.category == _LEARNED_CATEGORY)
    )
    for row in existing.scalars().all():
        await session.delete(row)

    if doc is None:
        logger.info("learned_knowledge_insufficient_data", outfits=len(outfits), users=num_users)
        return 0

    content_for_embedding = f"Title: {doc['title']}. {doc['content']}"
    embedding = await generate_text_embedding(content_for_embedding)
    session.add(
        FashionKnowledgeDocument(
            title=doc["title"],
            content=doc["content"],
            category=doc["category"],
            season=doc.get("season"),
            occasion=doc.get("occasion"),
            tags={
                "tags": doc.get("tags", []),
                "gender": doc.get("gender"),
                "source": doc.get("source"),
            },
            embedding=embedding,
        )
    )
    logger.info("learned_knowledge_refreshed", outfits=len(outfits), users=num_users)
    return 1
