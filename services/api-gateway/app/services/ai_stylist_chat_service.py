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

from app.core.logging import get_logger
from app.core.llm_safety import (
    build_closet_item_summary,
    sanitize_user_text,
    wrap_untrusted,
)
from app.models.closet import ClosetItem
from app.repositories.user_repo import UserRepository
from app.services import ai_service, weather_service
from app.services.embedding_service import (
    generate_text_embedding,
    item_to_embedding_text,
    pgvector_cosine_search,
)
from app.services.fashion_rag_service import get_fashion_context_for_prompt
from app.services.fashion_rules import build_fashion_rules_prompt_block
from app.services.outfit_history_service import get_outfit_history_for_prompt
from app.services.style_profile_context import load_merged_user_profile_for_ai

logger = get_logger("ai_stylist_chat_service")

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
You are FANI — ClozeHive's personal AI stylist (Fashion AI Nurturing Individuality). \
You are warm, encouraging, and specific. You handle ALL fashion and styling questions — not just outfit building.

CAPABILITIES:
• Recommend outfits built exclusively from the user's wardrobe (WARDROBE CONTEXT below)
• Answer general fashion/styling questions (color theory, trends, rules, care tips, etc.)
• Critique and improve existing outfits — suggest specific closet items to swap or add
• Identify wardrobe gaps and what to buy next
• Give styling tips for specific body types, occasions, or moods
• Help the user understand their own style identity

STRICT RULES FOR OUTFIT RECOMMENDATIONS:
1. Outfit items MUST come exclusively from [WARDROBE CONTEXT]. NEVER invent items.
2. Always use the exact item id and name from the wardrobe list.
3. matching_score must equal color + occasion + fit + style + weather + preference (max 100).
4. For every outfit, explain WHY it works in "reasoning".
5. List 1–3 actionable "improvement_tips" — reference specific closet items where possible.
6. List "fashion_rules_used" as short strings (e.g. "color harmony", "60-30-10 rule").
7. If wardrobe has <3 suitable items, fill "purchase_gaps" with what is missing.

STYLING SUGGESTIONS:
• When asked to improve styling or "how can I look better", provide "styling_suggestions" — an array of specific, actionable tips.
• Each suggestion should reference real items from the wardrobe when possible (use their exact names).
• Suggestions can cover: adding accessories, trying different color combos, re-purposing items, layering ideas.

GENERAL QUESTIONS:
• When the question is general (trends, color theory, care, fashion rules, body type advice), answer in "reply" conversationally.
• You may still suggest closet items if they're relevant.
• Skip "recommended_outfits" array (leave empty []) for purely general questions.

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
        "season": row.get("season") or [],
        "occasion": row.get("occasion") or [],
        "wear_count": row.get("wear_count") or 0,
        "image_url": (
            row.get("processed_image_url")
            or row.get("image_url")
            or row.get("original_image_url")
        ),
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
        "season": item.season or [],
        "occasion": item.occasion or [],
        "wear_count": item.wear_count,
        "image_url": (
            item.processed_image_url
            or item.image_url
            or item.original_image_url
            or None
        ),
        "tags": item.tags or [],
    }


