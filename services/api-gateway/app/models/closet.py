"""
ClosetItem and Outfit ORM models.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

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
    color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fabric: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(100), nullable=True)
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)
    occasion: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    eco_score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    wear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_worn: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occasion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
