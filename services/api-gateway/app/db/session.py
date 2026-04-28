"""
Async SQLAlchemy session factory + connection pool.
Use get_session() as a FastAPI dependency to get a per-request session.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("db.session")
settings = get_settings()

# ── Engine (singleton, shared across workers) ────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=settings.db_pool_pre_ping,
    echo=settings.debug,
    future=True,
)

# ── Session factory ───────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session; rolls back on error, always closes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Lifecycle helpers ─────────────────────────────────────────────────────────

async def connect() -> None:
    """Verify the database is reachable on startup."""
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("database_connected", url=settings.database_url.split("@")[-1])
    except Exception as exc:
        logger.error("database_connection_failed", error=str(exc))
        raise


async def disconnect() -> None:
    await engine.dispose()
    logger.info("database_disconnected")
