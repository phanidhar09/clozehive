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

from app.api.v1.intelligence.services import ai_service
from app.api.v1.intelligence.services.fashion_rag_service import get_fashion_context_for_prompt
from app.api.v1.wardrobe.services.vision_service import analyze_for_bulk
from app.core import outfit_compatibility as compat
from app.core.embedding_service import (
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
    vector_literal,
)
from app.core.logging import get_logger

logger = get_logger("shopping_check_service")

# ── Scoring weights ──────────────────────────────────────────────────────────
_DUPLICATE_THRESHOLD = 0.88  # cosine sim — item is "essentially the same" (dupe-check only)

# Steers vision when the input is a rendered product-PAGE screenshot (the fallback
# for bot-blocked retailers) rather than a clean garment photo. Without this the
# model labels the whole page "other" and compatibility finds nothing to pair.
_SCREENSHOT_VISION_HINT = (
    "IMPORTANT CONTEXT: This image is a SCREENSHOT of an online clothing-store "
    "product page — not a clean studio photo. It may include site navigation, "
    "buttons, price text, thumbnails of other products, and a model wearing "
    "several garments. Identify the SINGLE main product this page is selling "
    "(usually the largest central garment, matching the page title). Describe "
    "ONLY that item. Ignore site chrome, navigation, related-product thumbnails, "
    "and any secondary garments the model also wears. Always assign a concrete "
    "category (tops, bottoms, shoes, outerwear, dresses, accessories) — never "
    "'other' — by inferring the main product's type."
)

# Percentage-weighted scoring: each factor weight is the % it can contribute, and
# the weights SUM TO 100. buy_score = Σ(weight × factor_subscore) where each
# subscore is 0–1, so the result is a true 0–100% with no clamping needed.
_WEIGHTS: dict[str, float] = {
    "uniqueness": 30.0,  # not a near-duplicate of something already owned
    "compatibility": 35.0,  # genuinely *pairs* with items already in the closet
    "gap_fill": 15.0,  # fills a detected category gap
    "occasion_new": 12.0,  # adds new occasion coverage
    "season_new": 8.0,  # adds new season coverage
}
assert round(sum(_WEIGHTS.values())) == 100, "buy_score weights must sum to 100%"
_COMPAT_SATURATION = 4  # this many genuine pairings = full compatibility credit
# Embedding-similarity cutoff for the dupe-check (a near-identical item). This is
# ONLY used for "do you already own this" — never for "does this match".
_DUPE_FETCH_LIMIT = 12
# Cap how many closet items we role-score for compatibility (closets are small).
_COMPAT_CLOSET_LIMIT = 200


# ── Instrumentation ───────────────────────────────────────────────────────────

# The Shop with FANI funnel. Logged from line one so repeat-paste (retention) and
# act-on-verdict (intent) are measurable from the first user.
SHOPPING_EVENT_TYPES = frozenset(
    {
        "check_created",  # a verdict was produced (photo or URL)
        "verdict_viewed",  # user actually saw the result card
        "outfit_opened",  # user expanded the matched/pairing items
        "verdict_acted",  # user recorded a buy/skip decision
        "added_to_closet",  # user saved the item
        "paste_again",  # user started another check from the result
    }
)


