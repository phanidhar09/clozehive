"""
User, UserCredential, and RefreshToken ORM models.
"""

from __future__ import annotations

from typing import Optional

import uuid
from datetime import timezone, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    google_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)

    # ── Personalization profile (JSONB; nullable for backwards compat) ────────
    # body_profile  — height/weight/body_type/preferred_fit/sizes
    # style_profile — initial styles + behaviorally-learned style classification
    # preferences   — favorite_colors, dislikes, occasion_focus, etc.
    # permissions   — { location: bool, calendar: bool, location_coords?: ..., timezone?: ... }
    body_profile: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    style_profile: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    permissions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    avatar_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    credential: Mapped[Optional[UserCredential]] = relationship(
        "UserCredential", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    closet_items: Mapped[list["ClosetItem"]] = relationship(
        "ClosetItem", back_populates="owner", cascade="all, delete-orphan"
    )
    # following: Mapped[list["Follow"]] = relationship(  # Non-MVP social features disabled for launch stabilization
    #     "Follow", foreign_keys="Follow.follower_id", back_populates="follower", cascade="all, delete-orphan"
    # )
    # followers: Mapped[list["Follow"]] = relationship(  # Non-MVP social features disabled for launch stabilization
    #     "Follow", foreign_keys="Follow.following_id", back_populates="following", cascade="all, delete-orphan"
    # )
    # owned_groups: Mapped[list["Group"]] = relationship(  # Non-MVP social features disabled for launch stabilization
    #     "Group", back_populates="owner", cascade="all, delete-orphan"
    # )
    # group_memberships: Mapped[list["GroupMember"]] = relationship(  # Non-MVP social features disabled for launch stabilization
    #     "GroupMember", back_populates="user", cascade="all, delete-orphan"
    # )


class UserCredential(Base):
    __tablename__ = "user_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="credential")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")
