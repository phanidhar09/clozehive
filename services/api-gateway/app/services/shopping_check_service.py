"""Shopping Check Service — in-store buy/skip advisor.

Flow:
1. Vision AI analyses the photo → extracts item attributes
2. Embedding generated for the new item description
3. pgvector similarity search against user's closet_items
4. Scoring engine computes buy_score (0–100) based on:
   - Duplicate penalty  (very similar item already owned)
   - Outfit compatibility boost (pairs with many existing items)
   - Gap fill boost  (fills a detected purchase_gap)
   - Occasion/season coverage boost
5. Recommendation + reasoning returned
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.embedding_service import (
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
    vector_literal,
)
from app.services.vision_service import analyze_for_bulk
from app.services.upload_service import persist_upload
from app.services import ai_service

logger = get_logger("shopping_check_service")

# ── Scoring weights ──────────────────────────────────────────────────────────
_DUPLICATE_THRESHOLD = 0.88   # cosine sim — item is "essentially the same"
_MATCH_THRESHOLD = 0.65       # cosine sim — item pairs well
_BASE_SCORE = 50.0

_W_DUPLICATE_PENALTY = -35.0
_W_COMPATIBILITY_PER_MATCH = 4.0   # up to +20 for 5 compatible items
_W_GAP_FILL = 20.0
_W_OCCASION_NEW = 12.0
_W_SEASON_NEW = 10.0
_MAX_COMPATIBILITY_BOOST = 20.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_item_text(analysis: dict[str, Any]) -> str:
    """
    Convert vision analysis payload into embedding text.
    Pass both alias variants so item_to_embedding_text resolves whichever is populated.
    """
    return item_to_embedding_text({
        # Both naming conventions kept — _resolve() picks the first non-empty one
        "name":         analysis.get("name", ""),
        "category":     analysis.get("category", ""),
        "subcategory":  analysis.get("subcategory", ""),
        "color":        analysis.get("color", ""),
        "primary_color": analysis.get("primary_color", ""),
        "fabric":       analysis.get("fabric", ""),
        "material":     analysis.get("material", ""),
        "pattern":      analysis.get("pattern", ""),
        "fit":          analysis.get("fit", ""),
        "season":       analysis.get("season") or [],
        "season_tags":  analysis.get("season_tags") or [],
        "occasion":     analysis.get("occasion") or [],
        "occasion_tags": analysis.get("occasion_tags") or [],
        "tags":         analysis.get("tags") or [],
        "style_tags":   analysis.get("style_tags") or [],
        "notes":        analysis.get("notes", ""),
        "description":  analysis.get("description", ""),
        "brand":        analysis.get("brand", ""),
        "secondary_colors": analysis.get("secondary_colors") or [],
    })


async def _fetch_existing_occasions_seasons(
    session: AsyncSession, user_id: str
) -> tuple[set[str], set[str]]:
    """Return sets of occasions and seasons already covered by the user's closet."""
    sql = text("""
        SELECT occasion, season FROM closet_items
        WHERE user_id = CAST(:uid AS uuid) AND is_archived = false
    """)
    result = await session.execute(sql, {"uid": user_id})
    rows = result.mappings().all()
    occasions: set[str] = set()
    seasons: set[str] = set()
    for row in rows:
        for occ in (row["occasion"] or []):
            occasions.add(occ.lower())
        for s in (row["season"] or []):
            seasons.add(s.lower())
    return occasions, seasons


async def _has_open_gap_for_category(
    session: AsyncSession, user_id: str, category: str
) -> bool:
    """Return True if there's an unresolved purchase gap for this category."""
    sql = text("""
        SELECT 1 FROM purchase_gaps
        WHERE user_id = CAST(:uid AS uuid)
          AND resolved = false
          AND LOWER(missing_category) = LOWER(:cat)
        LIMIT 1
    """)
    result = await session.execute(sql, {"uid": user_id, "cat": category})
    return result.first() is not None


