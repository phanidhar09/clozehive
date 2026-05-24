"""Closet item similarity search service.

Finds similar items using:
1. Text embeddings (pgvector cosine similarity) — primary
2. Rule-based metadata scoring — fallback when embeddings unavailable

Returns richer results: similarity_label, difference_summary, score as 0–100 int.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.closet import ClosetItem
from app.services.embedding_service import (
    _DEFAULT_LIMIT,
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
)
from app.services.similarity_service import generate_item_embedding

logger = get_logger("closet_similarity_service")


# ── Similarity label thresholds (score is 0–100) ──────────────────────────────

def _similarity_label(score: int) -> str:
    if score >= 90:
        return "Possible duplicate"
    if score >= 75:
        return "Very similar"
    if score >= 55:
        return "Related item"
    return "Not similar"


# ── Difference summary ────────────────────────────────────────────────────────

def _build_difference_summary(source: dict[str, Any], existing: dict[str, Any]) -> str:
    """Generate a human-readable difference summary between two items."""
    diffs: list[str] = []

    # Color
    src_color = (source.get("color") or "").lower().strip()
    ex_color = (existing.get("color") or "").lower().strip()
    if src_color and ex_color and src_color != ex_color:
        diffs.append(f"yours is {src_color}, existing is {ex_color}")

    # Season
    src_season = _to_list(source.get("season_tags") or source.get("season"))
    ex_season = _to_list(existing.get("season"))
    if src_season and ex_season and set(src_season) != set(ex_season):
        diffs.append(f"yours suits {', '.join(src_season)}, theirs {', '.join(ex_season)}")

    # Material
    src_mat = (source.get("material") or "").lower().strip()
    ex_mat = (existing.get("fabric") or "").lower().strip()
    if src_mat and ex_mat and src_mat != ex_mat:
        diffs.append(f"material: {src_mat} vs {ex_mat}")

    # Pattern
    src_pat = (source.get("pattern") or "").lower().strip()
    ex_pat = (existing.get("pattern") or "").lower().strip()
    if src_pat and ex_pat and src_pat != ex_pat:
        diffs.append(f"pattern: {src_pat} vs {ex_pat}")

    if not diffs:
        return "These items look very similar with few obvious differences."
    return "Key differences: " + "; ".join(diffs) + "."


def _build_similarity_reason(score: int, source: dict[str, Any], existing: dict[str, Any]) -> str:
    """Generate a human-readable reason why items are similar."""
    reasons: list[str] = []

    src_cat = (source.get("category") or "").lower()
    ex_cat = (existing.get("category") or "").lower()
    if src_cat and src_cat == ex_cat:
        reasons.append(f"same category ({src_cat})")

    src_color = (source.get("color") or "").lower().strip()
    ex_color = (existing.get("color") or "").lower().strip()
    if src_color and ex_color:
        if src_color == ex_color:
            reasons.append(f"identical color ({src_color})")
        elif _colors_are_close(src_color, ex_color):
            reasons.append("similar color palette")

    src_occ = _to_list(source.get("occasion_tags") or source.get("occasion"))
    ex_occ = _to_list(existing.get("occasion"))
    shared_occ = set(src_occ) & set(ex_occ)
    if shared_occ:
        reasons.append(f"both work for {', '.join(sorted(shared_occ))}")

    if not reasons:
        return f"Similar {src_cat or 'item'} based on overall style and attributes."
    return " · ".join(r.capitalize() for r in reasons) + "."


def _colors_are_close(a: str, b: str) -> bool:
    """Very simple check: do two color strings share a base word?"""
    a_words = set(a.split())
    b_words = set(b.split())
    # neutrals group
    neutrals = {"white", "black", "grey", "gray", "beige", "cream", "ivory", "off-white"}
    if a_words & neutrals and b_words & neutrals:
        return True
    return bool(a_words & b_words)


def _to_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(x).lower().strip() for x in val if x]
    if isinstance(val, str) and val.strip():
        return [val.lower().strip()]
    return []


# ── Metadata-based scoring (fallback, no embeddings needed) ──────────────────

def _metadata_similarity_score(
    source: dict[str, Any],
    existing_item: ClosetItem,
) -> int:
    """
    Rule-based similarity score 0–100.
    Used as fallback when pgvector embeddings are unavailable.
    """
    score = 0

    src_cat = (source.get("category") or "").lower().strip()
    ex_cat = (existing_item.category or "").lower().strip()

    # Category match is the most important signal (40 pts)
    if src_cat and ex_cat:
        if src_cat == ex_cat:
            score += 40
        elif _categories_compatible(src_cat, ex_cat):
            score += 20

    # Color (20 pts)
    src_color = (source.get("color") or "").lower().strip()
    ex_color = (existing_item.color or "").lower().strip()
    if src_color and ex_color:
        if src_color == ex_color:
            score += 20
        elif _colors_are_close(src_color, ex_color):
            score += 10

    # Occasion overlap (15 pts)
    src_occ = set(_to_list(source.get("occasion_tags") or source.get("occasion")))
    ex_occ = set(_to_list(existing_item.occasion))
    if src_occ and ex_occ:
        overlap = len(src_occ & ex_occ)
        score += min(15, overlap * 8)

    # Season overlap (10 pts)
    src_sea = set(_to_list(source.get("season_tags") or source.get("season")))
    ex_sea = set(_to_list(existing_item.season))
    if src_sea and ex_sea:
        overlap = len(src_sea & ex_sea)
        score += min(10, overlap * 5)

    # Pattern match (5 pts)
    src_pat = (source.get("pattern") or "").lower().strip()
    ex_pat = (existing_item.pattern or "").lower().strip()
    if src_pat and ex_pat and src_pat == ex_pat:
        score += 5

    # Material match (5 pts)
    src_mat = (source.get("material") or "").lower().strip()
    ex_mat = (existing_item.fabric or "").lower().strip()
    if src_mat and ex_mat and src_mat == ex_mat:
        score += 5

    # Style tag overlap (5 pts)
    src_tags = set(_to_list(source.get("style_tags") or source.get("tags")))
    ex_tags = set(_to_list(existing_item.tags))
    if src_tags and ex_tags:
        overlap = len(src_tags & ex_tags)
        score += min(5, overlap * 3)

    return min(100, score)


def _categories_compatible(a: str, b: str) -> bool:
    """E.g. 'shirt' and 'tops' are compatible."""
    TOPS = {"tops", "shirt", "t-shirt", "blouse", "sweater", "hoodie", "jumper", "polo"}
    BOTTOMS = {"bottoms", "pants", "trousers", "jeans", "shorts", "skirt", "leggings"}
    OUTERWEAR = {"outerwear", "jacket", "coat", "blazer", "cardigan", "vest"}
    SHOES = {"shoes", "sneakers", "boots", "heels", "flats", "sandals", "loafers"}
    DRESSES = {"dresses", "dress", "jumpsuit", "romper"}
    ACCESSORIES = {"accessories", "bag", "belt", "scarf", "hat", "watch", "jewelry"}
    for group in [TOPS, BOTTOMS, OUTERWEAR, SHOES, DRESSES, ACCESSORIES]:
        if a in group and b in group:
            return True
    return False


# ── Embedding helpers ─────────────────────────────────────────────────────────

async def _ensure_item_embedding(session: AsyncSession, item: ClosetItem) -> list[float] | None:
    """Return the item's embedding, generating and persisting it if missing."""
    if item.embedding:
        return list(item.embedding)
    try:
        embedding = await generate_item_embedding(item)
        item.embedding = embedding
        await session.flush()
        return embedding
    except Exception as exc:
        logger.warning("ensure_embedding_failed", item_id=str(item.id), error=str(exc))
        return None


