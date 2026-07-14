"""Streaming + summarization helpers for the FANI AI Stylist chat.

Two responsibilities:

1. `stream_chat_message` — runs the same RAG pipeline as
   `ai_stylist_chat_service.process_chat_message` but yields incremental
   events instead of a single dict. The conversational `reply` field is
   extracted from the streaming JSON and emitted token-by-token; the rest of
   the structured payload (outfits, suggestions, gaps, follow-ups) is emitted
   as a single `structured` event once the full response has arrived.

2. `summarize_history` — folds older conversation turns into a compact memory
   block so long-running sessions stay coherent without exceeding the model's
   context budget. Re-summarises only the *new* messages since the last pass,
   merging them into any existing summary already stored on the session.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity.services.style_profile_context import load_merged_user_profile_for_ai
from app.api.v1.intelligence.services import ai_service, model_router, trend_grounding
from app.api.v1.intelligence.services.ai_stylist_chat_service import (
    _CHAT_MAX_TOKENS,
    _SYSTEM_PROMPT_TEMPLATE,
    _build_feedback_block,
    _build_knowledge_block,
    _build_profile_block,
    _build_wardrobe_block,
    _build_weather_block,
    _clean_json,
    _enrich_items_with_images,
    _fallback_closet,
    _fallback_response,
    _fetch_image_lookup,
    _rag_load_closet,
    _resolve_weather,
)
from app.api.v1.intelligence.services.fashion_rag_service import get_fashion_context_for_prompt
from app.api.v1.intelligence.services.fashion_rules import build_fashion_rules_prompt_block
from app.api.v1.intelligence.services.model_router import RouteSignals
from app.api.v1.wardrobe.services.outfit_history_service import get_outfit_history_for_prompt
from app.core import cache_service, semantic_cache
from app.core.ai_output_validator import score_response_quality, validate_chat_response
from app.core.analytics import LLMTelemetry
from app.core.claim_grounding import (
    GroundingContext,
    audit_outfit_seasons,
    audit_reply_claims,
    audit_suggestion_entries,
    redact_ungrounded_claims,
)
from app.core.embedding_service import generate_text_embedding
from app.core.llm_safety import sanitize_user_text
from app.core.logging import get_logger
from app.db.session import run_in_read_session
from app.models.ai_chat import AIChatSession
from app.models.closet import ClosetItem
from app.rag.query_builder import build_closet_rag_query

logger = get_logger("ai_stylist_streaming")


# ─────────────────────────────────────────────────────────────────────────────
# Conversation summarization
# ─────────────────────────────────────────────────────────────────────────────

# Below this many *prior* messages, we send the whole history verbatim.
SUMMARY_TRIGGER_TURNS = 10
# Once triggered, keep this many of the most-recent messages verbatim and
# fold the rest into the rolling summary. Recent turns matter most for
# immediate context, so we never summarise them.
SUMMARY_KEEP_RECENT = 4

# Above this item-hallucination ratio the streamed reply text likely references
# items the validator removed. Streamed tokens can't be un-sent, so we emit a
# `correction` event and let the client annotate the already-shown text.
_HALLUCINATION_NOTICE_THRESHOLD = 0.34

_SUMMARY_SYSTEM_PROMPT = (
    "You are summarising a styling conversation between a user and FANI "
    "(an AI fashion assistant). Produce a dense, third-person memory note "
    "that future turns can use as background.\n\n"
    "Include, when present:\n"
    "  - Recurring style preferences the user has stated\n"
    "  - Occasions, trips, or events they're dressing for\n"
    "  - Items they've liked, rejected, or asked to avoid\n"
    "  - Any wardrobe gaps or purchases discussed\n"
    "  - Constraints (budget, weather, body-fit issues)\n\n"
    "Output 4-8 bullet points, no preamble, no closing remarks. "
    "Each bullet under 25 words."
)


async def summarize_history(
    session: AsyncSession,
    chat_session: AIChatSession,
    full_history: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Compress older turns into a rolling summary.

    Returns ``(summary_text, recent_history_to_send_verbatim)``. The summary
    is also persisted onto ``chat_session`` so subsequent turns reuse it
    instead of regenerating from scratch.
    """
    if len(full_history) <= SUMMARY_TRIGGER_TURNS:
        return chat_session.summary or "", full_history

    cutoff = len(full_history) - SUMMARY_KEEP_RECENT
    older = full_history[:cutoff]
    recent = full_history[cutoff:]

    already_done = chat_session.summary_through_msg_count or 0
    new_to_summarise = older[already_done:]
    if not new_to_summarise:
        return chat_session.summary or "", recent

    # Build the summarisation prompt: existing summary (if any) plus the new
    # messages, all sanitised to defeat prompt-injection from the user side.
    lines: list[str] = []
    if chat_session.summary:
        lines.append(f"[EXISTING SUMMARY]\n{chat_session.summary}\n")
    lines.append("[NEW MESSAGES TO FOLD IN]")
    for h in new_to_summarise:
        role = h.get("role", "user")
        content = sanitize_user_text(str(h.get("content", "")), field="message")
        if content:
            lines.append(f"{role.upper()}: {content}")
    lines.append("\nReturn the updated, merged summary now.")

    try:
        text = await ai_service.chat(
            messages=[{"role": "user", "content": "\n".join(lines)}],
            system_prompt=_SUMMARY_SYSTEM_PROMPT,
        )
        summary = text.strip()
        # Persist progress so the next turn skips already-summarised messages.
        chat_session.summary = summary
        chat_session.summary_through_msg_count = cutoff
        logger.info(
            "chat_summary_updated",
            session_id=str(chat_session.id),
            folded=len(new_to_summarise),
            summary_len=len(summary),
        )
        return summary, recent
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_summary_failed", error=str(exc))
        # Fall back to the previous summary; don't bump the watermark so we'll
        # retry next turn.
        return chat_session.summary or "", recent


