"""RAG layer ORM models.

FashionKnowledgeDocument  — static fashion knowledge for general advice
OutfitHistory             — AI-generated outfit recommendations + user feedback
PackingMemory             — previous trip packing behavior
PurchaseGap               — detected wardrobe gaps
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
except ModuleNotFoundError:
    from sqlalchemy import JSON as _JSON

    def Vector(_: int) -> _JSON:  # type: ignore
        return _JSON()

from app.db.base import Base


class FashionKnowledgeDocument(Base):
    __tablename__ = "fashion_knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    season: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    occasion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OutfitHistory(Base):
    __tablename__ = "outfit_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occasion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    weather_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    selected_item_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    matching_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recommendation_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    improvement_tips: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    was_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    was_worn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PackingMemory(Base):
    __tablename__ = "packing_memory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trip_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trips.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    destination: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    start_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    purpose: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    weather_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    packed_item_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    missing_items: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    saved_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("packing_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PurchaseGap(Base):
    __tablename__ = "purchase_gaps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gap_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # outfit | trip_packing | seasonal | occasion
    missing_category: Mapped[str] = mapped_column(String(100), nullable=False)
    missing_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    missing_season: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    missing_occasion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority_score: Mapped[float] = mapped_column(
        Numeric(4, 2), nullable=False, default=0.5
    )
    source_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    suggested_attributes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