async def _rag_load_closet(
    session: AsyncSession, user_id: UUID, query_embedding: list[float]
) -> list[dict[str, Any]]:
    """Vector-search closet items by semantic similarity to the user's message."""
    rows = await pgvector_cosine_search(
        session,
        table="closet_items",
        embedding=query_embedding,
        user_id=str(user_id),
        limit=_RAG_CLOSET_LIMIT,
        threshold=0.30,  # low threshold — we want broad coverage for fashion
        filter_archived=True,
    )
    if rows:
        logger.info(
            "rag_closet_retrieved",
            user_id=str(user_id),
            count=len(rows),
            top_score=round(float(rows[0].get("similarity_score", 0)), 3),
        )
        return [_row_to_item(r) for r in rows]

    # Fallback: no embeddings yet — load by wear count
    logger.info("rag_closet_fallback_no_embeddings", user_id=str(user_id))
    result = await session.execute(
        select(ClosetItem)
        .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
        .order_by(ClosetItem.wear_count.desc(), ClosetItem.created_at.desc())
        .limit(_FALLBACK_CLOSET_LIMIT)
    )
    return [_orm_to_item(item) for item in result.scalars().all()]


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
                return await weather_service.get_current_weather(
                    float(coords["lat"]), float(coords["lon"]), label
                )
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
        occ = sanitize_user_text(
            ", ".join(occ_raw) if isinstance(occ_raw, list) else str(occ_raw),
            field="notes", max_len=80,
        ) or "any"
        season_raw = it.get("season") or []
        season = sanitize_user_text(
            ", ".join(season_raw) if isinstance(season_raw, list) else str(season_raw),
            field="notes", max_len=60,
        ) or "all"
        lines.append(
            f"  id={it['id']} | {sanitize_user_text(it.get('name', ''), field='name')} | "
            f"{sanitize_user_text(it.get('category', ''), field='category')} | "
            f"color={sanitize_user_text(it.get('color') or '?', field='color', max_len=40)} | "
            f"fabric={sanitize_user_text(it.get('fabric') or '?', field='material', max_len=60)} | "
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
    return knowledge_text if knowledge_text else ""


def _validate_item_ids(
    outfits: list[dict[str, Any]], valid_ids: set[str]
) -> list[dict[str, Any]]:
    """Strip any outfit items whose ID is not in the user's actual closet."""
    cleaned = []
    for outfit in outfits:
        items = [it for it in (outfit.get("items") or []) if it.get("id") in valid_ids]
        if items:
            outfit = {**outfit, "items": items}
            cleaned.append(outfit)
    return cleaned


def _enrich_items_with_images(
    outfits: list[dict[str, Any]], closet_map: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Add image_url to each outfit item from the closet map."""
    for outfit in outfits:
        enriched = []
        for it in outfit.get("items") or []:
            full = closet_map.get(it.get("id") or "")
            enriched.append({**it, "image_url": full.get("image_url") if full else None})
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
    occasion = ctx.get("occasion") or "casual"
    location = ctx.get("location")
    weather_required = ctx.get("weather_required", False)
    mood = ctx.get("mood") or ""

    # ── Step 1: Embed the user message (used for all vector searches) ─────────
    rag_query = f"{message} occasion:{occasion}"
    if mood:
        rag_query += f" mood:{mood}"

    query_embedding = await generate_text_embedding(rag_query)

    # ── Step 2: Parallel RAG + profile + weather retrieval ────────────────────
    async def _no_weather() -> None:
        return None

    closet_task = asyncio.create_task(
        _rag_load_closet(session, user_id, query_embedding)
        if query_embedding
        else _fallback_closet(session, user_id)
    )
    profile_task = asyncio.create_task(load_merged_user_profile_for_ai(session, user_id, None))
    weather_task = asyncio.create_task(
        _resolve_weather(session, user_id, location) if (weather_required or location) else _no_weather()
    )
    # RAG: similar past outfits via pgvector (uses its own embedding internally)
    feedback_task = asyncio.create_task(
        get_outfit_history_for_prompt(session, str(user_id), occasion, limit=5)
    )
    # RAG: fashion knowledge base
    knowledge_task = asyncio.create_task(
        get_fashion_context_for_prompt(session, rag_query, limit=3)
    )

    closet_items, user_profile, weather, feedback_text, knowledge_text = await asyncio.gather(
        closet_task, profile_task, weather_task, feedback_task, knowledge_task,
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

    # Build a fast lookup map for post-validation
    # RAG returns top-K — we also need full closet IDs to validate recommendations
    # Load all IDs (no embeddings needed) for the validation set
    all_id_rows = await session.execute(
        select(ClosetItem.id)
        .where(ClosetItem.user_id == user_id, ClosetItem.is_archived == False)  # noqa: E712
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

    # ── Step 3: Build fashion rules hint ─────────────────────────────────────
    weather_cond = (weather.get("condition") or "mild") if weather else "mild"
    fashion_rules_block = build_fashion_rules_prompt_block(
        closet_items[:20], occasion, weather_cond, user_profile
    )

    # ── Step 4: Assemble system prompt ────────────────────────────────────────
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        wardrobe_block=_build_wardrobe_block(closet_items),
        profile_block=_build_profile_block(user_profile),
        weather_block=_build_weather_block(weather),
        feedback_block=_build_feedback_block(feedback_text),
        fashion_rules_block=f"\n{fashion_rules_block}",
        knowledge_block=_build_knowledge_block(knowledge_text),
    )

    # ── Step 5: Build conversation messages ───────────────────────────────────
    # Sanitise every user-supplied string before it enters the conversation.
    messages: list[dict[str, str]] = []
    for h in (chat_history or [])[-10:]:
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
    if occasion and occasion != "casual":
        safe_occasion = sanitize_user_text(occasion, field="notes", max_len=60)
        augmented_message += f"\n[Occasion: {safe_occasion}]"
    messages.append({"role": "user", "content": augmented_message})

    # ── Call AI ───────────────────────────────────────────────────────────────
    try:
        raw = await ai_service.chat(messages, system_prompt)
        data = json.loads(_clean_json(raw))
    except json.JSONDecodeError:
        logger.warning("ai_chat_bad_json", user_id=str(user_id))
        data = _fallback_response(message, closet_items)
    except Exception as exc:
        logger.error("ai_chat_failed", error=str(exc), user_id=str(user_id))
        data = _fallback_response(message, closet_items)

    # ── Validate & enrich ─────────────────────────────────────────────────────
    outfits = data.get("recommended_outfits") or []
    outfits = _validate_item_ids(outfits, valid_ids)
    outfits = _enrich_items_with_images(outfits, closet_map)
    data["recommended_outfits"] = outfits

    return {
        "reply": str(data.get("reply") or ""),
        "recommended_outfits": outfits,
        "styling_suggestions": data.get("styling_suggestions") or [],
        "purchase_gaps": data.get("purchase_gaps") or [],
        "follow_up_questions": data.get("follow_up_questions") or [],
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
