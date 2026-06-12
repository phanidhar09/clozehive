"""
AI Stylist Chat routes — /api/v1/ai-chat/*

Endpoints:
  POST   /ai-chat/sessions               — create a new chat session
  GET    /ai-chat/sessions               — list user's sessions
  GET    /ai-chat/sessions/{id}/messages — messages in a session
  POST   /ai-chat/message                — send a message (with outfit recommendations)
  POST   /ai-chat/feedback               — rate an AI-recommended outfit
  POST   /ai-chat/save-outfit            — save a recommended outfit to outfits table
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc

from app.core.deps import CurrentUser, DbSession
from app.core.rate_limit import limiter
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.ai_chat import (
    AIChatMessage,
    AIChatSession,
    DailyNudge,
    OutfitFeedback,
)
from app.models.closet import ClosetItem, Outfit
from app.services.ai_stylist_chat_service import process_chat_message
from app.services.ai_stylist_streaming import stream_chat_message
from app.services.daily_nudges_service import (
    fetch_or_generate_today_nudge,
    serialize_nudge,
)
from app.services.outfit_history_service import (
    save_outfit_history,
    save_outfit_history_background,
)

router = APIRouter(prefix="/ai-chat", tags=["AI Chat"])
logger = get_logger("ai_chat.routes")

# ── Request / Response Schemas ────────────────────────────────────────────────


class ChatContext(BaseModel):
    occasion: str | None = None
    mood: str | None = None
    location: str | None = None
    weather_required: bool = False


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None  # if None, creates a new session
    context: ChatContext | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list, max_length=3)  # base64 data-URLs


class FeedbackRequest(BaseModel):
    closet_item_ids: list[str] = Field(default_factory=list)
    outfit_id: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    feedback_text: str | None = Field(None, max_length=1000)
    occasion: str | None = None
    mood: str | None = None
    was_worn: bool = False


class SaveOutfitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    item_ids: list[str] = Field(..., min_items=1)
    occasion: str = "casual"
    explanation: str | None = None
    style_score: int | None = Field(None, ge=0, le=100)
    session_id: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _session_title_from_message(message: str) -> str:
    """Derive a short session title from the first user message."""
    cleaned = message.strip().rstrip("?!.")[:60]
    return cleaned if cleaned else "AI Stylist Chat"


async def _assert_session_owner(session, session_id: UUID, user_id: UUID) -> AIChatSession:
    result = await session.execute(
        select(AIChatSession).where(
            AIChatSession.id == session_id,
            AIChatSession.user_id == user_id,
        )
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return chat_session


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(user_id: CurrentUser, session: DbSession) -> dict[str, Any]:
    """Create a new empty chat session."""
    uid = UUID(user_id)
    chat_session = AIChatSession(user_id=uid, title="New Chat")
    session.add(chat_session)
    await session.flush()
    await session.refresh(chat_session)
    return {
        "id": str(chat_session.id),
        "title": chat_session.title,
        "created_at": chat_session.created_at.isoformat(),
        "updated_at": chat_session.updated_at.isoformat(),
    }


@router.get("/sessions")
async def list_sessions(user_id: CurrentUser, session: DbSession) -> dict[str, Any]:
    """List all chat sessions for the authenticated user."""
    uid = UUID(user_id)
    result = await session.execute(
        select(AIChatSession)
        .where(AIChatSession.user_id == uid)
        .order_by(desc(AIChatSession.updated_at))
        .limit(50)
    )
    rows = result.scalars().all()
    return {
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in rows
        ]
    }


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str, user_id: CurrentUser, session: DbSession
) -> None:
    """Delete a chat session and all its messages. Validates ownership."""
    uid = UUID(user_id)
    try:
        sid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id")

    chat_session = await _assert_session_owner(session, sid, uid)
    await session.delete(chat_session)
    # AIChatMessage rows cascade-delete via FK ondelete="CASCADE"
    logger.info("chat_session_deleted", session_id=session_id, user_id=user_id)


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str, user_id: CurrentUser, session: DbSession
) -> dict[str, Any]:
    """Return all messages in a session. Validates ownership."""
    uid = UUID(user_id)
    try:
        sid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id")

    await _assert_session_owner(session, sid, uid)

    result = await session.execute(
        select(AIChatMessage)
        .where(AIChatMessage.session_id == sid)
        .order_by(AIChatMessage.created_at)
    )
    msgs = result.scalars().all()
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "message": m.message,
                "structured_response": m.structured_response,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


@router.post("/message")
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    body: SendMessageRequest,
    user_id: CurrentUser,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Send a message to the AI Stylist and receive outfit recommendations."""
    uid = UUID(user_id)

    # ── Resolve or create session ─────────────────────────────────────────────
    if body.session_id:
        try:
            sid = UUID(body.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id")
        chat_session = await _assert_session_owner(session, sid, uid)
    else:
        chat_session = AIChatSession(
            user_id=uid,
            title=_session_title_from_message(body.message),
        )
        session.add(chat_session)
        await session.flush()  # get the ID before we need it

    # ── Persist user message ──────────────────────────────────────────────────
    user_msg = AIChatMessage(
        session_id=chat_session.id,
        user_id=uid,
        role="user",
        message=body.message,
    )
    session.add(user_msg)

    # ── Run AI pipeline ───────────────────────────────────────────────────────
    ctx = body.context.model_dump() if body.context else {}
    try:
        ai_response = await process_chat_message(
            session=session,
            user_id=uid,
            message=body.message,
            context=ctx,
            chat_history=body.history,
            images=body.images or [],
            chat_session=chat_session,
        )
    except Exception as exc:
        logger.error("ai_stylist_chat_error", error=str(exc), user_id=user_id)
        raise HTTPException(status_code=500, detail="AI stylist is temporarily unavailable")

    # ── Persist assistant message ─────────────────────────────────────────────
    assistant_msg = AIChatMessage(
        session_id=chat_session.id,
        user_id=uid,
        role="assistant",
        message=ai_response.get("reply") or "",
        structured_response=ai_response,
    )
    session.add(assistant_msg)

    # Update session title if first message created it
    if not body.session_id:
        chat_session.title = _session_title_from_message(body.message)

    await session.flush()
    await session.refresh(assistant_msg)

    # ── Save outfit history for RAG retrieval in future sessions ─────────────
    outfits = ai_response.get("recommended_outfits") or []
    occasion = ctx.get("occasion") or "casual"
    weather = ctx.get("location") or ""
    for outfit in outfits[:2]:  # save top 2 to avoid DB spam
        item_ids = [it.get("id") for it in (outfit.get("items") or []) if it.get("id")]
        item_names = [it.get("name") for it in (outfit.get("items") or []) if it.get("name")]
        score = outfit.get("matching_score")
        tips = outfit.get("improvement_tips") or []
        reasoning = outfit.get("reasoning") or ai_response.get("reply") or ""
        if item_ids:
            background_tasks.add_task(
                save_outfit_history_background,
                user_id=user_id,
                occasion=occasion,
                weather=weather,
                selected_item_ids=item_ids,
                item_names=item_names,
                matching_score=score,
                recommendation_text=reasoning,
                improvement_tips=tips,
            )

    return {
        "session_id": str(chat_session.id),
        "message_id": str(assistant_msg.id),
        "reply": ai_response.get("reply") or "",
        "recommended_outfits": outfits,
        "styling_suggestions": ai_response.get("styling_suggestions") or [],
        "purchase_gaps": ai_response.get("purchase_gaps") or [],
        "follow_up_questions": ai_response.get("follow_up_questions") or [],
    }


def _sse(payload: dict[str, Any]) -> bytes:
    """Encode a JSON payload as one Server-Sent Events frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/stream")
@limiter.limit("20/minute")
async def stream_message(
    request: Request,
    body: SendMessageRequest,
    user_id: CurrentUser,
) -> StreamingResponse:
    """Stream FANI's response via Server-Sent Events.

    Wire format (one ``data:`` frame per event):
        {"type": "session",    "session_id": "..."}
        {"type": "token",      "content": "..."}             (many)
        {"type": "structured", "recommended_outfits": [...],
                               "styling_suggestions": [...],
                               "purchase_gaps": [...],
                               "follow_up_questions": [...]}
        {"type": "done",       "message_id": "...", "session_id": "..."}
        {"type": "error",      "detail": "..."}              (on failure)
    """
    uid = UUID(user_id)
    ctx = body.context.model_dump() if body.context else {}

    async def event_generator():
        # Open a fresh DB session for the lifetime of the stream — the
        # request-scoped session is closed once the handler returns, but
        # this async generator continues yielding well after that.
        async with AsyncSessionLocal() as session:
            try:
                # ── Resolve or create chat session ───────────────────────────
                if body.session_id:
                    try:
                        sid = UUID(body.session_id)
                    except ValueError:
                        yield _sse({"type": "error", "detail": "Invalid session_id"})
                        return
                    chat_session = await _assert_session_owner(session, sid, uid)
                else:
                    chat_session = AIChatSession(
                        user_id=uid,
                        title=_session_title_from_message(body.message),
                    )
                    session.add(chat_session)
                    await session.flush()

                # Persist the user message immediately so it survives a
                # mid-stream disconnect.
                user_msg = AIChatMessage(
                    session_id=chat_session.id,
                    user_id=uid,
                    role="user",
                    message=body.message,
                )
                session.add(user_msg)
                await session.commit()
                await session.refresh(chat_session)

                yield _sse({"type": "session", "session_id": str(chat_session.id)})

                # ── Stream tokens + final structured payload ─────────────────
                final_payload: dict[str, Any] | None = None
                async for event in stream_chat_message(
                    session=session,
                    user_id=uid,
                    message=body.message,
                    chat_session=chat_session,
                    context=ctx,
                    chat_history=body.history,
                    images=body.images or [],
                ):
                    if event.get("type") == "structured":
                        final_payload = event
                    yield _sse(event)

                # ── Persist assistant message + outfit history ───────────────
                if final_payload is not None:
                    assistant_msg = AIChatMessage(
                        session_id=chat_session.id,
                        user_id=uid,
                        role="assistant",
                        message=str(final_payload.get("reply") or ""),
                        structured_response={
                            k: v for k, v in final_payload.items() if k != "type"
                        },
                    )
                    session.add(assistant_msg)
                    if not body.session_id:
                        chat_session.title = _session_title_from_message(body.message)
                    await session.commit()
                    await session.refresh(assistant_msg)

                    outfits = final_payload.get("recommended_outfits") or []
                    occasion = ctx.get("occasion") or "casual"
                    weather = ctx.get("location") or ""
                    for outfit in outfits[:2]:
                        item_ids = [
                            it.get("id")
                            for it in (outfit.get("items") or [])
                            if it.get("id")
                        ]
                        item_names = [
                            it.get("name")
                            for it in (outfit.get("items") or [])
                            if it.get("name")
                        ]
                        if item_ids:
                            try:
                                await save_outfit_history(
                                    session=session,
                                    user_id=user_id,
                                    occasion=occasion,
                                    weather=weather,
                                    selected_item_ids=item_ids,
                                    item_names=item_names,
                                    matching_score=outfit.get("matching_score"),
                                    recommendation_text=outfit.get("reasoning")
                                    or final_payload.get("reply")
                                    or "",
                                    improvement_tips=outfit.get("improvement_tips") or [],
                                )
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("stream_save_history_failed", error=str(exc))

                    yield _sse(
                        {
                            "type": "done",
                            "session_id": str(chat_session.id),
                            "message_id": str(assistant_msg.id),
                        }
                    )
                else:
                    yield _sse({"type": "error", "detail": "No structured response received"})

            except HTTPException as exc:
                yield _sse({"type": "error", "detail": exc.detail})
            except Exception as exc:  # noqa: BLE001
                logger.error("stream_endpoint_failed", error=str(exc), user_id=user_id)
                yield _sse({"type": "error", "detail": "AI stylist is temporarily unavailable"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


# ── Daily FANI nudges ─────────────────────────────────────────────────────────


@router.get("/nudges/today")
async def get_today_nudge(
    user_id: CurrentUser, session: DbSession
) -> dict[str, Any]:
    """Return today's proactive FANI nudge.

    Generates the nudge on first call of the day; subsequent calls return the
    cached row. Returns ``{"nudge": null}`` if the user has nothing actionable
    (empty wardrobe, AI unavailable) so the UI can hide the surface gracefully.
    """
    uid = UUID(user_id)
    nudge = await fetch_or_generate_today_nudge(session, uid)
    return {"nudge": serialize_nudge(nudge) if nudge else None}


@router.post("/nudges/{nudge_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_nudge(
    nudge_id: str, user_id: CurrentUser, session: DbSession
) -> dict[str, Any]:
    """Mark a nudge as dismissed so the UI hides it until tomorrow."""
    uid = UUID(user_id)
    try:
        nid = UUID(nudge_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid nudge id")

    result = await session.execute(
        select(DailyNudge).where(DailyNudge.id == nid, DailyNudge.user_id == uid)
    )
    nudge = result.scalar_one_or_none()
    if not nudge:
        raise HTTPException(status_code=404, detail="Nudge not found")

    nudge.dismissed = True
    await session.flush()
    return {"id": str(nudge.id), "dismissed": True}


@router.get("/history")
async def get_history(
    user_id: CurrentUser,
    session: DbSession,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Return the user's recent AI chat messages (across all sessions)."""
    uid = UUID(user_id)
    result = await session.execute(
        select(AIChatMessage)
        .where(AIChatMessage.user_id == uid)
        .order_by(desc(AIChatMessage.created_at))
        .limit(min(limit, 100))
        .offset(offset)
    )
    msgs = result.scalars().all()
    return {
        "count": len(msgs),
        "messages": [
            {
                "id": str(m.id),
                "session_id": str(m.session_id),
                "role": m.role,
                "message": m.message,
                "structured_response": m.structured_response,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    user_id: CurrentUser,
    session: DbSession,
) -> dict[str, Any]:
    """Record feedback on a recommended outfit. Improves future recommendations."""
    uid = UUID(user_id)

    outfit_uuid: UUID | None = None
    if body.outfit_id:
        try:
            outfit_uuid = UUID(body.outfit_id)
            # Validate this outfit belongs to the user
            res = await session.execute(
                select(Outfit).where(Outfit.id == outfit_uuid, Outfit.user_id == uid)
            )
            if not res.scalar_one_or_none():
                outfit_uuid = None
        except ValueError:
            outfit_uuid = None

    feedback = OutfitFeedback(
        user_id=uid,
        outfit_id=outfit_uuid,
        closet_item_ids=body.closet_item_ids or [],
        rating=body.rating,
        feedback_text=body.feedback_text,
        occasion=body.occasion,
        mood=body.mood,
        was_worn=body.was_worn,
    )
    session.add(feedback)
    await session.flush()
    await session.refresh(feedback)

    return {
        "id": str(feedback.id),
        "message": "Feedback recorded — thank you! This helps improve future recommendations.",
    }


@router.post("/save-outfit", status_code=status.HTTP_201_CREATED)
async def save_outfit(
    body: SaveOutfitRequest,
    user_id: CurrentUser,
    session: DbSession,
) -> dict[str, Any]:
    """Save an AI-recommended outfit to the user's outfits table."""
    uid = UUID(user_id)

    # Validate all item IDs belong to this user
    item_uuids: list[UUID] = []
    for raw_id in body.item_ids:
        try:
            item_uuids.append(UUID(raw_id))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid item id: {raw_id}")

    result = await session.execute(
        select(ClosetItem.id).where(
            ClosetItem.id.in_(item_uuids),
            ClosetItem.user_id == uid,
            ClosetItem.is_archived == False,  # noqa: E712
        )
    )
    valid_ids = {str(row) for row in result.scalars().all()}
    invalid = [str(i) for i in item_uuids if str(i) not in valid_ids]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Items not found in your closet: {invalid}",
        )

    outfit = Outfit(
        user_id=uid,
        name=body.name,
        occasion=body.occasion,
        item_ids=[str(i) for i in item_uuids],
        explanation=body.explanation or "",
        style_score=body.style_score or 0,
    )
    session.add(outfit)
    await session.flush()
    await session.refresh(outfit)

    logger.info("outfit_saved_from_chat", outfit_id=str(outfit.id), user_id=user_id)
    return {
        "id": str(outfit.id),
        "name": outfit.name,
        "occasion": outfit.occasion,
        "item_ids": outfit.item_ids,
        "style_score": outfit.style_score,
        "created_at": outfit.created_at.isoformat(),
        "message": "Outfit saved to your collection!",
    }
