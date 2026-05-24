"""
ClosetItem and Outfit ORM models.
"""

from __future__ import annotations

import uuid
from datetime import timezone, date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
try:
    from pgvector.sqlalchemy import Vector
except ModuleNotFoundError:  # Allows local syntax/import checks before requirements are installed.
    from sqlalchemy import JSON as _JSON

    def Vector(_: int) -> _JSON:  # type: ignore
        return _JSON()

from app.db.base import Base


class ClosetItem(Base):
    __tablename__ = "closet_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fabric: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pattern: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    season: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    occasion: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    eco_score: Mapped[Optional[float]] = mapped_column(Numeric(3, 1), nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    section: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True, index=False)
    wear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_worn: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Vision pipeline fields (added in migration 008) ───────────────────────
    original_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    background_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    background_removal_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    analysis_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Numeric(4, 2), nullable=True)
    scan_batch_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship("User", back_populates="closet_items")


class Outfit(Base):
    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    occasion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    item_ids: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    style_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

