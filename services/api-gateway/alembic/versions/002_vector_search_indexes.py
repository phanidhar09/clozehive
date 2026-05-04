"""Add pgvector support and scale-oriented indexes.

Revision ID: 002
Revises: 001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _try_execute(conn: sa.engine.Connection, sql: str) -> bool:
    """Run SQL inside a savepoint. Returns True on success, False if it fails.

    When a statement fails inside a Postgres transaction the whole transaction
    is aborted.  Rolling back to a savepoint un-aborts it so the surrounding
    migration can continue.
    """
    conn.execute(sa.text("SAVEPOINT _optional_stmt"))
    try:
        conn.execute(sa.text(sql))
        conn.execute(sa.text("RELEASE SAVEPOINT _optional_stmt"))
        return True
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _optional_stmt"))
        return False


def upgrade() -> None:
    # pgvector is optional — similarity search degrades gracefully without it.
    # Production always has the extension; local PG14 may not.  We use
    # savepoints so a missing extension doesn't abort the outer transaction.
    conn = op.get_bind()

    vector_available = _try_execute(conn, 'CREATE EXTENSION IF NOT EXISTS "vector"')
    _try_execute(conn, 'CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    op.create_table(
        "closet_item_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("closet_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("closet_items.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    if vector_available:
        conn.execute(sa.text(
            "ALTER TABLE closet_item_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
        ))
        conn.execute(sa.text(
            "CREATE INDEX idx_closet_item_embeddings_vector "
            "ON closet_item_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        ))

    op.create_index("idx_closet_item_embeddings_user_id", "closet_item_embeddings", ["user_id"])
    op.create_index("idx_outfits_user_id", "outfits", ["user_id"])
    _try_execute(conn, "CREATE INDEX idx_users_username_trgm ON users USING gin (username gin_trgm_ops)")
    _try_execute(conn, "CREATE INDEX idx_users_name_trgm ON users USING gin (name gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_users_username_trgm")
    op.drop_index("idx_outfits_user_id", table_name="outfits")
    op.drop_index("idx_closet_item_embeddings_user_id", table_name="closet_item_embeddings")
    op.execute("DROP INDEX IF EXISTS idx_closet_item_embeddings_vector")
    op.drop_table("closet_item_embeddings")
