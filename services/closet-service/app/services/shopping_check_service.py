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
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.embedding_service import (
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
    vector_literal,
)
from app.services.vision_service import analyze_for_bulk
from app.services import ai_service
from app.services.fashion_rag_service import get_fashion_context_for_prompt

logger = get_logger("shopping_check_service")

# ── Scoring weights ──────────────────────────────────────────────────────────
_DUPLICATE_THRESHOLD = 0.88   # cosine sim — item is "essentially the same"
_MATCH_THRESHOLD = 0.65       # cosine sim — item pairs well

# Percentage-weighted scoring: each factor weight is the % it can contribute, and
# the weights SUM TO 100. buy_score = Σ(weight × factor_subscore) where each
# subscore is 0–1, so the result is a true 0–100% with no clamping needed.
_WEIGHTS: dict[str, float] = {
    "uniqueness":    30.0,   # not a near-duplicate of something already owned
    "compatibility": 25.0,   # pairs with items already in the closet
    "gap_fill":      20.0,   # fills a detected category gap
    "occasion_new":  15.0,   # adds new occasion coverage
    "season_new":    10.0,   # adds new season coverage
}
assert round(sum(_WEIGHTS.values())) == 100, "buy_score weights must sum to 100%"
_COMPAT_SATURATION = 5       # this many compatible items = full compatibility credit


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

    # 5. Compute percentage-weighted score — each factor yields a 0–1 subscore,
    #    contributes (weight × subscore) %, and all weights sum to 100.
    reasons: list[str] = []

    has_duplicate = any(
        float(it.get("similarity_score", 0)) >= _DUPLICATE_THRESHOLD
        for it in similar_items
    )
    compatible_items = [
        it for it in similar_items
        if float(it.get("similarity_score", 0)) < _DUPLICATE_THRESHOLD
    ]
    item_occasions = {o.lower() for o in (analysis.get("occasion_tags") or [])}
    new_occasions = item_occasions - owned_occasions
    item_seasons = {s.lower() for s in (analysis.get("season_tags") or [])}
    new_seasons = item_seasons - owned_seasons
    fills_gap = bool(category and await _has_open_gap_for_category(session, user_id, category))

    # Factor subscores (0–1)
    subscores: dict[str, float] = {
        "uniqueness":    0.0 if has_duplicate else 1.0,
        "compatibility": min(len(compatible_items) / _COMPAT_SATURATION, 1.0),
        "gap_fill":      1.0 if fills_gap else 0.0,
        # Novelty only counts when the item isn't a duplicate.
        "occasion_new":  1.0 if (new_occasions and not has_duplicate) else 0.0,
        "season_new":    1.0 if (new_seasons and not has_duplicate) else 0.0,
    }

    # Weighted percentage contributions (sum to ≤ 100).
    score_breakdown = {k: round(_WEIGHTS[k] * subscores[k], 1) for k in _WEIGHTS}
    score = round(sum(score_breakdown.values()))
    score = max(0, min(100, score))

    # Human-readable reasons mirror the factors that contributed.
    if has_duplicate:
        reasons.append("You already own a very similar item.")
    if compatible_items:
        reasons.append(f"Pairs well with {len(compatible_items)} item(s) already in your closet.")
    if fills_gap:
        reasons.append(f"Fills a detected gap in your {category} collection.")
    if subscores["occasion_new"]:
        reasons.append(f"Adds new occasion coverage: {', '.join(new_occasions)}.")
    if subscores["season_new"]:
        reasons.append(f"Extends your wardrobe into: {', '.join(new_seasons)}.")

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
    if fills_gap:
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
        "score_breakdown": score_breakdown,
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
You help the user "Complete My Look" around ONE wardrobe item they selected.

You are given the selected item plus the user's full closet inventory (each owned item is
numbered). Your job:
1. Work out the complementary slots needed to build complete outfits around the selected item
   (e.g. for a blazer: a bottom, a shirt, footwear, maybe a belt).
2. For EACH slot, FIRST check the numbered closet inventory. If the user ALREADY OWNS an item
   that fills that slot well, reference it in "closet_pairings" by its number — DO NOT tell them
   to buy it.
3. ONLY recommend buying (in "suggestions") for slots the closet CANNOT fill from owned items.
   If the closet already completes the look, return an empty "suggestions" array.

Prefer using what the user already owns. Be honest — never invent owned items, only use the
provided numbers.

