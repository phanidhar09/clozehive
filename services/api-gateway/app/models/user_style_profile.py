"""Persisted style profile for personalization (onboarding + settings)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserStyleProfile(Base):
    __tablename__ = "user_style_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    custom_gender: Mapped[str | None] = mapped_column(String(120), nullable=True)

    height_value: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    height_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)

    weight_value: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    weight_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)

    age_range: Mapped[str | None] = mapped_column(String(32), nullable=True)

    body_types: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    custom_body_type: Mapped[str | None] = mapped_column(String(200), nullable=True)

    fit_preferences: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    custom_fit_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    size_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    custom_size_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    style_preferences: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    favorite_colors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    avoided_colors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    neutral_color_preference: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bold_color_preference: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    occasion_preferences: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    climate_preferences: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    onboarding_skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # AI-generated natural-language summary of this user's style preferences.
    # Regenerated automatically on every profile save.
    style_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
