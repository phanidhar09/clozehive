"""CLOZEHIVE AI Stylist Chat Service.

Orchestrates the full pipeline for a single chat turn:
  1. Embed the user message → pgvector search closet_items for top-K relevant items
  2. RAG-retrieve fashion knowledge and similar past outfits in parallel
  3. Load user profile + weather concurrently
  4. Build a grounded system prompt (only real, relevant closet items)
  5. Ask the LLM to return structured JSON
  6. Validate item IDs belong to the requesting user
  7. Return a rich structured response

The AI never invents closet items. If the wardrobe is insufficient, it calls out
purchase gaps explicitly instead of hallucinating items.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity.repositories.user_repo import UserRepository
from app.api.v1.identity.services.style_profile_context import load_merged_user_profile_for_ai
from app.api.v1.intelligence.services import ai_service, model_router, trend_grounding
from app.api.v1.intelligence.services.fashion_rag_service import get_fashion_context_for_prompt
from app.api.v1.intelligence.services.fashion_rules import build_fashion_rules_prompt_block
from app.api.v1.intelligence.services.model_router import RouteSignals
from app.api.v1.travel.services import weather_service
from app.api.v1.wardrobe.services.outfit_history_service import get_outfit_history_for_prompt
from app.core.ai_output_validator import (
    check_context_sufficiency,
    score_response_quality,
    validate_chat_response,
)
from app.core.analytics import LLMTelemetry
from app.core.embedding_service import (
    generate_text_embedding,
    pgvector_cosine_search,
)
from app.core.llm_safety import (
    sanitize_user_text,
)
from app.core.logging import get_logger
from app.models.ai_chat import AIChatSession
from app.models.closet import ClosetItem
from app.rag.query_builder import build_closet_rag_query

logger = get_logger("ai_stylist_chat_service")

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
You are FANI — ClozeHive's personal AI stylist (Fashion Analysis and Nurturing Intelligence). \
You are warm, encouraging, and specific. You handle ALL fashion and styling questions — not just outfit building.

CAPABILITIES:
• Recommend outfits built exclusively from the user's wardrobe (WARDROBE CONTEXT below)
• Answer general fashion/styling questions (color theory, trends, rules, care tips, etc.)
• Critique and improve existing outfits — suggest specific closet items to swap or add
• Identify wardrobe gaps and what to buy next
• Give styling tips for specific body types, occasions, or moods
• Help the user understand their own style identity

PERSONAL PROFILE MANDATE — Apply to EVERY response and EVERY outfit/analysis without exception. \
The four pillars below MUST be considered each time you recommend, critique, or analyse anything: \
(A) the user's stated preferences, (B) their body size, (C) their skin tone & undertone, and (D) their body fit. \
If a pillar's data is missing, apply general best practice for it — never ignore it:
1. Gender / style identity: Tailor every recommendation to the user's stated gender identity. Use gender-appropriate styling language and silhouette guidance (e.g. "a relaxed masculine fit", "a feminine A-line silhouette", "a gender-neutral oversized look").
2. Body type + fit preferences (PILLAR B + D): Choose items that suit the stated body type(s), body size, and fit preferences. Silently favour cuts that flatter their build and size; briefly note if a closet item is a less ideal fit for their proportions.
3. Height & body size: Factor proportions into every recommendation. Cropped tops + high-waist bottoms elongate petite frames; wide-leg trousers and longline coats complement taller builds. Respect the user's size profile so suggested layering and silhouettes are realistic for their build.
4. Skin tone & undertone (PILLAR C — apply to all colour choices): Recommend colours that flatter the user's skin tone and undertone. Warm undertones → earthy, golden, warm reds, olive, cream. Cool undertones → jewel tones, blues, emerald, true white, cool greys. Neutral undertones → most colours work; use contrast to guide. Deep skin tones carry vivid saturated colours beautifully; fair skin tones often suit softer or higher-contrast palettes. When the wardrobe offers a choice, prefer the colour that best complements their skin tone. Briefly explain the skin-tone rationale in "reasoning".
5. Favorite colors: Lead with these whenever available in the wardrobe AND they suit the skin tone. When two equally good items exist, prefer the one in a favourite colour.
6. Avoided colors: NEVER include items in avoided colors unless the user explicitly requests it in this message.
7. Style preferences / archetype (PILLAR A): Stay on-brand. Streetwear user → avoid purely formal combos. Classic/minimalist → avoid loud prints. Bohemian → lean into layering and texture.
8. Occasion coverage (CRITICAL): When the user does NOT name a specific occasion (e.g. "what should I wear?", "build me outfits", "dress me for the week"), return ONE outfit card per occasion from the user's occasion_preferences list (max 4). Title each card clearly: "Casual Day Look", "Work Meeting Outfit", "Date Night Pick", "Weekend Brunch". If occasion_preferences is empty, default to: casual, work, and evening.
9. Age range: Adapt style guidance to be age-appropriate while respecting personal taste.
10. Climate preferences: Note suitability for the user's typical climate when recommending layers or fabrics.
11. Never ask the user to complete their profile mid-chat. Apply what is known silently. Only ask for specific missing context (e.g. destination city, event date) when it is essential to the request.

STRICT RULES FOR OUTFIT RECOMMENDATIONS:
1. Outfit items MUST come exclusively from [WARDROBE CONTEXT]. NEVER invent items.
2. Always use the exact item id and name from the wardrobe list.
3. matching_score must equal color + occasion + fit + style + weather + preference (max 100).
4. For every outfit, explain WHY it works in "reasoning" — reference the user's body type, colors, and style preferences where relevant.
5. List 1–3 actionable "improvement_tips" — reference specific closet items where possible.
6. List "fashion_rules_used" as short strings (e.g. "color harmony", "60-30-10 rule").
7. If wardrobe has <3 suitable items, fill "purchase_gaps" with what is missing.
8. SILHOUETTE / PROPORTION (use each item's fit= field): balance volume with fit. Pair a relaxed/oversized piece with a slim/fitted one (e.g. an oversized top over slim jeans is a classic balanced look). AVOID pairing a relaxed/oversized top WITH a baggy/wide bottom — volume-on-volume reads shapeless. Head-to-toe slim is clean but can read severe; vary it when you can. When fit= is "?" (unknown), don't assume — judge proportion from the item name/category instead.
9. WOMEN / FEMININE SILHOUETTES (apply when the user's gender is female or they want a feminine look): the organising principle is WAIST DEFINITION, not just volume balance. A marked waist — a tuck/half-tuck, a belt, a high-rise bottom, or a fit-and-flare cut — is what makes a look read as intentional rather than frumpy. Canonical balanced pairings: a fitted or tucked top with an A-line, full, pleated, or wide/flowy skirt; a fitted bodice with a flared bottom; high-rise bottoms to elongate the legs. IMPORTANT NUANCE: volume-on-volume CAN work for women when the waist is defined (e.g. an oversized knit belted over a full midi skirt, or a billowy blouse tucked into wide-leg trousers) — do NOT reject it outright if a belt or tuck marks the waist; suggest the belt/tuck instead. DRESSES (onepiece): pair a fitted/bodycon dress with a structured or cropped layer; pair a flowy/voluminous dress with a fitted layer or a belt to define the waist. When recommending, name the waist-defining move (e.g. "tuck the front", "add a thin belt") in the reasoning.

STYLING SUGGESTIONS:
• When asked to improve styling or "how can I look better", provide "styling_suggestions" — an array of specific, actionable tips.
• Each suggestion should reference real items from the wardrobe when possible (use their exact names).
• Suggestions can cover: adding accessories, trying different color combos, re-purposing items, layering ideas.
• Always factor in the user's body type, fit preferences, and avoided colors.

WHEN TO RETURN OUTFIT CARDS (important):
• ANY question that mentions wearing something, getting dressed, an outfit, an occasion, or "what should I wear" MUST return at least one outfit in "recommended_outfits".
• When no specific occasion is mentioned, cover ALL occasions from the user's profile (see rule 7 above) — do not default to casual only.
• Even vague requests like "dress me", "outfit today", "I have a date" — build an outfit from the wardrobe.
• Only skip "recommended_outfits" (leave []) for purely theoretical questions: color theory, care instructions, trend news — where no specific outfit is being built.
• When in doubt, include outfit cards. Users came here to see outfits, not just read text.

RESPONSE SCHEMA — always return valid JSON, no markdown fences, no prose outside JSON:
{{
  "reply": "Conversational response (1-4 sentences). For general questions this is the main answer.",
  "recommended_outfits": [
    {{
      "title": "Smart Dinner Look",
      "items": [
        {{"id": "<uuid>", "name": "...", "category": "...", "color": "...", "image_url": null}}
      ],
      "matching_score": 88,
      "score_breakdown": {{"color": 22, "occasion": 23, "fit": 18, "style": 12, "weather": 9, "preference": 4}},
      "reasoning": "One paragraph explaining why this outfit works.",
      "fashion_rules_used": ["color harmony", "occasion match"],
      "improvement_tips": ["Swap X for Y to elevate the look.", "Add your navy blazer for a polished finish."]
    }}
  ],
  "styling_suggestions": [
    {{
      "tip": "Short actionable tip (1-2 sentences)",
      "closet_item_name": "Exact item name from wardrobe if relevant, or null",
      "closet_item_id": "Item UUID if relevant, or null",
      "category": "One of: color | layering | accessories | fit | occasion | general"
    }}
  ],
  "purchase_gaps": [
    {{"category": "shoes", "reason": "No formal footwear in wardrobe for dinner."}}
  ],
  "follow_up_questions": [
    "Would you like a more casual alternative?",
    "Should I factor in the weather forecast?",
    "Want me to suggest what to buy next?"
  ]
}}

{wardrobe_block}
{profile_block}
{weather_block}
{feedback_block}
{fashion_rules_block}
{knowledge_block}
"""

