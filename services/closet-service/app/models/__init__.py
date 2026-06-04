"""ORM models for closet-service.

Imported by ``app.db.session`` (and alembic ``env.py``) to register all
SQLAlchemy mappers on ``Base.metadata`` before any query or autogenerate runs.

These tables carry a plain ``user_id UUID`` column with NO foreign key to a
users table — users live in the api-gateway database. Referential cleanup on
account deletion is handled by the internal purge seam, not ON DELETE CASCADE.
"""

from __future__ import annotations

from app.models import (  # noqa: F401 — imported for mapper registration
    ai_chat,
    closet,
    packing,
    rag,
    trips,
    user_style_profile,
)

__all__ = ["ai_chat", "closet", "packing", "rag", "trips", "user_style_profile"]
