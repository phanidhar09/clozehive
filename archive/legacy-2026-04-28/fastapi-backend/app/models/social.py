"""
Social graph: Follow relationship.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_follows_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    following_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    follower: Mapped["User"] = relationship(
        "User", foreign_keys=[follower_id], back_populates="following"
    )
    following: Mapped["User"] = relationship(
        "User", foreign_keys=[following_id], back_populates="followers"
    )

    def __repr__(self) -> str:
        return f"<Follow {self.follower_id} → {self.following_id}>"