# ── Core analysis ─────────────────────────────────────────────────────────────

async def analyze_shopping_item(
    image_bytes: bytes,
    media_type: str,
    user_id: str,
    session: AsyncSession,
    image_url: str | None = None,
) -> dict[str, Any]:
    """
    Analyse a shopping item photo against the user's closet and return a
    buy recommendation with percentage score.
    """
    # 1. Vision analysis
    analysis = await analyze_for_bulk(image_bytes, media_type)
    item_text = _build_item_text(analysis)
    category = analysis.get("category", "").lower()

    # 2. Embed the new item
    embedding = await generate_text_embedding(item_text)

    # 3. Similarity search against closet — fetch extra candidates, re-rank below
    similar_items: list[dict[str, Any]] = []
    if embedding:
        similar_items = await pgvector_cosine_search(
            session=session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=20,                  # fetch more, trim after scoring
            threshold=_MATCH_THRESHOLD,
            filter_archived=True,
        )

    # 4. Existing coverage
    owned_occasions, owned_seasons = await _fetch_existing_occasions_seasons(session, user_id)

    # 5. Compute score
    score = _BASE_SCORE
    reasons: list[str] = []

    # Duplicate check
    has_duplicate = any(
        float(it.get("similarity_score", 0)) >= _DUPLICATE_THRESHOLD
        for it in similar_items
    )
    if has_duplicate:
        score += _W_DUPLICATE_PENALTY
        reasons.append("You already own a very similar item.")

    # Compatibility boost
    compatible_items = [
        it for it in similar_items
        if float(it.get("similarity_score", 0)) < _DUPLICATE_THRESHOLD
    ]
    compat_boost = min(
        len(compatible_items) * _W_COMPATIBILITY_PER_MATCH,
        _MAX_COMPATIBILITY_BOOST,
    )
    if compat_boost > 0:
        score += compat_boost
        reasons.append(
            f"Pairs well with {len(compatible_items)} item(s) already in your closet."
        )

    # Gap fill boost
    if category and await _has_open_gap_for_category(session, user_id, category):
        score += _W_GAP_FILL
        reasons.append(f"Fills a detected gap in your {category} collection.")

    # Occasion novelty
    item_occasions = {o.lower() for o in (analysis.get("occasion_tags") or [])}
    new_occasions = item_occasions - owned_occasions
    if new_occasions and not has_duplicate:
        score += _W_OCCASION_NEW
        reasons.append(
            f"Adds new occasion coverage: {', '.join(new_occasions)}."
        )

    # Season novelty
    item_seasons = {s.lower() for s in (analysis.get("season_tags") or [])}
    new_seasons = item_seasons - owned_seasons
    if new_seasons and not has_duplicate:
        score += _W_SEASON_NEW
        reasons.append(
            f"Extends your wardrobe into: {', '.join(new_seasons)}."
        )

    # Clamp
    score = max(0.0, min(100.0, score))

    # 6. Recommendation label
    if score >= 75:
        recommendation = "buy"
    elif score >= 50:
        recommendation = "consider"
    else:
        recommendation = "skip"

    # 7. Closet boost % — how much this raises wardrobe completeness
    #    Simple heuristic: gap fill = 5%, novel occasions = 3%, novel seasons = 2%
    boost_pct = 0.0
    if category and await _has_open_gap_for_category(session, user_id, category):
        boost_pct += 5.0
    boost_pct += len(new_occasions) * 3.0
    boost_pct += len(new_seasons) * 2.0
    boost_pct = min(boost_pct, 20.0)

    # 8. Build matched item summaries (deduplicated)
    seen_ids: set[str] = set()
    matched_summary = []
    for it in similar_items[:5]:
        iid = str(it.get("id", ""))
        if iid in seen_ids:
            continue
        seen_ids.add(iid)
        matched_summary.append({
            "id": iid,
            "name": it.get("name", ""),
            "category": it.get("category", ""),
            "color": it.get("color", ""),
            "image_url": it.get("processed_image_url") or it.get("image_url"),
            "similarity_score": round(float(it.get("similarity_score", 0)), 3),
            "is_duplicate": float(it.get("similarity_score", 0)) >= _DUPLICATE_THRESHOLD,
        })

    # 9. Persist to DB
    record_id = str(uuid.uuid4())
    reasoning_text = " ".join(reasons) if reasons else "No specific matches found in your closet."

    sql = text("""
        INSERT INTO shopping_checks
            (id, user_id, image_url, item_analysis, matched_items,
             buy_score, buy_recommendation, closet_boost_pct, reasoning, created_at)
        VALUES
            (CAST(:id AS uuid), CAST(:uid AS uuid), :image_url,
             CAST(:analysis AS jsonb), CAST(:matched AS jsonb),
             :score, :rec, :boost, :reason, NOW())
    """)
    import json
    await session.execute(sql, {
        "id": record_id,
        "uid": user_id,
        "image_url": image_url,
        "analysis": json.dumps(analysis),
        "matched": json.dumps(matched_summary),
        "score": round(score, 1),
        "rec": recommendation,
        "boost": round(boost_pct, 1),
        "reason": reasoning_text,
    })
    await session.commit()

    return {
        "check_id": record_id,
        "item_analysis": analysis,
        "matched_items": matched_summary,
        "buy_score": round(score, 1),
        "buy_recommendation": recommendation,
        "closet_boost_pct": round(boost_pct, 1),
        "reasoning": reasoning_text,
    }


