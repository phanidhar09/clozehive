"""Add closet item embeddings and HNSW index.

Revision ID: 007
Revises: 006
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def _try_execute(conn: sa.engine.Connection, sql: str) -> bool:
    conn.execute(sa.text("SAVEPOINT _optional_stmt"))
    try:
        conn.execute(sa.text(sql))
        conn.execute(sa.text("RELEASE SAVEPOINT _optional_stmt"))
        return True
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _optional_stmt"))
        return False


def upgrade() -> None:
    conn = op.get_bind()
    if not _try_execute(conn, "CREATE EXTENSION IF NOT EXISTS vector"):
        return  # pgvector not installed; skip embedding column and HNSW index

    _try_execute(conn, "ALTER TABLE closet_items ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    _try_execute(conn, """
        CREATE INDEX IF NOT EXISTS ix_closet_items_embedding_hnsw
        ON closet_items
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_closet_items_embedding_hnsw")
    op.execute("ALTER TABLE closet_items DROP COLUMN IF EXISTS embedding")