# ── Similarity search for EXISTING items ────────────────────────────────────

async def find_similar_by_item_id(
    session: AsyncSession,
    item_id: str,
    user_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Find closet items similar to a given existing closet item."""
    source = await session.get(ClosetItem, uuid.UUID(item_id))
    if not source or str(source.user_id) != user_id or source.is_archived:
        return []

    embedding = await _ensure_item_embedding(session, source)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=limit,
            threshold=0.60,
            filter_archived=True,
            exclude_id=item_id,
        )
        if rows:
            source_dict = {
                "category": source.category,
                "color": source.color,
                "occasion_tags": source.occasion,
                "season_tags": source.season,
                "pattern": source.pattern,
                "material": source.fabric,
            }
            return _format_similarity_results(rows, source_dict)

    # Metadata fallback
    return await _metadata_fallback_search(session, user_id, item_id, {
        "category": source.category,
        "color": source.color,
        "occasion_tags": source.occasion,
        "season_tags": source.season,
        "pattern": source.pattern,
        "material": source.fabric,
        "style_tags": source.tags,
    }, limit)


async def find_similar_by_text(
    session: AsyncSession,
    query: str,
    user_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Find closet items matching a text description."""
    embedding = await generate_text_embedding(query)
    if not embedding:
        return []

    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=embedding,
        user_id=user_id,
        limit=limit,
        threshold=0.60,
        filter_archived=True,
    )
    return _format_similarity_results(rows, {})