# Number of closet items retrieved via vector search
_RAG_CLOSET_LIMIT = 25
# Fallback: max items loaded when no embeddings exist
_FALLBACK_CLOSET_LIMIT = 80
# Similarity threshold for closet RAG retrieval.
# 0.45 keeps results focused — lower brings in items with only marginal semantic
# overlap to the query, which adds noise without improving outfit quality.
_RAG_CLOSET_THRESHOLD = 0.45
# Max tokens for the outfit-generation LLM call (wardrobe + profile context can be large)
_CHAT_MAX_TOKENS = 4096


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].removeprefix("json").strip()
        if "```" in text:
            text = text[: text.index("```")]
    return text.strip()


def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row.get("name") or "",
        "category": row.get("category") or "",
        "color": row.get("color") or "",
        "fabric": row.get("fabric") or "",
        "pattern": row.get("pattern") or "",
        "fit": row.get("fit") or "",
        "season": row.get("season") or [],
        "occasion": row.get("occasion") or [],
        "wear_count": row.get("wear_count") or 0,
        "image_url": (row.get("processed_image_url") or row.get("image_url") or row.get("original_image_url")),
        "tags": row.get("tags") or [],
    }


def _orm_to_item(item: ClosetItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "name": item.name,
        "category": item.category,
        "color": item.color or "",
        "fabric": item.fabric or "",
        "pattern": item.pattern or "",
        "fit": item.fit or "",
        "season": item.season or [],
        "occasion": item.occasion or [],
        "wear_count": item.wear_count,
        "image_url": (item.processed_image_url or item.image_url or item.original_image_url or None),
        "tags": item.tags or [],
    }


