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
    _resolve,
    _resolve_list,
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

    source_dict = _normalise_source({
        "name":     source.name,
        "category": source.category,
        "color":    source.color or "",
        "fabric":   source.fabric or "",
        "pattern":  source.pattern or "",
        "season":   source.season or [],
        "occasion": source.occasion or [],
        "tags":     source.tags or [],
        "notes":    source.notes or "",
        "brand":    source.brand or "",
    })

    embedding = await _ensure_item_embedding(session, source)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=limit * 3,
            threshold=0.55,
            filter_archived=True,
            exclude_id=item_id,
        )
        if rows:
            reranked = _hybrid_rerank(rows, source_dict)
            filtered = [r for r in reranked if r["similarity_score"] >= 0.70]
            return _format_similarity_results(filtered[:limit], source_dict)

    # Metadata fallback
    return await _metadata_fallback_search(session, user_id, item_id, source_dict, limit)


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


# ── Vision-metadata normalisation ─────────────────────────────────────────────

def _normalise_source(source_metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Produce a canonical dict with both DB-column names AND vision-analysis aliases
    so item_to_embedding_text() resolves all fields correctly.

    Vision analysis returns: primary_color, material, occasion_tags, season_tags,
    style_tags, description, subcategory, fit.

    DB columns use: color, fabric, occasion, season, tags, notes.

    We keep BOTH so _resolve() / _resolve_list() always finds a value.
    """
    color    = _resolve(source_metadata, "color", "primary_color")
    fabric   = _resolve(source_metadata, "fabric", "material")
    occasion = _resolve_list(source_metadata, "occasion", "occasion_tags")
    season   = _resolve_list(source_metadata, "season", "season_tags")
    tags     = _resolve_list(source_metadata, "tags", "style_tags")
    notes    = _resolve(source_metadata, "notes", "description")

    return {
        **source_metadata,          # keep originals so callers still work
        "color":    color,
        "primary_color": color,
        "fabric":   fabric,
        "material": fabric,
        "occasion": occasion,
        "occasion_tags": occasion,
        "season":   season,
        "season_tags": season,
        "tags":     tags,
        "style_tags": tags,
        "notes":    notes,
        "description": notes,
    }


# ── Category-aware post-filtering ─────────────────────────────────────────────

# Items flagged as "similar" should be in the same category family.
# Cross-category results are valid pairings but NOT "similar items".
_CATEGORY_GROUPS: list[frozenset[str]] = [
    frozenset({"tops", "shirt", "t-shirt", "blouse", "sweater", "hoodie",
               "jumper", "polo", "tank", "top", "turtleneck", "henley"}),
    frozenset({"bottoms", "pants", "trousers", "jeans", "shorts", "skirt",
               "leggings", "chinos", "joggers", "slacks"}),
    frozenset({"outerwear", "jacket", "coat", "blazer", "cardigan", "vest",
               "puffer", "windbreaker", "parka", "trench"}),
    frozenset({"shoes", "sneakers", "boots", "heels", "flats", "sandals",
               "loafers", "oxfords", "mules", "pumps", "footwear"}),
    frozenset({"dresses", "dress", "jumpsuit", "romper", "gown", "playsuit"}),
    frozenset({"accessories", "bag", "belt", "scarf", "hat", "cap", "watch",
               "jewelry", "sunglasses", "tie", "pocket square", "gloves"}),
    frozenset({"activewear", "sport", "gym", "athletic", "sportswear",
               "leggings", "sports bra", "shorts"}),
]


def _same_category_family(cat_a: str, cat_b: str) -> bool:
    a, b = cat_a.lower().strip(), cat_b.lower().strip()
    if a == b:
        return True
    for grp in _CATEGORY_GROUPS:
        if a in grp and b in grp:
            return True
    return False


def _hybrid_rerank(
    rows: list[dict[str, Any]],
    source: dict[str, Any],
    boost_same_category: float = 0.05,
    penalise_cross_category: float = 0.15,
) -> list[dict[str, Any]]:
    """
    Adjust raw cosine scores based on category compatibility and key metadata
    matches, then re-sort.  This corrects cases where the embedding model places
    semantically unrelated items close together (e.g. a white sneaker near a
    white blouse just because of the shared colour token).

    Rules:
    - Same category family  → +boost_same_category to cosine score
    - Different category    → -penalise_cross_category (hard penalty)
    - Exact same color      → +0.03
    - Exact same pattern    → +0.02
    """
    src_cat   = source.get("category", "").lower()
    src_color = _resolve(source, "color", "primary_color").lower()
    src_pat   = _resolve(source, "pattern").lower()

    adjusted: list[dict[str, Any]] = []
    for r in rows:
        score = float(r.get("similarity_score", 0))
        row_cat   = (r.get("category") or "").lower()
        row_color = (r.get("color") or "").lower()
        row_pat   = (r.get("pattern") or "").lower()

        if src_cat and row_cat:
            if _same_category_family(src_cat, row_cat):
                score += boost_same_category
            else:
                score -= penalise_cross_category

        if src_color and row_color and src_color == row_color:
            score += 0.03
        if src_pat and row_pat and src_pat == row_pat and src_pat not in ("solid", "unknown", ""):
            score += 0.02

        adjusted.append({**r, "similarity_score": max(0.0, min(1.0, score))})

    adjusted.sort(key=lambda x: x["similarity_score"], reverse=True)
    return adjusted


# ── Similarity check for NEW (not-yet-saved) items ────────────────────────────

async def check_similar_for_new_item(
    session: AsyncSession,
    user_id: str,
    source_metadata: dict[str, Any],
    limit: int = 5,
    threshold_score: int = 70,
) -> list[dict[str, Any]]:
    """
    Check if a newly uploaded item (not saved yet) is similar to existing closet items.

    Strategy:
    1. Normalise field names (handles both vision-analysis and DB-column naming)
    2. Embedding-based pgvector search (items WITH embeddings)
    3. Hybrid category-aware re-ranking to remove false positives
    4. Metadata fallback (items WITHOUT embeddings, or when pgvector unavailable)
    5. Merge both result sets — deduplicating by item ID, keeping higher score

    Runs BOTH paths every time so that recently-saved items (whose background
    embedding task hasn't completed yet) are still caught by the metadata scorer.
    """
    normalised = _normalise_source(source_metadata)
    text = item_to_embedding_text(normalised)
    threshold_frac = threshold_score / 100

    vector_ids: set[str] = set()
    vector_results: list[dict[str, Any]] = []

    embedding = await generate_text_embedding(text)
    if embedding:
        rows = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=limit * 4,          # fetch more, then re-rank and trim
            threshold=0.55,           # tighter raw cosine floor reduces false candidates
            filter_archived=True,
        )
        if rows:
            reranked = _hybrid_rerank(rows, normalised)
            filtered = [r for r in reranked if r["similarity_score"] >= threshold_frac]
            vector_results = _format_similarity_results(filtered[:limit], normalised)
            vector_ids = {r["id"] for r in vector_results}

    # Always run metadata fallback — catches items whose embedding background
    # task hasn't completed yet (common when uploading multiple items quickly)
    metadata_results = await _metadata_fallback_search(
        session, user_id, None, normalised, limit, threshold_score
    )

    # Merge: prefer vector result when an item appears in both (higher precision),
    # then append metadata-only results that vector search missed
    merged = list(vector_results)
    for r in metadata_results:
        if r["id"] not in vector_ids:
            merged.append(r)

    merged.sort(key=lambda x: x["similarity_score"], reverse=True)
    return merged[:limit]


async def _metadata_fallback_search(
    session: AsyncSession,
    user_id: str,
    exclude_item_id: str | None,
    source_metadata: dict[str, Any],
    limit: int = 5,
    threshold_score: int = 70,
) -> list[dict[str, Any]]:
    """Rule-based similarity against items in user's closet, restricted to the same category family."""
    src_cat = (source_metadata.get("category") or "").lower().strip()
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
        # Skip items in a different category family — shared color/season shouldn't
        # flag a white dress as similar to white sneakers
        if src_cat and item.category and not _same_category_family(src_cat, item.category):
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
