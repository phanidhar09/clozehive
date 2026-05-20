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

import uuid
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, desc

from fastapi import BackgroundTasks

from app.core.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.ai_chat import AIChatMessage, AIChatSession, OutfitFeedback
from app.models.closet import ClosetItem, Outfit
from app.services.ai_stylist_chat_service import process_chat_message
from app.services.outfit_history_service import save_outfit_history_background

router = APIRouter(prefix="/ai-chat", tags=["AI Chat"])
logger = get_logger("ai_chat.routes")

_limiter = Limiter(key_func=get_remote_address)

# ── Request / Response Schemas ────────────────────────────────────────────────


class ChatContext(BaseModel):
    occasion: Optional[str] = None
    mood: Optional[str] = None
    location: Optional[str] = None
    weather_required: bool = False


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None  # if None, creates a new session
    context: Optional[ChatContext] = None
    history: list[dict[str, str]] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    closet_item_ids: list[str] = Field(default_factory=list)
    outfit_id: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    feedback_text: Optional[str] = Field(None, max_length=1000)
    occasion: Optional[str] = None
    mood: Optional[str] = None
    was_worn: bool = False


class SaveOutfitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    item_ids: list[str] = Field(..., min_items=1)
    occasion: str = "casual"
    explanation: Optional[str] = None
    style_score: Optional[int] = Field(None, ge=0, le=100)
    session_id: Optional[str] = None


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
    await session.commit()
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
async def send_message(
    body: SendMessageRequest,
    user_id: CurrentUser,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Send a message to the AI Stylist and receive outfit recommendations.

    Rate limit: 20 requests/minute per IP.
    """
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

    await session.commit()
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
        "purchase_gaps": ai_response.get("purchase_gaps") or [],
        "follow_up_questions": ai_response.get("follow_up_questions") or [],
    }


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

    outfit_uuid: Optional[UUID] = None
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
    await session.commit()
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
    await session.commit()
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