async def _rag_load_closet(
    session: AsyncSession,
    user_id: UUID,
    query_embedding: list[float],
    occasion: str | None = None,
) -> list[dict[str, Any]]:
    """Vector-search closet items by semantic similarity to the user's message.

    Uses a tiered fallback strategy:
      1. pgvector cosine search at threshold 0.45 (focused, relevant results).
      2. If that returns fewer than 10 items, broaden to threshold 0.30 so FANI
         always has a reasonable wardrobe to work with.
      3. If no embeddings exist at all, fall back to most-worn items.
    """
    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=query_embedding,
        user_id=str(user_id),
        limit=_RAG_CLOSET_LIMIT,
        threshold=_RAG_CLOSET_THRESHOLD,
        filter_archived=True,
    )

    # Broaden search when too few results — ensures outfit variety
    if len(rows) < 10:
        broader = await pgvector_cosine_search(
            session,
            table="closet_items",
            embedding=query_embedding,
            user_id=str(user_id),
            limit=_RAG_CLOSET_LIMIT,
            threshold=0.30,
            filter_archived=True,
        )
        if len(broader) > len(rows):
            rows = broader
            logger.info("rag_closet_broadened", user_id=str(user_id), count=len(rows))

    if rows:
        items = [_row_to_item(r) for r in rows]
        # Rerank: boost items whose occasion tags match the requested occasion
        if occasion:
            items = _rerank_by_occasion(items, occasion)
        logger.info(
            "rag_closet_retrieved",
            user_id=str(user_id),
            count=len(items),
            top_score=round(float(rows[0].get("similarity_score", 0)), 3),
            occasion=occasion,
        )
        return items

    # Fallback: no embeddings yet — load by wear count
    logger.info("rag_closet_fallback_no_embeddings", user_id=str(user_id))
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(_FALLBACK_CLOSET_LIMIT)
    )
    return [_orm_to_item(item) for item in result.scalars().all()]


