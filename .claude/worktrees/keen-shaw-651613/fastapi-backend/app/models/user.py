"""
User and RefreshToken ORM models.

Security fields added:
  role                  — RBAC: 'user' | 'admin'
  last_login            — audit trail, shown in admin dashboards
  failed_login_attempts — incremented on bad password; reset on success
  locked_until          — account temporarily locked after MAX_LOGIN_ATTEMPTS failures
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.social import Follow
    from app.models.group import GroupMember
    from app.models.closet import ClosetItem


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class UserRole(str, enum.Enum):
    """
    RBAC roles.  Using a string enum means the DB stores a human-readable
    value ('user'/'admin') and Python comparisons work with plain strings.
    """
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── RBAC ─────────────────────────────────────────────────────────────────
    # Default every new account to USER; promote via admin tooling or migration.
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), default=UserRole.USER, nullable=False
    )

    # ── Security / audit ─────────────────────────────────────────────────────
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Counts consecutive bad-password attempts; reset to 0 on successful login.
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Non-null while the account is temporarily locked.
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    followers: Mapped[List["Follow"]] = relationship(
        "Follow",
        foreign_keys="Follow.following_id",
        back_populates="following",
        cascade="all, delete-orphan",
    )
    following: Mapped[List["Follow"]] = relationship(
        "Follow",
        foreign_keys="Follow.follower_id",
        back_populates="follower",
        cascade="all, delete-orphan",
    )
    group_memberships: Mapped[List["GroupMember"]] = relationship(
        "GroupMember", back_populates="user", cascade="all, delete-orphan"
    )
    closet_items: Mapped[List["ClosetItem"]] = relationship(
        "ClosetItem", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