async def find_similar_by_image_url(
    session: AsyncSession,
    image_url: str,
    user_id: str,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Find items similar to an image URL (text-metadata fallback for MVP)."""
    url_path = image_url.split("/")[-1]
    fallback_text = f"Image: {url_path}"
    return await find_similar_by_text(session, fallback_text, user_id, limit)


# ── Similarity check for NEW (not-yet-saved) items ────────────────────────────

async def check_similar_for_new_item(
    session: AsyncSession,
    user_id: str,
    source_metadata: dict[str, Any],
    limit: int = 5,
    threshold_score: int = 55,
) -> list[dict[str, Any]]:
    """
    Check if a newly uploaded item (not saved yet) is similar to existing closet items.

    Strategy:
    1. Try embedding-based search using metadata text
    2. Fall back to rule-based metadata scoring if embeddings fail
    """
    # Build text from the new item metadata and try embedding search first
    text = item_to_embedding_text({
        "name": source_metadata.get("name", ""),
        "category": source_metadata.get("category", ""),
        "color": source_metadata.get("color") or (source_metadata.get("colors") or [""])[0],
        "fabric": source_metadata.get("material", ""),
        "pattern": source_metadata.get("pattern", ""),
        "season": source_metadata.get("season_tags", []),
        "occasion": source_metadata.get("occasion_tags", []),
        "tags": source_metadata.get("style_tags", []),
    })

    embedding = await generate_text_embedding(text)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=limit,
            threshold=threshold_score / 100,
            filter_archived=True,
        )
        if rows:
            return _format_similarity_results(rows, source_metadata)

    # Fallback: metadata scoring against all items in same/compatible category
    return await _metadata_fallback_search(
        session, user_id, None, source_metadata, limit, threshold_score
    )


async def _metadata_fallback_search(
    session: AsyncSession,
    user_id: str,
    exclude_item_id: str | None,
    source_metadata: dict[str, Any],
    limit: int = 5,
    threshold_score: int = 55,
) -> list[dict[str, Any]]:
    """Rule-based similarity against all items in user's closet."""
    try:
        stmt = select(ClosetItem).where(
            ClosetItem.user_id == uuid.UUID(user_id),
            ClosetItem.is_archived.is_(False),
        )
        result = await session.execute(stmt)
        all_items = result.scalars().all()
    except Exception as exc:
        logger.warning("metadata_fallback_query_failed", error=str(exc))
        return []

    scored: list[tuple[int, ClosetItem]] = []
    for item in all_items:
        if exclude_item_id and str(item.id) == exclude_item_id:
            continue
        score = _metadata_similarity_score(source_metadata, item)
        if score >= threshold_score:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, item in scored[:limit]:
        label = _similarity_label(score)
        reason = _build_similarity_reason(score, source_metadata, {
            "category": item.category,
            "color": item.color,
            "occasion": item.occasion,
            "season": item.season,
        })
        diff = _build_difference_summary(source_metadata, {
            "color": item.color,
            "season": item.season,
            "fabric": item.fabric,
            "pattern": item.pattern,
        })
        results.append({
            "id": str(item.id),
            "item_id": str(item.id),
            "name": item.name,
            "category": item.category,
            "color": item.color or "",
            "brand": item.brand or "",
            "image_url": item.processed_image_url or item.image_url or "",
            "colors": [item.color] if item.color else [],
            "similarity_score": score,
            "similarity_label": label,
            "similarity_reason": reason,
            "difference_summary": diff,
        })

    return results


# ── Result formatting (for embedding-based results) ──────────────────────────

def _format_similarity_results(
    rows: list[dict[str, Any]],
    source_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    results = []
    for r in rows:
        raw_score = float(r.get("similarity_score", 0))
        score_int = min(100, max(0, round(raw_score * 100)))
        label = _similarity_label(score_int)
        reason = _build_similarity_reason(score_int, source_metadata, dict(r))
        diff = _build_difference_summary(source_metadata, dict(r))
        color = r.get("color") or ""
        results.append({
            "id": str(r.get("id", "")),
            "item_id": str(r.get("id", "")),
            "name": r.get("name", ""),
            "category": r.get("category", ""),
            "color": color,
            "brand": r.get("brand") or "",
            "image_url": r.get("processed_image_url") or r.get("image_url") or "",
            "colors": [color] if color else [],
            "similarity_score": score_int,
            "similarity_label": label,
            "similarity_reason": reason,
            "difference_summary": diff,
            # Legacy field for backward-compat
            "reason": reason,
        })
    return results


# ── Legacy duplicate-check on upload ─────────────────────────────────────────

async def check_duplicate_on_upload(
    session: AsyncSession,
    user_id: str,
    item_metadata: dict[str, Any],
    threshold: float = 0.88,
) -> list[dict[str, Any]]:
    """
    Check if a newly uploaded/detected item already exists in the closet.
    Called during bulk ingest confirmation before saving.
    """
    text = item_to_embedding_text(item_metadata)
    embedding = await generate_text_embedding(text)
    if not embedding:
        return []

    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=embedding,
        user_id=user_id,
        limit=3,
        threshold=threshold,
        filter_archived=True,
    )
    return _format_similarity_results(rows, item_metadata)