def _rerank_by_occasion(items: list[dict[str, Any]], occasion: str) -> list[dict[str, Any]]:
    """Stable-sort: items whose occasion tags match float to the top."""
    occ_lower = occasion.lower()

    def _score(it: dict[str, Any]) -> int:
        tags = it.get("occasion") or []
        if isinstance(tags, list):
            return -int(any(occ_lower in str(t).lower() for t in tags))
        return 0

    return sorted(items, key=_score)


async def _resolve_weather(session: AsyncSession, user_id: UUID, location: str | None) -> dict[str, Any] | None:
    # 1. Use explicitly provided location
    if location:
        try:
            return await weather_service.get_weather_by_city(location)
        except Exception as exc:
            logger.warning("weather_by_location_failed", location=location, error=str(exc))

    # 2. Fall back to user's saved location from profile/permissions
    try:
        user = await UserRepository(session).get(user_id)
        permissions = user.permissions if user else None
        if isinstance(permissions, dict) and permissions.get("location"):
            coords = permissions.get("location_coords")
            label = permissions.get("location_label")
            if isinstance(coords, dict) and coords.get("lat") is not None:
                return await weather_service.get_current_weather(float(coords["lat"]), float(coords["lon"]), label)
            if label:
                return await weather_service.get_weather_by_city(str(label))
    except Exception as exc:
        logger.warning("weather_from_profile_failed", user_id=str(user_id), error=str(exc))

    return None


def _build_wardrobe_block(items: list[dict[str, Any]]) -> str:
    """Build the wardrobe context block.

    All user-provided field values are sanitised before embedding so that a
    malicious item name (e.g. "ignore previous instructions") cannot hijack
    the system prompt.  Item IDs are server-generated UUIDs and trusted.
    """
    if not items:
        return "[WARDROBE CONTEXT]\nNo items in wardrobe yet.\n[END WARDROBE CONTEXT]"
    lines = [f"[WARDROBE CONTEXT] ({len(items)} items)"]
    for it in items:
        occ_raw = it.get("occasion") or []
        occ = (
            sanitize_user_text(
                ", ".join(occ_raw) if isinstance(occ_raw, list) else str(occ_raw),
                field="notes",
                max_len=80,
            )
            or "any"
        )
        season_raw = it.get("season") or []
        season = (
            sanitize_user_text(
                ", ".join(season_raw) if isinstance(season_raw, list) else str(season_raw),
                field="notes",
                max_len=60,
            )
            or "all"
        )
        lines.append(
            f"  id={it['id']} | {sanitize_user_text(it.get('name', ''), field='name')} | "
            f"{sanitize_user_text(it.get('category', ''), field='category')} | "
            f"color={sanitize_user_text(it.get('color') or '?', field='color', max_len=40)} | "
            f"fabric={sanitize_user_text(it.get('fabric') or '?', field='material', max_len=60)} | "
            f"fit={sanitize_user_text(it.get('fit') or '?', field='fit', max_len=30)} | "
            f"occasion={occ} | season={season} | worn={it.get('wear_count', 0)}x"
        )
    lines.append("[END WARDROBE CONTEXT]")
    return "\n".join(lines)


