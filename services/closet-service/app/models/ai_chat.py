"""ORM models for the CLOZEHIVE AI Stylist Chat feature.

AIChatSession   — a named conversation thread per user
AIChatMessage   — individual messages within a session
OutfitFeedback  — user ratings on AI-recommended outfits
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from datetime import date as date_type
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        # No FK: users live in the api-gateway DB (cleanup via internal purge seam).
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Rolling LLM-generated summary of older turns once a session exceeds the
    # short-window threshold. Lets unlimited-length conversations stay coherent
    # without blowing the context budget.
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Number of historical messages already folded into `summary` so we only
    # ever summarise *new* turns on each pass.
    summary_through_msg_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DailyNudge(Base):
    """One proactive FANI message per user per day.

    Generated lazily: the first request to /ai-chat/nudges/today on a given
    date triggers generation based on weather, recent additions, unworn items,
    and upcoming calendar events. Users can dismiss to suppress until tomorrow.
    """

    __tablename__ = "daily_nudges"
    __table_args__ = (
        UniqueConstraint("user_id", "nudge_date", name="uq_daily_nudges_user_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        # No FK: users live in the api-gateway DB (cleanup via internal purge seam).
        UUID(as_uuid=True),
        nullable=False,
    )
    nudge_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # weather_outfit | new_arrival | unworn_pick | calendar_prep | streak | generic
    nudge_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        # No FK: users live in the api-gateway DB (cleanup via internal purge seam).
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured outfit recommendations and follow-up questions from the assistant
    structured_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class OutfitFeedback(Base):
    __tablename__ = "outfit_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        # No FK: users live in the api-gateway DB (cleanup via internal purge seam).
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    # nullable — feedback can be on an ad-hoc AI recommendation (no saved outfit row yet)
    outfit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outfits.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The closet item IDs that made up the outfit at feedback time
    closet_item_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # 1–5 star rating
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occasion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    mood: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    was_worn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
