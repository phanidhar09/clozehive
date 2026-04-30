"""
Async SQLAlchemy engine + session factory.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Engine ───────────────────────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,        # detect stale connections
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,         # recycle connections every hour
)

# ── Session factory ──────────────────────────────────────────────────────────
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,    # objects stay usable after commit
    autoflush=False,
)
