"""
Group and GroupMember ORM models.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _invite_code() -> str:
    """Generate an 8-character uppercase invite code."""
    return secrets.token_hex(4).upper()


class GroupRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invite_code: Mapped[str] = mapped_column(
        String(16), unique=True, nullable=False, default=_invite_code
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    members: Mapped[List["GroupMember"]] = relationship(
        "GroupMember", back_populates="group", cascade="all, delete-orphan"
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[creator_id]
    )

    def __repr__(self) -> str:
        return f"<Group id={self.id} name={self.name!r}>"


class GroupMember(Base):
    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[GroupRole] = mapped_column(
        Enum(GroupRole, name="group_role_enum"), default=GroupRole.member, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    group: Mapped["Group"] = relationship("Group", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="group_memberships")

    def __repr__(self) -> str:
        return f"<GroupMember user={self.user_id} group={self.group_id} role={self.role}>"
