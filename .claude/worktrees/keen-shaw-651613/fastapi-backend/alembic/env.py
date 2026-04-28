"""
Alembic migration environment.
Reads SYNC_DATABASE_URL from .env (psycopg2 driver, not asyncpg).
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# Load .env so DATABASE_URL is available
load_dotenv()

from app.db.base import Base  # noqa: E402
from app.models import user, social, group, closet  # noqa: E402, F401 — register metadata

config = context.config

# Override URL from environment
sync_url = os.environ.get("SYNC_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