def _build_profile_block(profile: dict[str, Any] | None) -> str:
    if not profile:
        return ""
    ctx = profile.get("style_profile_context_text") or ""
    if not ctx:
        return ""
    return f"\n[USER STYLE PROFILE]\n{ctx}\n[END USER STYLE PROFILE]"


def _build_weather_block(weather: dict[str, Any] | None) -> str:
    if not weather:
        return ""
    label = weather.get("location_label") or "your location"
    return (
        f"\n[CURRENT WEATHER at {label}]\n"
        f"Condition: {weather.get('condition', 'unknown')}\n"
        f"Temperature: {weather.get('temp_c', '?')}°C / {weather.get('temp_f', '?')}°F\n"
        f"Feels like: {weather.get('feels_like_c', '?')}°C\n"
        f"Humidity: {weather.get('humidity', '?')}%\n"
        "[END WEATHER]\n"
        "Factor this weather into all recommendations. Mention weather suitability explicitly."
    )


def _build_feedback_block(feedback_text: str) -> str:
    return feedback_text if feedback_text else ""


def _build_knowledge_block(knowledge_text: str) -> str:
    if not knowledge_text:
        return ""
    return f"\n[FASHION KNOWLEDGE — cite [SOURCE-N] when referencing these rules]\n{knowledge_text}\n[END FASHION KNOWLEDGE]"


async def _fetch_image_lookup(session: AsyncSession, item_ids: set[str]) -> dict[str, str | None]:
    """Query image URLs for a specific set of item IDs in one round-trip.

    This is intentionally separate from the RAG closet load: the RAG window is
    capped at 25 items, but FANI may reference items from earlier conversation
    turns that fell outside the current RAG window.  We always look up images
    directly so we never miss a photo.
    """
    if not item_ids:
        return {}
    uuids = []
    for raw in item_ids:
        try:
            uuids.append(UUID(raw))
        except (ValueError, AttributeError):
            pass
    if not uuids:
        return {}
    rows = await session.execute(
        select(
            ClosetItem.id,
            ClosetItem.processed_image_url,
            ClosetItem.image_url,
            ClosetItem.original_image_url,
        ).where(ClosetItem.id.in_(uuids))
    )
    return {str(row.id): (row.processed_image_url or row.image_url or row.original_image_url) for row in rows}


