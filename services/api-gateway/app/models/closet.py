"""
ClosetItem and Outfit ORM models.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ModuleNotFoundError:  # Allows local syntax/import checks before requirements are installed.
    from sqlalchemy import JSON as _JSON

    def Vector(_: int) -> _JSON:
        return _JSON()


from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class ClosetItem(Base):
    __tablename__ = "closet_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    season: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    occasion: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    eco_score: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Garment fit (slim/regular/relaxed/oversized/tailored). Detected by the
    # vision pipeline; combined with brand+size to resolve true measurements.
    fit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Canonical measurements in cm (chest/waist/inseam/length), null until
    # resolved from a brand size chart or user input. See migration 036.
    measurements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    section: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True, index=False)
    wear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_worn: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Physical availability: available | in_laundry | at_cleaners | lent_out
    # (see app.constants.wardrobe.Availability). FANI only styles available items.
    availability: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available", server_default="available"
    )

    # ── Vision pipeline fields (added in migration 008) ───────────────────────
    original_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    background_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    background_removal_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    analysis_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)
    scan_batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[User] = relationship("User", back_populates="closet_items")


class WearEvent(Base):
    """Append-only wear history — one row per item per time it's worn.

    ClosetItem.wear_count / last_worn are a destructive rollup (a counter and a
    single date); they can't reconstruct *when* something was worn. This table is
    the source of truth for time-series analytics: cost-per-wear over time,
    utilization, streaks, and the weekly recap. Both write paths that bump the
    rollup (manual log_wear and the planner's mark-worn) also append here.
    """

    __tablename__ = "wear_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("closet_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    worn_on: Mapped[date] = mapped_column(Date, nullable=False)
    # Loose link back to the outfit (planned_outfit or saved outfit) that drove
    # the wear, when one exists. Kept FK-free on purpose — it may point at either
    # table, and analytics only ever reads it for grouping, never joins on it.
    outfit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # manual | planner
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Outfit(Base):
    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PlannedOutfit(Base):
    """One planned outfit per user per calendar day (weekly outfit planner)."""

    __tablename__ = "planned_outfits"
    # The unique constraint doubles as the composite (user_id, plan_date) index,
    # which serves every planner query — so user_id / plan_date carry no separate
    # index=True (would be redundant write overhead; see migration 032).
    __table_args__ = (UniqueConstraint("user_id", "plan_date", name="uq_planned_outfits_user_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    item_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    occasion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Forecast snapshot at planning time — keeps the day card explainable even
    # after the live forecast shifts.
    weather_condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temp_high: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    temp_low: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="fani")  # fani | manual
    is_worn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