def _build_summary_block(summary: str) -> str:
    if not summary:
        return ""
    return (
        "\n[CONVERSATION SUMMARY — earlier turns folded down for brevity]\n"
        f"{summary}\n[END CONVERSATION SUMMARY]\n"
        "Use this as background. It supersedes anything contradictory in the "
        "live history but is itself superseded by the user's current message."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Partial JSON streaming: extract the `reply` field as it arrives
# ─────────────────────────────────────────────────────────────────────────────


_REPLY_MARKER_RE = re.compile(r'"reply"\s*:\s*"')


class _ReplyExtractor:
    """Incrementally pull the value of the JSON ``"reply"`` field out of a
    stream of OpenAI-generated text.

    The LLM is instructed to emit ``reply`` first in its JSON object. We scan
    the accumulating buffer, locate the field, then yield characters until we
    hit the unescaped closing quote — handling JSON escape sequences
    (``\\n``, ``\\"``, ``\\\\`` …) along the way so the user-visible text is
    properly decoded.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._cursor = 0
        self._in_reply = False
        self._done = False
        self._pending_escape = False

    def feed(self, chunk: str) -> str:
        """Append a chunk of raw model output, return any newly-decoded reply
        characters that should be flushed to the client."""
        if self._done:
            self._buf += chunk  # keep buffering so the caller can parse later
            return ""
        self._buf += chunk

        # Locate the reply field's opening quote if we haven't yet.
        if not self._in_reply:
            match = _REPLY_MARKER_RE.search(self._buf, self._cursor)
            if not match:
                return ""
            self._in_reply = True
            self._cursor = match.end()

        out: list[str] = []
        i = self._cursor
        n = len(self._buf)
        while i < n:
            ch = self._buf[i]
            if self._pending_escape:
                # JSON string escape decoding.
                out.append(
                    {
                        "n": "\n",
                        "t": "\t",
                        "r": "\r",
                        '"': '"',
                        "\\": "\\",
                        "/": "/",
                        "b": "\b",
                        "f": "\f",
                    }.get(ch, ch)
                )
                self._pending_escape = False
                i += 1
            elif ch == "\\":
                # Need the next char to interpret the escape. Bail and resume
                # next feed() once we have it.
                if i + 1 >= n:
                    break
                self._pending_escape = True
                i += 1
            elif ch == '"':
                # End of the reply string.
                self._done = True
                i += 1
                self._cursor = i
                return "".join(out)
            else:
                out.append(ch)
                i += 1

        self._cursor = i
        return "".join(out)

    @property
    def raw_buffer(self) -> str:
        return self._buf


# ─────────────────────────────────────────────────────────────────────────────
# Public streaming entry point
# ─────────────────────────────────────────────────────────────────────────────


async def stream_chat_message(
    session: AsyncSession,
    user_id: UUID,
    message: str,
    chat_session: AIChatSession,
    context: dict[str, Any] | None = None,
    chat_history: list[dict[str, str]] | None = None,
    images: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the FANI RAG pipeline and stream events.

    Yields:
        ``{"type": "token", "content": "..."}`` — reply text fragments
        ``{"type": "structured", "reply": "...", "recommended_outfits": ...,
            "styling_suggestions": ..., "purchase_gaps": ...,
            "follow_up_questions": ...}``
    """
    ctx = context or {}
    occasion: str | None = ctx.get("occasion") or None
    location = ctx.get("location")
    weather_required = ctx.get("weather_required", False)
    mood = ctx.get("mood") or ""

    rag_query = build_closet_rag_query(message, occasion=occasion, mood=mood)
    weather_str = location or ""

    query_embedding = await generate_text_embedding(rag_query)

    async def _no_weather() -> None:
        return None

    # Each parallel DB task MUST own its session — a single AsyncSession is not
    # safe for concurrent use, so the shared request session cannot be fanned
    # out across asyncio.gather (see db.session.run_in_read_session).
    closet_task = asyncio.create_task(
        run_in_read_session(lambda s: _rag_load_closet(s, user_id, query_embedding, occasion=occasion))
        if query_embedding
        else run_in_read_session(lambda s: _fallback_closet(s, user_id))
    )
    profile_task = asyncio.create_task(
        run_in_read_session(lambda s: load_merged_user_profile_for_ai(s, user_id, None))
    )
    weather_task = asyncio.create_task(
        run_in_read_session(lambda s: _resolve_weather(s, user_id, location))
        if (weather_required or location)
        else _no_weather()
    )
    feedback_task = asyncio.create_task(
        run_in_read_session(
            lambda s: get_outfit_history_for_prompt(
                s,
                str(user_id),
                occasion=occasion,
                limit=5,
                message=message,
            )
        )
    )
    knowledge_task = asyncio.create_task(
        run_in_read_session(
            lambda s: get_fashion_context_for_prompt(s, rag_query, limit=5, occasion=occasion, weather=weather_str)
        )
    )
    # Live trend grounding — short-circuits to None unless the message has
    # trend intent (Phase 7; kept at parity with process_chat_message).
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

    if isinstance(closet_items, Exception):
        logger.warning("stream_closet_rag_failed", error=str(closet_items))
        closet_items = await _fallback_closet(session, user_id)
    if isinstance(user_profile, Exception):
        user_profile = None
    if isinstance(weather, Exception):
        weather = None
    if isinstance(feedback_text, Exception):
        feedback_text = ""
    if isinstance(knowledge_text, Exception):
        knowledge_text = ""
    if isinstance(trend_context, Exception):
        trend_context = None

    all_id_rows = await session.execute(
        select(ClosetItem.id).where(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    valid_ids = {str(r[0]) for r in all_id_rows.all()}
    closet_map = {it["id"]: it for it in closet_items}

    # ── Semantic cache lookup (parity with the non-streaming path) ──────────
    # Reuses the RAG query embedding; keyed on the FULL closet hash + profile +
    # weather condition. Context-light turns only. On a hit the whole reply is
    # emitted as one token event and the structured payload follows — the
    # client render path is identical to a live stream, just instant.
    sem_closet_hash = cache_service.build_closet_hash([{"id": i} for i in sorted(valid_ids)])
    sem_profile_hash = cache_service.build_profile_hash(user_profile)
    sem_weather_key = (weather.get("condition") or "mild") if weather else ""
    sem_eligible = not [img for img in (images or []) if img.startswith("data:image/")] and len(chat_history or []) <= 2
    if sem_eligible:
        cached_response = await semantic_cache.lookup(
            str(user_id),
            query_embedding,
            closet_hash=sem_closet_hash,
            profile_hash=sem_profile_hash,
            weather_key=sem_weather_key,
        )
        if cached_response is not None:
            yield {"type": "token", "content": str(cached_response.get("reply") or ""), "cache": "HIT"}
            yield {"type": "structured", "cached": True, "corrected": False, **cached_response}
            return

    weather_cond = (weather.get("condition") or "mild") if weather else "mild"
    fashion_rules_block = build_fashion_rules_prompt_block(
        closet_items, occasion or "casual", weather_cond, user_profile
    )

    # Conversation summarization — fold older turns once history gets long.
    full_history = list(chat_history or [])
    summary_text, recent_history = await summarize_history(session, chat_session, full_history)

    user_images = [img for img in (images or []) if img.startswith("data:image/")][:3]
    image_instruction = (
        "\n[IMAGE ANALYSIS] The user has attached image(s) showing their outfit "
        "or clothing. Analyse visible items — colours, fit, silhouette, style — "
        "and cross-reference their wardrobe.\n"
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
        + _build_summary_block(summary_text)
        + image_instruction
        + (
            "\n\nSTREAMING DIRECTIVE: emit the JSON object with the `reply` field "
            "FIRST so the user sees the conversational answer immediately while "
            "the rest of the structured payload is still being generated."
        )
    )

    messages: list[dict[str, Any]] = []
    for h in recent_history[-10:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": sanitize_user_text(str(content), field="message")})

    safe_message = sanitize_user_text(message, field="message")
    augmented = safe_message
    if mood:
        augmented += f"\n\n[User mood: {sanitize_user_text(mood, field='notes', max_len=50)}]"
    if occasion:
        augmented += f"\n[Occasion: {sanitize_user_text(occasion, field='notes', max_len=60)}]"
    else:
        augmented += (
            "\n[No specific occasion requested — please build outfits for all "
            "occasions in the user's occasion_preferences (max 4). If empty, "
            "default to: casual, work, and evening.]"
        )

    if user_images:
        content_arr: list[dict[str, Any]] = [{"type": "text", "text": augmented}]
        for img_b64 in user_images:
            content_arr.append({"type": "image_url", "image_url": {"url": img_b64, "detail": "high"}})
        messages.append({"role": "user", "content": content_arr})
    else:
        messages.append({"role": "user", "content": augmented})

    # ── Routing decision (before generation) ─────────────────────────────────
    decision = await model_router.route_async(
        RouteSignals(
            message=message,
            has_images=bool(user_images),
            closet_item_count=len(closet_items),
            expects_outfits=bool(occasion) or model_router.looks_like_outfit_request(message),
            weather_required=bool(weather),
            history_depth=len(recent_history),
            constraint_count=sum(bool(x) for x in (occasion, weather, mood, user_profile)),
        )
    )

    # ── Stream ──────────────────────────────────────────────────────────────
    extractor = _ReplyExtractor()
    try:
        async for chunk in ai_service.stream_chat(
            messages,
            system_prompt,
            use_json_mode=True,
            model=decision.model,
            max_tokens=min(_CHAT_MAX_TOKENS, decision.max_tokens),
            temperature=decision.temperature,
            telemetry=LLMTelemetry(
                operation="stylist_chat_stream",
                user_id=str(user_id),
                trace_id=str(chat_session.id) if chat_session else str(user_id),
                tier=decision.tier.value,
                route_reasons=decision.reasons,
            ),
        ):
            decoded = extractor.feed(chunk)
            if decoded:
                yield {"type": "token", "content": decoded}
    except Exception as exc:  # noqa: BLE001
        logger.error("stream_chat_failed", error=str(exc), user_id=str(user_id))
        fallback = _fallback_response(message, closet_items)
        yield {"type": "structured", **fallback}
        return

    # ── Parse the full JSON for the structured payload ──────────────────────
    raw = extractor.raw_buffer
    try:
        data = json.loads(_clean_json(raw))
    except json.JSONDecodeError:
        logger.warning("stream_chat_bad_json", user_id=str(user_id))
        data = _fallback_response(message, closet_items)

    # Use the same strong validator as the non-streaming path: UUID-format check,
    # closet-membership check, within-outfit de-dupe, closet-record attribute
    # grounding, and score-breakdown correction — not just an ID strip.
    validation = validate_chat_response(data, valid_ids, closet_map=closet_map)

    # ── Grounding gate (parity with the non-streaming path) ─────────────────
    # The reply tokens have already streamed, so we can't retract them. Instead,
    # when validation finds the response ungrounded we (a) emit a `correction`
    # event the client can act on and (b) persist the *grounded* payload rather
    # than the raw model output.
    if validation.errors and not validation.cleaned.get("reply"):
        logger.error("stream_chat_response_invalid", errors=validation.errors, user_id=str(user_id))
        fallback = _fallback_response(message, closet_items)
        # `reply` replaces the (unusable) streamed text on the client.
        yield {"type": "correction", "reason": "ungrounded", "reply": fallback["reply"]}
        yield {"type": "structured", "corrected": True, **fallback}
        return

    if validation.warnings:
        logger.info(
            "stream_chat_response_warnings",
            warnings=validation.warnings,
            outfits_removed=validation.outfits_removed,
            items_removed=validation.items_removed,
            user_id=str(user_id),
        )
    cleaned = validation.cleaned
    outfits = cleaned.get("recommended_outfits") or []

    # ── Claim-grounding audit (prose + item seasons) ─────────────────────────
    # Provenance checks (weather/memory/preference/image claims require the
    # matching context this turn) + closet-record checks (colour/material/brand
    # of *owned* items) + season sanity on recommended items. The streamed text
    # already shipped, so ungrounded sentences are redacted from the *persisted*
    # reply and the client gets a `correction` annotation.
    grounding_ctx = GroundingContext(
        weather_provided=bool(weather),
        history_depth=len(full_history),
        profile_provided=bool(user_profile),
        images_provided=bool(user_images),
        current_month=datetime.now(UTC).month,
    )
    reply_violations = audit_reply_claims(cleaned.get("reply"), closet_map, grounding_ctx)
    season_violations = audit_outfit_seasons(outfits, closet_map, grounding_ctx.current_month)
    # Suggestion side channels get the same audit; flagged entries are dropped
    # whole (they ship in this structured event, so containment is total here).
    cleaned["styling_suggestions"], suggestion_violations = audit_suggestion_entries(
        cleaned.get("styling_suggestions"), closet_map, grounding_ctx, valid_item_ids=valid_ids
    )
    cleaned["purchase_gaps"], gap_violations = audit_suggestion_entries(
        cleaned.get("purchase_gaps"), closet_map, grounding_ctx, valid_item_ids=valid_ids
    )
    if suggestion_violations or gap_violations:
        logger.warning(
            "stream_suggestions_dropped",
            user_id=str(user_id),
            dropped=len(suggestion_violations) + len(gap_violations),
            kinds=sorted({v.kind for v in suggestion_violations + gap_violations}),
        )
    claim_violations = reply_violations + suggestion_violations + gap_violations
    if reply_violations:
        redacted_reply, removed_sentences = redact_ungrounded_claims(cleaned.get("reply"), reply_violations)
        cleaned["reply"] = redacted_reply
        logger.warning(
            "stream_reply_claims_redacted",
            user_id=str(user_id),
            removed_sentences=removed_sentences,
            kinds=sorted({v.kind for v in reply_violations}),
        )
        yield {
            "type": "correction",
            "reason": "ungrounded_claims",
            "note": "I've removed a couple of details I couldn't verify against your closet or this conversation.",
            "reply": redacted_reply,
        }
    if season_violations:
        logger.info(
            "stream_outfit_season_mismatch",
            user_id=str(user_id),
            details=[v.detail for v in season_violations],
        )

    quality = score_response_quality(validation, len(valid_ids))
    logger.info(
        "stream_response_quality",
        user_id=str(user_id),
        quality_overall=quality.overall,
        hallucination_risk=quality.hallucination_risk,
        ungrounded_claims=len(claim_violations),
        season_mismatches=len(season_violations),
        attributes_corrected=validation.attributes_corrected,
        outfits=len(outfits),
    )

    # The validator removed hallucinated items/outfits. When a meaningful share
    # was removed, the already-streamed reply text may reference them — flag it so
    # the client can annotate (the text itself cannot be un-sent).
    corrected = validation.outfits_removed > 0 or validation.items_removed > 0 or bool(claim_violations)
    if (
        validation.outfits_removed or validation.items_removed
    ) and quality.hallucination_risk >= _HALLUCINATION_NOTICE_THRESHOLD:
        yield {
            "type": "correction",
            "reason": "adjusted",
            "note": "I refined a few suggestions to match items you actually own.",
        }

    suggested_ids = {it.get("id") or "" for outfit in outfits for it in outfit.get("items") or [] if it.get("id")}
    image_lookup = await _fetch_image_lookup(session, suggested_ids)
    outfits = _enrich_items_with_images(outfits, image_lookup, closet_map)

    response = {
        "reply": str(cleaned.get("reply") or ""),
        "recommended_outfits": outfits,
        "styling_suggestions": cleaned.get("styling_suggestions") or [],
        "purchase_gaps": cleaned.get("purchase_gaps") or [],
        "follow_up_questions": cleaned.get("follow_up_questions") or [],
    }

    yield {
        "type": "structured",
        **response,
        # Grounding signals — surfaced to the client and persisted for later audit.
        "corrected": corrected,
        "quality": {
            "overall": quality.overall,
            "hallucination_risk": quality.hallucination_risk,
            "outfit_completeness": quality.outfit_completeness,
            "ungrounded_claims": len(claim_violations),
            "season_mismatches": len(season_violations),
            "attributes_corrected": validation.attributes_corrected,
        },
    }

    # ── Semantic cache store (parity with the non-streaming path) ────────────
    # Only replay responses that could not be wrong: fully valid, nothing
    # removed by the grounding gate, no claim-audit violations, a real reply.
    if (
        sem_eligible
        and validation.is_valid
        and validation.items_removed == 0
        and validation.outfits_removed == 0
        and not claim_violations
        and not season_violations
        and response["reply"]
    ):
        await semantic_cache.store(
            str(user_id),
            query_embedding,
            response,
            closet_hash=sem_closet_hash,
            profile_hash=sem_profile_hash,
            weather_key=sem_weather_key,
        )