async def record_shopping_event(
    session: AsyncSession,
    user_id: str,
    event_type: str,
    check_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Best-effort funnel event write. Never raises into the caller — analytics
    must not break a verdict. Returns True if a row was written."""
    if event_type not in SHOPPING_EVENT_TYPES:
        logger.warning("shopping_event_unknown_type", event_type=event_type)
        return False
    import json as _json

    try:
        await session.execute(
            text("""
                INSERT INTO shopping_events (id, user_id, check_id, event_type, metadata, created_at)
                VALUES (gen_random_uuid(), CAST(:uid AS uuid),
                        CAST(:cid AS uuid), :etype, CAST(:meta AS jsonb), NOW())
            """),
            {
                "uid": user_id,
                "cid": check_id,
                "etype": event_type,
                "meta": _json.dumps(metadata) if metadata is not None else None,
            },
        )
        await session.commit()
        return True
    except Exception as exc:  # noqa: BLE001 — instrumentation is never load-bearing
        logger.warning("shopping_event_write_failed", event_type=event_type, error=str(exc))
        return False


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_item_text(analysis: dict[str, Any]) -> str:
    """
    Convert vision analysis payload into embedding text.
    Pass both alias variants so item_to_embedding_text resolves whichever is populated.
    """
    return item_to_embedding_text(
        {
            # Both naming conventions kept — _resolve() picks the first non-empty one
            "name": analysis.get("name", ""),
            "category": analysis.get("category", ""),
            "subcategory": analysis.get("subcategory", ""),
            "color": analysis.get("color", ""),
            "primary_color": analysis.get("primary_color", ""),
            "fabric": analysis.get("fabric", ""),
            "material": analysis.get("material", ""),
            "pattern": analysis.get("pattern", ""),
            "fit": analysis.get("fit", ""),
            "season": analysis.get("season") or [],
            "season_tags": analysis.get("season_tags") or [],
            "occasion": analysis.get("occasion") or [],
            "occasion_tags": analysis.get("occasion_tags") or [],
            "tags": analysis.get("tags") or [],
            "style_tags": analysis.get("style_tags") or [],
            "notes": analysis.get("notes", ""),
            "description": analysis.get("description", ""),
            "brand": analysis.get("brand", ""),
            "secondary_colors": analysis.get("secondary_colors") or [],
        }
    )


async def _fetch_existing_occasions_seasons(session: AsyncSession, user_id: str) -> tuple[set[str], set[str]]:
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
        for occ in row["occasion"] or []:
            occasions.add(occ.lower())
        for s in row["season"] or []:
            seasons.add(s.lower())
    return occasions, seasons


async def _has_open_gap_for_category(session: AsyncSession, user_id: str, category: str) -> bool:
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


async def _fetch_closet_for_compat(session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
    """Fetch the user's available closet items with the attributes compatibility
    scoring needs. Unlike the embedding search, this returns the WHOLE closet
    (capped) so role-complementary items — the things the pasted item pairs with,
    which embedding similarity never surfaces — are actually considered.

    Only AVAILABLE items are styled (in-laundry / at-cleaners / lent-out excluded),
    matching the rest of the styling pipeline.
    """
    sql = text("""
        SELECT id, name, category, color, fabric, pattern, season, occasion,
               image_url, processed_image_url, wear_count
        FROM closet_items
        WHERE user_id = CAST(:uid AS uuid)
          AND is_archived = false
          AND COALESCE(availability, 'available') = 'available'
        ORDER BY wear_count DESC NULLS LAST, created_at DESC
        LIMIT :lim
    """)
    result = await session.execute(sql, {"uid": user_id, "lim": _COMPAT_CLOSET_LIMIT})
    return [dict(r) for r in result.mappings().all()]


# ── Core analysis ─────────────────────────────────────────────────────────────


async def analyze_shopping_item(
    image_bytes: bytes,
    media_type: str,
    user_id: str,
    session: AsyncSession,
    image_url: str | None = None,
    *,
    input_type: str = "photo",
    source_url: str | None = None,
    product_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Analyse a shopping item photo against the user's closet and return a
    buy recommendation with percentage score.

    ``input_type`` records how the image was sourced ("photo" upload, "url"
    product image, or "screenshot" page render). ``product_meta`` carries the
    OG/JSON-LD fields pulled from a pasted product URL — used both to enrich the
    vision analysis (brand/name the photo can't reveal) and for attribution.
    """
    # 1. Vision analysis. A page screenshot needs extra steering — it contains
    #    site chrome, price text, and thumbnails of other products, so the model
    #    must pick the single main garment instead of assuming one clean photo.
    extra_instruction: str | None = None
    if input_type == "screenshot":
        extra_instruction = _SCREENSHOT_VISION_HINT
        name_hint = (product_meta or {}).get("title")
        if name_hint:
            extra_instruction += (
                f"\n\nThe page title/URL indicates the product is: \"{name_hint}\". "
                "Identify and describe THAT garment specifically."
            )
    analysis = await analyze_for_bulk(image_bytes, media_type, extra_instruction=extra_instruction)

    # 1b. Enrich with product-page metadata the image alone can't reveal (brand,
    #     marketed name, price) and keep the source for attribution in the UI.
    if product_meta:
        if product_meta.get("brand") and not analysis.get("brand"):
            analysis["brand"] = product_meta["brand"]
        if product_meta.get("title") and not analysis.get("name"):
            analysis["name"] = product_meta["title"]
        analysis["source_url"] = source_url or product_meta.get("source_url")
        analysis["source_title"] = product_meta.get("title")
        analysis["source_brand"] = product_meta.get("brand")
        analysis["source_price"] = product_meta.get("price")
        analysis["source_site"] = product_meta.get("site_name")

    item_text = _build_item_text(analysis)
    category = analysis.get("category", "").lower()

    # 2. Embed the new item — used ONLY for the dupe-check ("do you own this").
    embedding = await generate_text_embedding(item_text)

    # 3a. DUPE-CHECK (embedding similarity). High cosine similarity = a near-
    #     identical garment (another navy blazer). This is the honesty signal,
    #     deliberately kept apart from compatibility.
    dupe_candidates: list[dict[str, Any]] = []
    if embedding:
        dupe_candidates = await pgvector_cosine_search(
            session=session,
            table="closet_items",
            embedding=embedding,
            user_id=user_id,
            limit=_DUPE_FETCH_LIMIT,
            threshold=_DUPLICATE_THRESHOLD,
            filter_archived=True,
        )
    dupe_items = [it for it in dupe_candidates if float(it.get("similarity_score", 0)) >= _DUPLICATE_THRESHOLD]
    has_duplicate = bool(dupe_items)
    dupe_ids = {str(it.get("id", "")) for it in dupe_items}

    # 3b. COMPATIBILITY (does this *go with* what I own). Score the pasted item
    #     against role-complementary closet items — the matches embedding search
    #     can never surface. A blazer is scored against bottoms/shoes/layers,
    #     not against other blazers.
    closet = await _fetch_closet_for_compat(session, user_id)
    pairings: list[dict[str, Any]] = []
    for owned in closet:
        if str(owned.get("id", "")) in dupe_ids:
            continue  # a duplicate isn't a "pairing"
        result = compat.score_compatibility(analysis, owned)
        if result["pairs"]:
            pairings.append(
                {
                    "id": str(owned.get("id", "")),
                    "name": owned.get("name", ""),
                    "category": owned.get("category", ""),
                    "color": owned.get("color", ""),
                    "image_url": owned.get("processed_image_url") or owned.get("image_url"),
                    "similarity_score": result["score"],  # compatibility, not embedding
                    "is_duplicate": False,
                    "compat_reasons": result["reasons"],
                }
            )
    pairings.sort(key=lambda p: p["similarity_score"], reverse=True)
    compatible_count = len(pairings)

    # 4. Existing coverage
    owned_occasions, owned_seasons = await _fetch_existing_occasions_seasons(session, user_id)

    # 5. Compute percentage-weighted score — each factor yields a 0–1 subscore,
    #    contributes (weight × subscore) %, and all weights sum to 100.
    reasons: list[str] = []

    item_occasions = {o.lower() for o in (analysis.get("occasion_tags") or [])}
    new_occasions = item_occasions - owned_occasions
    item_seasons = {s.lower() for s in (analysis.get("season_tags") or [])}
    new_seasons = item_seasons - owned_seasons
    fills_gap = bool(category and await _has_open_gap_for_category(session, user_id, category))

    # Factor subscores (0–1)
    subscores: dict[str, float] = {
        "uniqueness": 0.0 if has_duplicate else 1.0,
        "compatibility": min(compatible_count / _COMPAT_SATURATION, 1.0),
        "gap_fill": 1.0 if fills_gap else 0.0,
        # Novelty only counts when the item isn't a duplicate.
        "occasion_new": 1.0 if (new_occasions and not has_duplicate) else 0.0,
        "season_new": 1.0 if (new_seasons and not has_duplicate) else 0.0,
    }

    # Weighted percentage contributions (sum to ≤ 100).
    score_breakdown = {k: round(_WEIGHTS[k] * subscores[k], 1) for k in _WEIGHTS}
    score = round(sum(score_breakdown.values()))
    score = max(0, min(100, score))

    # Human-readable reasons mirror the factors that contributed.
    if has_duplicate:
        reasons.append(f"You already own {len(dupe_items)} very similar item(s).")
    if pairings:
        sample = ", ".join(p["name"] for p in pairings[:3] if p["name"])
        tail = f" (e.g. {sample})" if sample else ""
        reasons.append(f"Pairs with {compatible_count} item(s) you already own{tail}.")
    else:
        reasons.append("Doesn't clearly pair with anything in your closet yet.")
    if fills_gap:
        reasons.append(f"Fills a detected gap in your {category} collection.")
    if subscores["occasion_new"]:
        reasons.append(f"Adds new occasion coverage: {', '.join(new_occasions)}.")
    if subscores["season_new"]:
        reasons.append(f"Extends your wardrobe into: {', '.join(new_seasons)}.")

    # 6. Recommendation label — Worth it vs Skip, with a middle "consider" band.
    if score >= 70:
        recommendation = "buy"
    elif score >= 45:
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

    # 8. Matched items shown in the UI: duplicates first (the honest warning),
    #    then the best genuine pairings. Both carry is_duplicate so the frontend
    #    renders "you own this" vs "pairs with this" distinctly.
    matched_summary: list[dict[str, Any]] = []
    for it in dupe_items[:5]:
        matched_summary.append(
            {
                "id": str(it.get("id", "")),
                "name": it.get("name", ""),
                "category": it.get("category", ""),
                "color": it.get("color", ""),
                "image_url": it.get("processed_image_url") or it.get("image_url"),
                "similarity_score": round(float(it.get("similarity_score", 0)), 3),
                "is_duplicate": True,
            }
        )
    matched_summary.extend(pairings[:6])

    # 8b. Honest one-liners surfaced in the UI.
    #     "completes N outfits" = distinct COMPLETE looks this unlocks from owned
    #     items (the real buy-signal), not just the count of items it pairs with.
    from app.core import outfit_builder

    dupe_count = len(dupe_items)
    completes_outfits, _capped = outfit_builder.count_completable_outfits(analysis, closet)

    # 9. Persist to DB
    record_id = str(uuid.uuid4())
    reasoning_text = " ".join(reasons) if reasons else "No specific matches found in your closet."

    sql = text("""
        INSERT INTO shopping_checks
            (id, user_id, image_url, item_analysis, matched_items,
             buy_score, buy_recommendation, closet_boost_pct, reasoning,
             input_type, source_url, created_at)
        VALUES
            (CAST(:id AS uuid), CAST(:uid AS uuid), :image_url,
             CAST(:analysis AS jsonb), CAST(:matched AS jsonb),
             :score, :rec, :boost, :reason,
             :input_type, :source_url, NOW())
    """)
    import json

    await session.execute(
        sql,
        {
            "id": record_id,
            "uid": user_id,
            "image_url": image_url,
            "analysis": json.dumps(analysis),
            "matched": json.dumps(matched_summary),
            "score": round(score, 1),
            "rec": recommendation,
            "boost": round(boost_pct, 1),
            "reason": reasoning_text,
            "input_type": input_type,
            "source_url": source_url,
        },
    )
    await session.commit()

    # Instrument repeat link-paste behaviour: the retention/viral signal. Cheap
    # count of how many URL/screenshot checks this user has now run.
    url_check_count = await _count_url_checks(session, user_id) if input_type != "photo" else 0

    # Funnel: a verdict was produced. Records the shape of the result so we can
    # later correlate "what kind of verdict" with "did they act / paste again".
    await record_shopping_event(
        session,
        user_id,
        "check_created",
        check_id=record_id,
        metadata={
            "input_type": input_type,
            "recommendation": recommendation,
            "buy_score": round(score, 1),
            "dupe_count": dupe_count,
            "completes_outfits": completes_outfits,
            "has_source_url": bool(source_url),
        },
    )

    return {
        "check_id": record_id,
        "item_analysis": analysis,
        "matched_items": matched_summary,
        "buy_score": round(score, 1),
        "buy_recommendation": recommendation,
        "closet_boost_pct": round(boost_pct, 1),
        "score_breakdown": score_breakdown,
        "reasoning": reasoning_text,
        "image_url": image_url,
        "input_type": input_type,
        "source_url": source_url,
        "source_title": (product_meta or {}).get("title"),
        "source_brand": (product_meta or {}).get("brand"),
        "source_price": (product_meta or {}).get("price"),
        "source_site": (product_meta or {}).get("site_name"),
        "dupe_count": dupe_count,
        "completes_outfits": completes_outfits,
        "url_check_count": url_check_count,
    }


async def _count_url_checks(session: AsyncSession, user_id: str) -> int:
    """How many URL/screenshot-sourced checks this user has run (incl. the latest)."""
    sql = text("""
        SELECT COUNT(*) AS n FROM shopping_checks
        WHERE user_id = CAST(:uid AS uuid)
          AND input_type IN ('url', 'screenshot')
    """)
    result = await session.execute(sql, {"uid": user_id})
    row = result.mappings().first()
    return int(row["n"]) if row else 0


async def analyze_shopping_item_from_url(
    url: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Run the FANI buy/skip verdict against a pasted product URL.

    Pulls the product image from OG/JSON-LD metadata; if the page exposes none,
    falls back to a rendered screenshot (when a screenshot service is configured)
    and runs the same vision pipeline. No scraper infrastructure — one page fetch.
    """
    from app.core import product_url as product_url_mod
    from app.core.exceptions import BadRequestError
    from app.core.upload_service import persist_upload

    # 1. Try to read the page's OG/JSON-LD metadata. Big retailers (Abercrombie,
    #    Nike, Zara…) sit behind Akamai/Cloudflare bot managers that 403 any
    #    server-side fetch — that's expected, not a hard failure. We remember the
    #    page was blocked and degrade to the screenshot renderer below.
    meta: product_url_mod.ProductMetadata | None = None
    page_blocked = False
    try:
        meta = await product_url_mod.fetch_product_metadata(url)
    except BadRequestError as exc:
        # Re-raise true user errors (bad scheme, SSRF, malformed URL) immediately;
        # only "couldn't open / reach" failures are eligible for the screenshot path.
        msg = str(exc).lower()
        if "private" in msg or "http(s)" in msg or "valid url" in msg or "redirect" in msg:
            raise
        page_blocked = True
        logger.info("shopping_url_page_blocked", url=url[:120], detail=str(exc))

    source_url = meta.source_url if meta else url.strip()

    # 2. Prefer the author-curated product image when we could read the page.
    image: tuple[bytes, str] | None = None
    input_type = "url"
    if meta and meta.image_url:
        image = await product_url_mod.fetch_image_bytes(meta.image_url)

    # 3. Fall back to a rendered page screenshot through the same vision pipeline.
    #    This uses a real-browser render service (config:
    #    PRODUCT_SCREENSHOT_URL_TEMPLATE) which also gets past bot managers.
    if image is None:
        image = await product_url_mod.fetch_page_screenshot(source_url)
        if image is not None:
            input_type = "screenshot"

    if image is None:
        if page_blocked:
            raise BadRequestError(
                "That store blocks automated readers, so FANI couldn't open the "
                "page. Screenshot a photo of the item and upload it instead."
            )
        raise BadRequestError(
            "Couldn't pull a product image from that link. Try a direct product "
            "page, or snap a photo instead."
        )

    image_bytes, media_type = image

    # Persist the sourced image (best-effort — verdict still runs if storage fails).
    image_url: str | None = None
    try:
        image_url = await persist_upload(image_bytes, media_type, None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("shopping_url_image_persist_failed", error=str(exc))

    # Carry a product-name hint (page title, else the URL slug) — this is what
    # lets vision pick the RIGHT garment out of a fully-styled product-page
    # screenshot instead of grabbing whichever item the model also wears.
    product_meta = meta.to_dict() if meta else {"source_url": source_url}
    if not product_meta.get("title"):
        product_meta["title"] = product_url_mod.product_name_hint_from_url(source_url)

    return await analyze_shopping_item(
        image_bytes=image_bytes,
        media_type=media_type,
        user_id=user_id,
        session=session,
        image_url=image_url,
        input_type=input_type,
        source_url=source_url,
        product_meta=product_meta,
    )


def _outfit_note(anchor_name: str, items: list[dict[str, Any]], forgotten_ids: set[str], tier: str) -> str:
    """A short, deterministic stylist one-liner for a built outfit."""
    names = ", ".join(it["name"] for it in items if it.get("name"))
    anchor = anchor_name or "this piece"
    note = f"{tier} look — styles {anchor} with {names}." if names else f"{tier} look around {anchor}."
    forgotten = next((it["name"] for it in items if str(it.get("id", "")) in forgotten_ids and it.get("name")), None)
    if forgotten:
        note += f" Brings back your {forgotten} you haven't worn yet."
    return note


async def build_outfits_for_check(
    check_id: str,
    user_id: str,
    session: AsyncSession,
) -> dict[str, Any] | None:
    """Ask 2 — anchored outfit completion. Treat the checked item as the anchor and
    return the best complete outfits buildable from the user's own closet."""
    from app.core import outfit_builder

    fetch_sql = text("""
        SELECT id, image_url, item_analysis FROM shopping_checks
        WHERE id = CAST(:cid AS uuid) AND user_id = CAST(:uid AS uuid)
    """)
    res = await session.execute(fetch_sql, {"cid": check_id, "uid": user_id})
    row = res.mappings().first()
    if not row:
        return None

    import json as _json

    analysis = row["item_analysis"]
    if isinstance(analysis, str):
        analysis = _json.loads(analysis)

    closet = await _fetch_closet_for_compat(session, user_id)
    built = outfit_builder.build_outfits(analysis, closet)

    # Attach a stylist note to each outfit.
    for outfit in built["outfits"]:
        outfit["note"] = _outfit_note(
            analysis.get("name", ""),
            outfit["items"],
            set(outfit.get("forgotten_item_ids") or []),
            outfit["tier"],
        )

    # Ask 3: the buy-signal + actionable gap completers.
    completes_outfits, _capped = outfit_builder.count_completable_outfits(analysis, closet)
    gap_suggestions = outfit_builder.suggest_for_gaps(analysis, built["missing_roles"], closet)

    await record_shopping_event(
        session, user_id, "outfit_opened", check_id=check_id,
        metadata={
            "outfit_count": len(built["outfits"]),
            "completes_outfits": completes_outfits,
            "missing_roles": built["missing_roles"],
        },
    )

    return {
        "anchor": {
            "name": analysis.get("name", ""),
            "category": analysis.get("category", ""),
            "color": analysis.get("primary_color") or analysis.get("color", ""),
            "image_url": row.get("image_url"),
        },
        "outfits": built["outfits"],
        "missing_roles": built["missing_roles"],
        "completes_outfits": completes_outfits,
        "gap_suggestions": gap_suggestions,
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
    result = await session.execute(
        sql,
        {
            "bought": bought,
            "cid": check_id,
            "uid": user_id,
        },
    )
    row = result.mappings().first()
    if not row:
        return None
    await session.commit()
    await record_shopping_event(
        session, user_id, "verdict_acted", check_id=check_id, metadata={"bought": bought}
    )
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
               input_type, source_url,
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
        f"{item.get('name', 'Item')}: {item.get('category', '')}, {item.get('color', '')} "
        f"{item.get('fabric', '')} {item.get('pattern', '')}. "
        f"Occasions: {', '.join(item.get('occasion') or [])}. "
        f"Seasons: {', '.join(item.get('season') or [])}."
    )
    if inventory:
        inv_lines = "\n".join(
            f"[{i + 1}] {r.get('name', '')} — {r.get('category', '')}"
            f"{', ' + str(r['color']) if r.get('color') else ''}"
            f"{' (' + ', '.join(r.get('occasion') or []) + ')' if r.get('occasion') else ''}"
            for i, r in enumerate(inventory)
        )
    else:
        inv_lines = "(the closet is otherwise empty)"

    # RAG: ground the styling reasoning in retrieved fashion knowledge (color theory,
    # pairing rules, occasion guidance). Degrades to "" if unavailable.
    knowledge_text = ""
    try:
        rag_query = (
            f"How to complete an outfit around a {item.get('color', '')} "
            f"{item.get('category', '')}; what pieces pair well for "
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
        closet_pairings.append(
            {
                "id": row_id,
                "name": row.get("name", ""),
                "category": row.get("category", ""),
                "image_url": row.get("processed_image_url") or row.get("image_url"),
                "role": str(p.get("role", "")),
                "reason": str(p.get("reason", "")),
            }
        )

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
    item_text = item_to_embedding_text(
        {
            "name": analysis.get("name", ""),
            "category": analysis.get("category", ""),
            "color": analysis.get("primary_color") or analysis.get("color", ""),
            "fabric": analysis.get("material", ""),
            "pattern": analysis.get("pattern", ""),
            "season": analysis.get("season_tags") or [],
            "occasion": analysis.get("occasion_tags") or [],
            "tags": analysis.get("style_tags") or [],
            "notes": analysis.get("description", ""),
            "brand": analysis.get("brand", ""),
        }
    )
    embedding = await generate_text_embedding(item_text)
    emb_literal = vector_literal(embedding) if embedding else None

    new_id = str(uuid.uuid4())
    insert_sql = text(
        """
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
        )
    )

    import json

    result = await session.execute(
        insert_sql,
        {
            "id": new_id,
            "uid": user_id,
            "name": analysis.get("name") or analysis.get("category") or "Shopping Item",
            "category": analysis.get("category", ""),
            "color": analysis.get("primary_color") or analysis.get("color", ""),
            "fabric": analysis.get("material", ""),
            "pattern": analysis.get("pattern", ""),
            "brand": analysis.get("brand", ""),
            "season": json.dumps(analysis.get("season_tags") or []),
            "occasion": json.dumps(analysis.get("occasion_tags") or []),
            "tags": json.dumps(analysis.get("style_tags") or []),
            "notes": analysis.get("description", ""),
            "image_url": row.get("image_url"),
        },
    )
    await session.commit()
    await record_shopping_event(
        session, user_id, "added_to_closet", check_id=check_id,
        metadata={"closet_item_id": new_id},
    )
    created = result.mappings().first()
    return dict(created) if created else {"id": new_id}