def _enrich_items_with_images(
    outfits: list[dict[str, Any]],
    image_lookup: dict[str, str | None],
    closet_map: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Stamp image_url onto each outfit item.

    Priority: direct DB image_lookup → closet_map fallback → None.
    The direct lookup covers items from prior conversation turns that may not
    be in the current RAG closet_map window.
    """
    for outfit in outfits:
        enriched = []
        for it in outfit.get("items") or []:
            item_id = it.get("id") or ""
            # Prefer the fresh DB lookup; fall back to the RAG closet_map
            if item_id in image_lookup:
                url = image_lookup[item_id]
            elif closet_map and item_id in closet_map:
                url = (closet_map[item_id] or {}).get("image_url")
            else:
                url = None
            enriched.append({**it, "image_url": url})
        outfit["items"] = enriched
    return outfits


async def _fallback_closet(session: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(_FALLBACK_CLOSET_LIMIT)
    )
    return [_orm_to_item(item) for item in result.scalars().all()]


# ── Public API ────────────────────────────────────────────────────────────────


async def process_chat_message(
    session: AsyncSession,
    user_id: UUID,
    message: str,
    context: dict[str, Any] | None = None,
    chat_history: list[dict[str, str]] | None = None,
    images: list[str] | None = None,
    chat_session: AIChatSession | None = None,
) -> dict[str, Any]:
    """
    Full RAG pipeline for a single AI stylist chat turn.

    Returns a dict matching the API response schema:
    {
        "reply": str,
        "recommended_outfits": [...],
        "purchase_gaps": [...],
        "follow_up_questions": [...]
    }
    """
    import asyncio

    ctx = context or {}
    # None means "no specific occasion requested" — let profile occasion_preferences drive variety.
    # "casual" is only used when the user explicitly passes it.
    occasion: str | None = ctx.get("occasion") or None
    location = ctx.get("location")
    weather_required = ctx.get("weather_required", False)
    mood = ctx.get("mood") or ""

    # ── Step 1: Embed the user message (used for all vector searches) ─────────
    # Do NOT bias the RAG query with "casual" when no occasion was provided —
    # that skews vector search away from formal/workwear items the user may need.
    rag_query = build_closet_rag_query(message, occasion=occasion, mood=mood)
    weather_str = ""
    if location:
        weather_str = location

    query_embedding = await generate_text_embedding(rag_query)

    # ── Step 2: Parallel RAG + profile + weather retrieval ────────────────────
    async def _no_weather() -> None:
        return None

    closet_task = asyncio.create_task(
        _rag_load_closet(session, user_id, query_embedding, occasion=occasion)
        if query_embedding
        else _fallback_closet(session, user_id)
    )
    profile_task = asyncio.create_task(load_merged_user_profile_for_ai(session, user_id, None))
    weather_task = asyncio.create_task(
        _resolve_weather(session, user_id, location) if (weather_required or location) else _no_weather()
    )
    # RAG: similar past outfits via pgvector (uses its own embedding internally)
    feedback_task = asyncio.create_task(
        get_outfit_history_for_prompt(
            session,
            str(user_id),
            occasion=occasion,
            limit=5,
            message=message,
        )
    )
    # RAG: fashion knowledge base
    knowledge_task = asyncio.create_task(
        get_fashion_context_for_prompt(session, rag_query, limit=5, occasion=occasion, weather=weather_str)
    )

    # Live trend grounding — short-circuits to None unless the message has
    # trend intent, so it adds no work to ordinary chat turns (Phase 7).
    trend_task = asyncio.create_task(trend_grounding.get_trend_context(message))

    closet_items, user_profile, weather, feedback_text, knowledge_text, trend_context = await asyncio.gather(
        closet_task,
        profile_task,
        weather_task,
        feedback_task,
        knowledge_task,
        trend_task,
        return_exceptions=True,
    )

    # Gracefully degrade on any failure
    if isinstance(closet_items, Exception):
        logger.warning("closet_rag_failed", error=str(closet_items))
        closet_items = await _fallback_closet(session, user_id)
    if isinstance(user_profile, Exception):
        logger.warning("profile_load_failed", error=str(user_profile))
        user_profile = None
    if isinstance(weather, Exception):
        logger.warning("weather_load_failed", error=str(weather))
        weather = None
    if isinstance(feedback_text, Exception):
        logger.warning("feedback_rag_failed", error=str(feedback_text))
        feedback_text = ""
    if isinstance(knowledge_text, Exception):
        logger.warning("knowledge_rag_failed", error=str(knowledge_text))
        knowledge_text = ""
    if isinstance(trend_context, Exception):
        logger.warning("trend_grounding_failed", error=str(trend_context))
        trend_context = None

    # Build a fast lookup map for post-validation
    # RAG returns top-K — we also need full closet IDs to validate recommendations
    # Load all IDs (no embeddings needed) for the validation set
    all_id_rows = await session.execute(
        select(ClosetItem.id).where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
    )
    valid_ids = {str(r[0]) for r in all_id_rows.all()}

    closet_map = {it["id"]: it for it in closet_items}

    logger.info(
        "rag_context_built",
        user_id=str(user_id),
        rag_items=len(closet_items),
        total_valid_ids=len(valid_ids),
        has_knowledge=bool(knowledge_text),
        has_feedback=bool(feedback_text),
    )

    # ── Context-sufficiency gate ──────────────────────────────────────────────
    # Check before spending tokens on the LLM call
    is_sufficient, insufficiency_reason = check_context_sufficiency(closet_items, [], message)
    if not is_sufficient:
        logger.info("context_insufficient", reason=insufficiency_reason, user_id=str(user_id))
        if not closet_items:
            return _empty_wardrobe_response()

    # ── Step 3: Build fashion rules hint ─────────────────────────────────────
    weather_cond = (weather.get("condition") or "mild") if weather else "mild"
    fashion_rules_block = build_fashion_rules_prompt_block(
        closet_items, occasion or "casual", weather_cond, user_profile
    )

    # ── Step 3b: Conversation summarization (long-chat memory) ───────────────
    summary_block = ""
    history_for_prompt = list(chat_history or [])
    if chat_session is not None and history_for_prompt:
        # Lazy import — avoids a circular dependency with the streaming module.
        from app.api.v1.intelligence.services.ai_stylist_streaming import (
            _build_summary_block,
            summarize_history,
        )

        summary_text, history_for_prompt = await summarize_history(session, chat_session, history_for_prompt)
        summary_block = _build_summary_block(summary_text)

    # ── Step 4: Assemble system prompt ────────────────────────────────────────
    user_images = [img for img in (images or []) if img.startswith("data:image/")][:3]
    image_instruction = (
        "\n[IMAGE ANALYSIS] The user has attached image(s) showing their outfit or clothing. "
        "Carefully analyse the visible items — colours, fit, silhouette, style, and occasion-appropriateness. "
        "Reference specific details you observe in the image when giving feedback. "
        "Cross-reference with their wardrobe to suggest complementary pieces they already own.\n"
        if user_images
        else ""
    )
    system_prompt = (
        _SYSTEM_PROMPT_TEMPLATE.format(
            wardrobe_block=_build_wardrobe_block(closet_items),
            profile_block=_build_profile_block(user_profile),
            weather_block=_build_weather_block(weather),
            feedback_block=_build_feedback_block(feedback_text),
            fashion_rules_block=f"\n{fashion_rules_block}",
            knowledge_block=_build_knowledge_block(knowledge_text) + trend_grounding.build_trend_block(trend_context),
        )
        + summary_block
        + image_instruction
    )

    # ── Step 5: Build conversation messages ───────────────────────────────────
    # Sanitise every user-supplied string before it enters the conversation.
    messages: list[dict[str, Any]] = []
    for h in history_for_prompt[-10:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            safe_content = sanitize_user_text(str(content), field="message")
            messages.append({"role": role, "content": safe_content})

    safe_message = sanitize_user_text(message, field="message")
    augmented_message = safe_message
    if mood:
        safe_mood = sanitize_user_text(mood, field="notes", max_len=50)
        augmented_message += f"\n\n[User mood: {safe_mood}]"
    if occasion:
        safe_occasion = sanitize_user_text(occasion, field="notes", max_len=60)
        augmented_message += f"\n[Occasion: {safe_occasion}]"
    else:
        # No specific occasion given — instruct FANI to cover all profile occasions
        augmented_message += "\n[No specific occasion requested — please build outfits for all occasions in the user's occasion_preferences profile list (max 4). If empty, default to: casual, work, and evening.]"

    # Build vision message when images are attached
    user_images = [img for img in (images or []) if img.startswith("data:image/")][:3]
    if user_images:
        vision_content: list[dict[str, Any]] = [{"type": "text", "text": augmented_message}]
        for img_b64 in user_images:
            vision_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": img_b64, "detail": "high"},
                }
            )
        messages.append({"role": "user", "content": vision_content})
        logger.info("vision_message_built", user_id=str(user_id), image_count=len(user_images))
    else:
        messages.append({"role": "user", "content": augmented_message})

    # ── Early exit: empty wardrobe ────────────────────────────────────────────
    if not closet_items and not valid_ids:
        logger.info("ai_chat_empty_wardrobe", user_id=str(user_id))
        return _empty_wardrobe_response()

    # ── Routing decision (before generation) ──────────────────────────────────
    # Score the task from signals already computed — not raw message length.
    decision = await model_router.route_async(
        RouteSignals(
            message=message,
            has_images=bool(user_images),
            closet_item_count=len(closet_items),
            expects_outfits=bool(occasion) or model_router.looks_like_outfit_request(message),
            weather_required=bool(weather),
            history_depth=len(history_for_prompt),
            constraint_count=sum(bool(x) for x in (occasion, weather, mood, user_profile)),
        )
    )

    # ── Call AI ───────────────────────────────────────────────────────────────
    try:
        raw = await ai_service.chat(
            messages,
            system_prompt,
            use_json_mode=True,
            model=decision.model,
            max_tokens=min(_CHAT_MAX_TOKENS, decision.max_tokens),
            temperature=decision.temperature,
            telemetry=LLMTelemetry(
                operation="stylist_chat",
                user_id=str(user_id),
                trace_id=str(chat_session.id) if chat_session else str(user_id),
                tier=decision.tier.value,
                route_reasons=decision.reasons,
            ),
        )
        data = json.loads(_clean_json(raw))
    except json.JSONDecodeError:
        logger.warning("ai_chat_bad_json", user_id=str(user_id), raw_preview=raw[:200] if "raw" in dir() else "")
        data = _fallback_response(message, closet_items)
    except Exception as exc:
        logger.error("ai_chat_failed", error=str(exc), user_id=str(user_id))
        data = _fallback_response(message, closet_items)

    # ── Validate & enrich ─────────────────────────────────────────────────────
    validation = validate_chat_response(data, valid_ids)
    if validation.errors and not validation.cleaned.get("reply"):
        # Hard error with no usable reply — cannot recover
        logger.error("ai_chat_response_invalid", errors=validation.errors, user_id=str(user_id))
        return _fallback_response(message, closet_items)
    if validation.errors:
        # Structural errors but reply exists — log and continue with cleaned data
        logger.warning("ai_chat_response_errors_degraded", errors=validation.errors, user_id=str(user_id))
    if validation.warnings:
        logger.info(
            "ai_chat_response_warnings",
            warnings=validation.warnings,
            outfits_removed=validation.outfits_removed,
            items_removed=validation.items_removed,
            user_id=str(user_id),
        )

    outfits = validation.cleaned.get("recommended_outfits") or []

    # Quality score — logged for monitoring; not returned to client
    quality = score_response_quality(validation, len(valid_ids))
    logger.info(
        "ai_response_quality",
        user_id=str(user_id),
        quality_overall=quality.overall,
        hallucination_risk=quality.hallucination_risk,
        outfit_completeness=quality.outfit_completeness,
        outfits=len(outfits),
    )

    # Collect the exact item IDs FANI chose and fetch their images in one query.
    # This covers items from prior chat turns that fall outside the RAG window.
    suggested_ids = {it.get("id") or "" for outfit in outfits for it in outfit.get("items") or [] if it.get("id")}
    image_lookup = await _fetch_image_lookup(session, suggested_ids)
    outfits = _enrich_items_with_images(outfits, image_lookup, closet_map)

    return {
        "reply": str(validation.cleaned.get("reply") or ""),
        "recommended_outfits": outfits,
        "styling_suggestions": validation.cleaned.get("styling_suggestions") or [],
        "purchase_gaps": validation.cleaned.get("purchase_gaps") or [],
        "follow_up_questions": validation.cleaned.get("follow_up_questions") or [],
    }


def _fallback_response(message: str, closet_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "reply": (
            "I'm having a moment — please try again in a few seconds. "
            f"Your wardrobe has {len(closet_items)} items ready for me to work with."
        ),
        "recommended_outfits": [],
        "styling_suggestions": [],
        "purchase_gaps": [],
        "follow_up_questions": [
            "What occasion are you dressing for?",
            "Would you like casual or smart recommendations?",
            "Can you help me improve my current style?",
        ],
    }


def _empty_wardrobe_response() -> dict[str, Any]:
    """Returned when the user has no closet items — prevents hallucination."""
    return {
        "reply": (
            "I don't have enough information to build outfits yet — your wardrobe is empty. "
            "Upload a few clothing items first and I'll craft personalised outfit recommendations from your actual clothes."
        ),
        "recommended_outfits": [],
        "styling_suggestions": [
            {
                "tip": "Start by uploading photos of your clothing items so I can learn your wardrobe.",
                "closet_item_name": None,
                "closet_item_id": None,
                "category": "general",
            }
        ],
        "purchase_gaps": [],
        "follow_up_questions": [
            "Once you've added items, what occasion would you like to dress for?",
            "Do you have a specific event coming up I can help with?",
        ],
    }
