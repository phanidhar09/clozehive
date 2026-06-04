"""
Async SQLAlchemy session factory + connection pool.

Transaction policy
------------------
``get_session()`` is the **single owner** of commit/rollback for normal HTTP
handlers that depend on it:

- Handlers and services should use ``session.add`` / ``session.delete``,
  ``await session.flush()`` when IDs are needed before commit, and
  ``await session.refresh(obj)`` after flush when returning ORM objects.
- **Do not** call ``session.commit()`` from services or from routes except
  for documented exceptions below.

A second commit at the end of the request (from ``get_session``) is harmless:
the session begins a new transaction after an explicit commit, and an empty
commit is a no-op.

Background tasks that run **after** the response must not rely on the request
session lifecycle; use :func:`app.services.similarity_service.update_item_embedding_job`
or open a new ``AsyncSessionLocal`` scope there.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: F401 — registers all ORM mappers before any query runs
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("db.session")
settings = get_settings()

# ── Engine (singleton, shared across workers) ────────────────────────────────

_is_sqlite = settings.database_url.startswith("sqlite")


def _db_ssl_context() -> ssl.SSLContext:
    """TLS context for the production Postgres connection.

    Render's *internal* Postgres endpoint (host like ``dpg-xxxx-a``) presents a
    self-signed / private-CA certificate, so full verification fails with
    "certificate verify failed: self-signed certificate". We keep the connection
    encrypted but skip certificate verification — safe because the link never
    leaves Render's private network. (A publicly-trusted DB like Neon would verify
    fine, but disabling verify here keeps both cases working.)
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# SQLite (used in tests) does not support pool_size / max_overflow / pool_timeout.
_engine_kwargs: dict = {"echo": settings.debug, "future": True}
if not _is_sqlite:
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=settings.db_pool_pre_ping,
        pool_recycle=settings.db_pool_recycle,
        pool_timeout=settings.db_pool_timeout,
        connect_args={"ssl": _db_ssl_context(), "statement_cache_size": 0} if settings.is_production else {},
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)

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
    """Yield a request-scoped session; commit on success, rollback on errors."""
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
        # Never log credentials — host/db fragment only
        logger.info("database_connected", target=settings.database_url.split("@")[-1])
    except Exception as exc:
        logger.error("database_connection_failed", error=str(exc))
        raise


async def disconnect() -> None:
    await engine.dispose()
    logger.info("database_disconnected")