async def record_purchase_decision(
    check_id: str,
    user_id: str,
    bought: bool,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Record whether the user actually bought the item."""
    sql = text("""
        UPDATE shopping_checks
        SET purchase_decision = :bought,
            decision_at       = NOW()
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
        RETURNING id, buy_score, buy_recommendation, purchase_decision
    """)
    result = await session.execute(sql, {
        "bought": bought,
        "cid": check_id,
        "uid": user_id,
    })
    row = result.mappings().first()
    if not row:
        return None
    await session.commit()
    return dict(row)


async def get_shopping_history(
    user_id: str,
    session: AsyncSession,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return the user's recent shopping checks, newest first."""
    sql = text("""
        SELECT id, image_url, item_analysis, matched_items, buy_score,
               buy_recommendation, closet_boost_pct, reasoning,
               purchase_decision, decision_at, created_at
        FROM shopping_checks
        WHERE user_id = CAST(:uid AS uuid)
        ORDER BY created_at DESC
        LIMIT :lim
    """)
    result = await session.execute(sql, {"uid": user_id, "lim": limit})
    rows = result.mappings().all()
    return [_shopping_check_row(dict(r)) for r in rows]


def _shopping_check_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize DB row for API responses (id → check_id)."""
    out = dict(row)
    if "id" in out:
        out["check_id"] = str(out.pop("id"))
    return out


async def delete_shopping_check(
    check_id: str,
    user_id: str,
    session: AsyncSession,
) -> tuple[bool, str | None]:
    """
    Delete a shopping check owned by the user.

    Returns (found, image_url) where image_url is set when a stored image
    should be cleaned up (best-effort).
    """
    fetch_sql = text("""
        SELECT image_url FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    result = await session.execute(fetch_sql, {"cid": check_id, "uid": user_id})
    row = result.mappings().first()
    if not row:
        return False, None

    delete_sql = text("""
        DELETE FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    await session.execute(delete_sql, {"cid": check_id, "uid": user_id})
    await session.commit()
    return True, row.get("image_url")


# ── Closet → Shopping: "Complete My Look" ────────────────────────────────────

_MATCH_SUGGESTIONS_SYSTEM = """You are FANI, a professional AI fashion stylist.
Given a wardrobe item and the user's existing closet context, recommend specific shopping items
that would complete outfits and maximise the item's versatility.

Return ONLY a valid JSON object with this exact structure:
{
  "outfit_potential": "high" | "medium" | "low",
  "styling_tip": "<1-2 sentence overall styling advice for this item>",
  "suggestions": [
    {
      "category": "<specific item type to shop for, e.g. 'slim-fit chinos'>",
      "reason": "<why this pairs well — one sentence>",
      "colors": ["<color1>", "<color2>"],
      "occasions": ["<occasion1>"],
      "priority": "high" | "medium" | "low",
      "price_range": "<budget hint e.g. '$30–$80'>"
    }
  ]
}
Return 4–6 suggestions ordered by priority. No markdown fences, raw JSON only."""


async def get_closet_match_suggestions(
    closet_item_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Given a closet item, return AI shopping suggestions for what would pair well.

    Flow:
    1. Fetch the closet item and its metadata.
    2. Find existing items that already pair with it (pgvector search).
    3. Ask the AI to identify the *missing* pieces and return actionable shopping advice.
    """
    import json as _json

    # 1. Fetch closet item
    item_sql = text("""
        SELECT id, name, category, color, fabric, pattern, brand, season,
               occasion, tags, notes, image_url, processed_image_url
        FROM closet_items
        WHERE id = CAST(:iid AS uuid)
          AND user_id = CAST(:uid AS uuid)
          AND is_archived = false
    """)
    res = await session.execute(item_sql, {"iid": closet_item_id, "uid": user_id})
    item_row = res.mappings().first()
    if not item_row:
        return {}

    item = dict(item_row)

    # 2. Build item text + embedding for similarity search
    item_text = item_to_embedding_text({
        "name":     item.get("name", ""),
        "category": item.get("category", ""),
        "color":    item.get("color", ""),
        "fabric":   item.get("fabric", ""),
        "pattern":  item.get("pattern", ""),
        "season":   item.get("season") or [],
        "occasion": item.get("occasion") or [],
        "tags":     item.get("tags") or [],
        "notes":    item.get("notes", ""),
        "brand":    item.get("brand", ""),
    })
    embedding = await generate_text_embedding(item_text)

    # 3. Existing pairing items
    existing_pairs: list[dict[str, Any]] = []
    if embedding:
        rows = await pgvector_cosine_search(
            session=session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=8,
            threshold=0.55,
            filter_archived=True,
        )
        # Exclude the item itself
        existing_pairs = [r for r in rows if str(r.get("id")) != closet_item_id][:5]

    # 4. Build AI prompt
    existing_desc = (
        ", ".join(f"{r.get('name','')} ({r.get('category','')})" for r in existing_pairs)
        if existing_pairs else "none found"
    )
    item_desc = (
        f"{item.get('name','Item')}: {item.get('category','')}, {item.get('color','')} "
        f"{item.get('fabric','')} {item.get('pattern','')}. "
        f"Occasions: {', '.join(item.get('occasion') or [])}. "
        f"Seasons: {', '.join(item.get('season') or [])}."
    )
    user_msg = (
        f"My wardrobe item: {item_desc}\n"
        f"Items I already own that pair with it: {existing_desc}\n"
        "What should I shop for next to get the most out of this piece?"
    )

    # 5. Call AI
    raw_response = await ai_service.chat(
        messages=[{"role": "user", "content": user_msg}],
        system_prompt=_MATCH_SUGGESTIONS_SYSTEM,
    )

    # 6. Parse JSON
    suggestions_data: dict[str, Any] = {}
    try:
        # Strip markdown fences if present
        cleaned = raw_response.strip().strip("```json").strip("```").strip()
        suggestions_data = _json.loads(cleaned)
    except Exception:
        logger.warning("Failed to parse closet-match AI response: %s", raw_response[:200])
        suggestions_data = {
            "outfit_potential": "medium",
            "styling_tip": "This item has great pairing potential. Explore complementary pieces!",
            "suggestions": [],
        }

    # 7. Build response
    image_url = item.get("processed_image_url") or item.get("image_url")
    return {
        "closet_item": {
            "id": str(item["id"]),
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "color": item.get("color", ""),
            "image_url": image_url,
            "occasion": item.get("occasion") or [],
            "season": item.get("season") or [],
        },
        "existing_pairs": [
            {
                "id": str(r.get("id", "")),
                "name": r.get("name", ""),
                "category": r.get("category", ""),
                "image_url": r.get("processed_image_url") or r.get("image_url"),
                "similarity_score": round(float(r.get("similarity_score", 0)), 3),
            }
            for r in existing_pairs
        ],
        "outfit_potential": suggestions_data.get("outfit_potential", "medium"),
        "styling_tip": suggestions_data.get("styling_tip", ""),
        "suggestions": suggestions_data.get("suggestions", []),
    }


async def add_shopping_item_to_closet(
    check_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """
    Create a closet item from an already-analyzed shopping check record.
    Reuses the AI analysis data so no re-analysis is needed.
    """
    import json as _json

    # Fetch the shopping check
    fetch_sql = text("""
        SELECT id, image_url, item_analysis FROM shopping_checks
        WHERE id = CAST(:cid AS uuid)
          AND user_id = CAST(:uid AS uuid)
    """)
    res = await session.execute(fetch_sql, {"cid": check_id, "uid": user_id})
    row = res.mappings().first()
    if not row:
        return None

    analysis = row["item_analysis"]
    if isinstance(analysis, str):
        analysis = _json.loads(analysis)

    # Build embedding text
    item_text = item_to_embedding_text({
        "name":     analysis.get("name", ""),
        "category": analysis.get("category", ""),
        "color":    analysis.get("primary_color") or analysis.get("color", ""),
        "fabric":   analysis.get("material", ""),
        "pattern":  analysis.get("pattern", ""),
        "season":   analysis.get("season_tags") or [],
        "occasion": analysis.get("occasion_tags") or [],
        "tags":     analysis.get("style_tags") or [],
        "notes":    analysis.get("description", ""),
        "brand":    analysis.get("brand", ""),
    })
    embedding = await generate_text_embedding(item_text)
    emb_literal = vector_literal(embedding) if embedding else None

    new_id = str(uuid.uuid4())
    insert_sql = text("""
        INSERT INTO closet_items
            (id, user_id, name, category, color, fabric, pattern, brand,
             season, occasion, tags, notes, image_url,
             wear_count, is_archived, created_at
             {emb_col})
        VALUES
            (CAST(:id AS uuid), CAST(:uid AS uuid),
             :name, :category, :color, :fabric, :pattern, :brand,
             CAST(:season AS jsonb), CAST(:occasion AS jsonb), CAST(:tags AS jsonb),
             :notes, :image_url,
             0, false, NOW()
             {emb_val})
        RETURNING id, name, category, color, image_url, created_at
    """.format(
        emb_col=", embedding" if emb_literal else "",
        emb_val=f", {emb_literal}" if emb_literal else "",
    ))

    import json
    result = await session.execute(insert_sql, {
        "id":       new_id,
        "uid":      user_id,
        "name":     analysis.get("name") or analysis.get("category") or "Shopping Item",
        "category": analysis.get("category", ""),
        "color":    analysis.get("primary_color") or analysis.get("color", ""),
        "fabric":   analysis.get("material", ""),
        "pattern":  analysis.get("pattern", ""),
        "brand":    analysis.get("brand", ""),
        "season":   json.dumps(analysis.get("season_tags") or []),
        "occasion": json.dumps(analysis.get("occasion_tags") or []),
        "tags":     json.dumps(analysis.get("style_tags") or []),
        "notes":    analysis.get("description", ""),
        "image_url": row.get("image_url"),
    })
    await session.commit()
    created = result.mappings().first()
    return dict(created) if created else {"id": new_id}
