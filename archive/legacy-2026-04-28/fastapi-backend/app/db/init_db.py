"""
Database initialisation — creates all tables that don't exist yet.
Run this on startup (development) or use Alembic migrations (production).
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.session import engine

# Import ALL models so their metadata is registered before create_all
from app.models import user, social, group, closet  # noqa: F401

logger = logging.getLogger("clozehive.db")


async def create_all_tables(bind: AsyncEngine | None = None) -> None:
    target = bind or engine
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified.")


async def drop_all_tables(bind: AsyncEngine | None = None) -> None:
    """DANGER: only for test teardown."""
    target = bind or engine
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("All database tables DROPPED.")
