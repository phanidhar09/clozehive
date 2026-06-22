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
    # its lock — e.g. an orphaned Postgres backend from an earlier interrupted
    # migration still holding the alembic_version/table lock, or two booting
    # instances racing `upgrade head`. Startup migrations run inside the FastAPI
    # lifespan (before the port binds), so an unbounded wait means the health
    # check never passes and Render restarts the instance → boot loop. lock_timeout
    # bounds only the WAIT to acquire a lock, never how long a migration may run,
    # so legitimately long migrations are unaffected. A blocked migration now
    # errors after 15s; with FAIL_ON_STARTUP_MIGRATION_ERROR=false the app still
    # boots and self-heals once the lock clears.
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql("SET lock_timeout = '15s'")
    # Commit after EACH migration rather than wrapping the whole chain in one
    # transaction. A single giant transaction means nothing persists until the
    # final commit — so if the boot is interrupted mid-upgrade (a redeploy, an
    # instance restart) the entire chain rolls back and the next boot starts from
    # an empty DB, re-running 001→head forever without ever landing. Per-migration
    # commits make progress durable and resumable: alembic_version advances step
    # by step, so an interrupted upgrade picks up where it left off.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        transaction_per_migration=True,
    )
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
        # The `SET lock_timeout` in do_run_migrations autobegins a transaction on
        # the async connection before alembic configures its own per-migration
        # transactions. SQLAlchemy's "commit as you go" leaves that outer async
        # transaction open, so exiting this block would ROLL BACK the whole
        # upgrade (alembic_version advances in-memory but never persists). Commit
        # explicitly so applied migrations are durable.
        await connection.commit()
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
