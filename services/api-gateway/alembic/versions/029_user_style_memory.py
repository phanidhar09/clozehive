"""Add user_style_memory: persistent per-user style/preference facts for FANI.

Stores short natural-language preference facts ("dislikes the colour yellow",
"prefers smart-casual for work") that the ai-agent retrieves on every chat so
FANI feels like it remembers the user across sessions instead of re-deriving
context from the per-request history each turn.

Revision ID: 029
Revises: 028
Create Date: 2026-06-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def _try_execute(conn: sa.engine.Connection, sql: str) -> bool:
    """Run a statement inside a savepoint so a missing pgvector extension is
    non-fatal (the embedding column then stays TEXT and retrieval falls back to
    most-recent ordering)."""
    conn.execute(sa.text("SAVEPOINT _style_mem_stmt"))
    try:
        conn.execute(sa.text(sql))
        conn.execute(sa.text("RELEASE SAVEPOINT _style_mem_stmt"))
        return True
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _style_mem_stmt"))
        return False


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "user_style_memory",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Short first-person-free fact, e.g. "Dislikes the colour yellow".
        sa.Column("content", sa.Text(), nullable=False),
        # color_pref | style_pref | fit_pref | occasion | dislike | brand | general
        sa.Column("kind", sa.String(40), nullable=False, server_default="general"),
        sa.Column("source", sa.String(40), nullable=False, server_default="chat"),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("idx_user_style_memory_user_id", "user_style_memory", ["user_id"])
    op.create_index(
        "idx_user_style_memory_user_created",
        "user_style_memory",
        ["user_id", "created_at"],
    )

    _try_execute(
        conn,
        "ALTER TABLE user_style_memory "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector",
    )
    _try_execute(
        conn,
        "CREATE INDEX idx_user_style_memory_embedding ON user_style_memory "
        "USING hnsw (embedding vector_cosine_ops)",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_style_memory_embedding")
    op.execute("DROP INDEX IF EXISTS idx_user_style_memory_user_created")
    op.execute("DROP INDEX IF EXISTS idx_user_style_memory_user_id")
    op.drop_table("user_style_memory")