Return ONLY a valid JSON object with this exact structure:
{
  "outfit_potential": "high" | "medium" | "low",
  "styling_tip": "<1-2 sentence overall styling advice for this item>",
  "closet_pairings": [
    {
      "item_number": <integer index from the inventory list>,
      "role": "<the slot it fills, e.g. 'bottom', 'footwear', 'layer'>",
      "reason": "<why it works with the selected item — one short sentence>"
    }
  ],
  "suggestions": [
    {
      "category": "<specific item type to shop for, e.g. 'slim-fit chinos'>",
      "role": "<the slot this fills>",
      "reason": "<why this completes the look and why the closet can't already — one sentence>",
      "colors": ["<color1>", "<color2>"],
      "occasions": ["<occasion1>"],
      "priority": "high" | "medium" | "low",
      "price_range": "<budget hint e.g. '$30–$80'>"
    }
  ]
}
List closet_pairings first (best matches first). Provide at most 4 suggestions, only for genuine
gaps. No markdown fences, raw JSON only."""


async def get_closet_match_suggestions(
    closet_item_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Given a closet item, "Complete My Look": surface owned items that complete an outfit
    around it FIRST, and only suggest buying for slots the closet cannot fill.

    Flow:
    1. Fetch the selected closet item and its metadata.
    2. Fetch the user's full closet inventory (numbered) as matching context.
    3. Ask the AI to fill complementary slots from owned items first, and only recommend
       purchases for the remaining gaps.
    4. Resolve the AI's owned-item references back to real closet rows (id + image).
    """
    import json as _json

    # 1. Fetch selected closet item
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

    # 2. Fetch full closet inventory (excluding the selected item) as matching context
    inv_sql = text("""
        SELECT id, name, category, color, occasion, image_url, processed_image_url
        FROM closet_items
        WHERE user_id = CAST(:uid AS uuid)
          AND is_archived = false
          AND id <> CAST(:iid AS uuid)
        ORDER BY created_at DESC
        LIMIT 60
    """)
    inv_res = await session.execute(inv_sql, {"uid": user_id, "iid": closet_item_id})
    inventory = [dict(r) for r in inv_res.mappings().all()]

    # 3. Build AI prompt — number each owned item so the AI can reference it reliably
    item_desc = (
        f"{item.get('name','Item')}: {item.get('category','')}, {item.get('color','')} "
        f"{item.get('fabric','')} {item.get('pattern','')}. "
        f"Occasions: {', '.join(item.get('occasion') or [])}. "
        f"Seasons: {', '.join(item.get('season') or [])}."
    )
    if inventory:
        inv_lines = "\n".join(
            f"[{i + 1}] {r.get('name','')} — {r.get('category','')}"
            f"{', ' + r.get('color') if r.get('color') else ''}"
            f"{' (' + ', '.join(r.get('occasion')) + ')' if r.get('occasion') else ''}"
            for i, r in enumerate(inventory)
        )
    else:
        inv_lines = "(the closet is otherwise empty)"

    # RAG: ground the styling reasoning in retrieved fashion knowledge (color theory,
    # pairing rules, occasion guidance). Degrades to "" if unavailable.
    knowledge_text = ""
    try:
        rag_query = (
            f"How to complete an outfit around a {item.get('color','')} "
            f"{item.get('category','')}; what pieces pair well for "
            f"{', '.join(item.get('occasion') or ['everyday'])}"
        )
        knowledge_text = await get_fashion_context_for_prompt(session, rag_query, limit=3)
    except Exception as exc:  # noqa: BLE001 — RAG is best-effort context
        logger.warning("closet_match_rag_failed: %s", exc)

    knowledge_block = f"\n\n{knowledge_text}\n" if knowledge_text else ""

    user_msg = (
        f"Selected item to build a look around: {item_desc}\n\n"
        f"My closet inventory (owned items, numbered):\n{inv_lines}\n"
        f"{knowledge_block}\n"
        "Complete the look: pair owned items first, and only suggest buying for gaps the "
        "closet cannot fill. Use the fashion knowledge above to justify pairings where relevant."
    )

    # 4. Call AI
    raw_response = await ai_service.chat(
        messages=[{"role": "user", "content": user_msg}],
        system_prompt=_MATCH_SUGGESTIONS_SYSTEM,
    )

    # 5. Parse JSON
    data: dict[str, Any] = {}
    try:
        cleaned = raw_response.strip().strip("```json").strip("```").strip()
        data = _json.loads(cleaned)
    except Exception:
        logger.warning("Failed to parse closet-match AI response: %s", raw_response[:200])
        data = {
            "outfit_potential": "medium",
            "styling_tip": "This item has great pairing potential. Explore complementary pieces!",
            "closet_pairings": [],
            "suggestions": [],
        }

    # 6. Resolve AI owned-item references (1-based) back to real closet rows
    closet_pairings: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for p in data.get("closet_pairings", []) or []:
        try:
            idx = int(p.get("item_number", 0)) - 1
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(inventory):
            continue
        row = inventory[idx]
        row_id = str(row.get("id", ""))
        if not row_id or row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        closet_pairings.append({
            "id": row_id,
            "name": row.get("name", ""),
            "category": row.get("category", ""),
            "image_url": row.get("processed_image_url") or row.get("image_url"),
            "role": str(p.get("role", "")),
            "reason": str(p.get("reason", "")),
        })

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
        "closet_pairings": closet_pairings,
        "outfit_potential": data.get("outfit_potential", "medium"),
        "styling_tip": data.get("styling_tip", ""),
        "suggestions": data.get("suggestions", []),
        "grounded_in_knowledge": bool(knowledge_text),
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
