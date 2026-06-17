"""Alembic environment — async SQLAlchemy 2.0 compatible."""

import asyncio
import ssl as _ssl
from logging.config import fileConfig
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from app.core.config import get_settings
from app.db.base import Base

# Import models so Alembic can auto-detect them
from app.models import user, closet, social, trips  # noqa: F401

config = context.config
settings = get_settings()

# Strip ssl/sslmode query params — asyncpg doesn't accept them in the URL;
# SSL is passed via connect_args instead.
def _clean_url(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs.pop("ssl", None)
    qs.pop("sslmode", None)
    cleaned = parsed._replace(query=urlencode(qs, doseq=True))
    return urlunparse(cleaned)

_db_url = _clean_url(settings.database_url)
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Fail fast instead of hanging the boot forever if a migration can't acquire
    # its lock — e.g. the previous instance still holds it during a deploy
    # overlap, or two booting instances race `upgrade head`. Without this,
    # startup `command.upgrade` blocks indefinitely, the FastAPI lifespan never
    # completes, the port never binds, the health check fails, and Render
    # restarts the instance → silent boot loop. lock_timeout bounds only the
    # WAIT to acquire a lock (not how long a migration may run), so it never
    # kills a legitimately long migration. A blocked migration now errors after
    # 15s; the next restart retries once the conflicting lock is released.
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET lock_timeout = '15s'")
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Use SSL connect_args for cloud databases (Neon, Supabase, etc.)
    _needs_ssl = any(h in settings.database_url for h in ("neon.tech", "supabase.com", "render.com"))
    _connect_args = {"ssl": _ssl.create_default_context(), "statement_cache_size": 0} if _needs_ssl else {}

    connectable = create_async_engine(
        _db_url,
        poolclass=pool.NullPool,
        connect_args=_connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
