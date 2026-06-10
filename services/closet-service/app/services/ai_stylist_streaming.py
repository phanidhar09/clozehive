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
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_safety import sanitize_user_text
from app.core.logging import get_logger
from app.models.ai_chat import AIChatSession
from app.models.closet import ClosetItem
from app.services import ai_service, weather_service
from app.core.ai_output_validator import score_response_quality, validate_chat_response
from app.services.ai_stylist_chat_service import (
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
from app.services.embedding_service import generate_text_embedding
from app.services.fashion_rag_service import get_fashion_context_for_prompt
from app.services.fashion_rules import build_fashion_rules_prompt_block
from app.services.outfit_history_service import get_outfit_history_for_prompt
from app.rag.query_builder import build_closet_rag_query
from app.services.style_profile_context import load_merged_user_profile_for_ai

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

    closet_task = asyncio.create_task(
        _rag_load_closet(session, user_id, query_embedding, occasion=occasion)
        if query_embedding
        else _fallback_closet(session, user_id)
    )
    profile_task = asyncio.create_task(
        load_merged_user_profile_for_ai(session, user_id, None)
    )
    weather_task = asyncio.create_task(
        _resolve_weather(session, user_id, location)
        if (weather_required or location)
        else _no_weather()
    )
    feedback_task = asyncio.create_task(
        get_outfit_history_for_prompt(
            session,
            str(user_id),
            occasion=occasion,
            limit=5,
            message=message,
        )
    )
    knowledge_task = asyncio.create_task(
        get_fashion_context_for_prompt(
            session, rag_query, limit=5, occasion=occasion, weather=weather_str
        )
    )

    closet_items, user_profile, weather, feedback_text, knowledge_text = await asyncio.gather(
        closet_task, profile_task, weather_task, feedback_task, knowledge_task,
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

    all_id_rows = await session.execute(
        select(ClosetItem.id).where(
            ClosetItem.user_id == user_id,
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    valid_ids = {str(r[0]) for r in all_id_rows.all()}
    closet_map = {it["id"]: it for it in closet_items}

    weather_cond = (weather.get("condition") or "mild") if weather else "mild"
    fashion_rules_block = build_fashion_rules_prompt_block(
        closet_items, occasion, weather_cond, user_profile
    )

    # Conversation summarization — fold older turns once history gets long.
    full_history = list(chat_history or [])
    summary_text, recent_history = await summarize_history(
        session, chat_session, full_history
    )

    user_images = [img for img in (images or []) if img.startswith("data:image/")][:3]
    image_instruction = (
        "\n[IMAGE ANALYSIS] The user has attached image(s) showing their outfit "
        "or clothing. Analyse visible items — colours, fit, silhouette, style — "
        "and cross-reference their wardrobe.\n"
        if user_images
        else ""
    )

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        wardrobe_block=_build_wardrobe_block(closet_items),
        profile_block=_build_profile_block(user_profile),
        weather_block=_build_weather_block(weather),
        feedback_block=_build_feedback_block(feedback_text),
        fashion_rules_block=f"\n{fashion_rules_block}",
        knowledge_block=_build_knowledge_block(knowledge_text),
    ) + _build_summary_block(summary_text) + image_instruction + (
        "\n\nSTREAMING DIRECTIVE: emit the JSON object with the `reply` field "
        "FIRST so the user sees the conversational answer immediately while "
        "the rest of the structured payload is still being generated."
    )

    messages: list[dict[str, Any]] = []
    for h in recent_history[-10:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append(
                {"role": role, "content": sanitize_user_text(str(content), field="message")}
            )

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
            content_arr.append(
                {"type": "image_url", "image_url": {"url": img_b64, "detail": "high"}}
            )
        messages.append({"role": "user", "content": content_arr})
    else:
        messages.append({"role": "user", "content": augmented})

    # ── Stream ──────────────────────────────────────────────────────────────
    # Match the non-streaming pipeline's reliability settings: JSON mode so the
    # full payload always parses, a large token budget so the structured JSON is
    # never truncated mid-outfit, and a lower temperature for schema adherence.
    extractor = _ReplyExtractor()
    try:
        async for chunk in ai_service.stream_chat(
            messages,
            system_prompt,
            use_json_mode=True,
            max_tokens=_CHAT_MAX_TOKENS,
            temperature=0.5,
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
    # closet-membership check, and score-breakdown correction — not just an ID strip.
    validation = validate_chat_response(data, valid_ids)
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

    quality = score_response_quality(validation, len(valid_ids))
    logger.info(
        "stream_response_quality",
        user_id=str(user_id),
        quality_overall=quality.overall,
        hallucination_risk=quality.hallucination_risk,
        outfits=len(outfits),
    )

    suggested_ids = {
        it.get("id") or ""
        for outfit in outfits
        for it in outfit.get("items") or []
        if it.get("id")
    }
    image_lookup = await _fetch_image_lookup(session, suggested_ids)
    outfits = _enrich_items_with_images(outfits, image_lookup, closet_map)

    yield {
        "type": "structured",
        "reply": str(cleaned.get("reply") or ""),
        "recommended_outfits": outfits,
        "styling_suggestions": cleaned.get("styling_suggestions") or [],
        "purchase_gaps": cleaned.get("purchase_gaps") or [],
        "follow_up_questions": cleaned.get("follow_up_questions") or [],
    }
