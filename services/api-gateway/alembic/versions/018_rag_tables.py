"""Add RAG layer tables: fashion_knowledge_documents, outfit_history, packing_memory, purchase_gaps.

Revision ID: 018
Revises: 017
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def _try_execute(conn: sa.engine.Connection, sql: str) -> bool:
    conn.execute(sa.text("SAVEPOINT _rag_stmt"))
    try:
        conn.execute(sa.text(sql))
        conn.execute(sa.text("RELEASE SAVEPOINT _rag_stmt"))
        return True
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _rag_stmt"))
        return False


def upgrade() -> None:
    conn = op.get_bind()

    # ── fashion_knowledge_documents ───────────────────────────────────────────
    op.create_table(
        "fashion_knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("season", sa.String(50), nullable=True),
        sa.Column("occasion", sa.String(100), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_fkd_category", "fashion_knowledge_documents", ["category"])
    op.create_index("idx_fkd_title", "fashion_knowledge_documents", ["title"])

    # cast embedding column to vector(1536) if pgvector is available
    _try_execute(conn,
        "ALTER TABLE fashion_knowledge_documents "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    _try_execute(conn,
        "CREATE INDEX idx_fkd_embedding ON fashion_knowledge_documents "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── outfit_history ────────────────────────────────────────────────────────
    op.create_table(
        "outfit_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occasion", sa.String(100), nullable=True),
        sa.Column("weather_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("selected_item_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("matching_score", sa.Integer(), nullable=True),
        sa.Column("recommendation_text", sa.Text(), nullable=True),
        sa.Column("improvement_tips", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("was_saved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("was_worn", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_outfit_history_user_id", "outfit_history", ["user_id"])
    op.create_index("idx_outfit_history_occasion", "outfit_history", ["occasion"])
    op.create_index("idx_outfit_history_created_at", "outfit_history", ["created_at"])

    _try_execute(conn,
        "ALTER TABLE outfit_history "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    _try_execute(conn,
        "CREATE INDEX idx_outfit_history_embedding ON outfit_history "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── packing_memory ────────────────────────────────────────────────────────
    op.create_table(
        "packing_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="SET NULL"), nullable=True),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("start_date", sa.String(10), nullable=True),
        sa.Column("end_date", sa.String(10), nullable=True),
        sa.Column("purpose", sa.String(50), nullable=True),
        sa.Column("weather_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("packed_item_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("missing_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("saved_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("packing_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_feedback", sa.Text(), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_packing_memory_user_id", "packing_memory", ["user_id"])
    op.create_index("idx_packing_memory_trip_id", "packing_memory", ["trip_id"])
    op.create_index("idx_packing_memory_destination", "packing_memory", ["destination"])

    _try_execute(conn,
        "ALTER TABLE packing_memory "
        "ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector"
    )
    _try_execute(conn,
        "CREATE INDEX idx_packing_memory_embedding ON packing_memory "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # ── purchase_gaps ─────────────────────────────────────────────────────────
    op.create_table(
        "purchase_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gap_type", sa.String(50), nullable=False),
        sa.Column("missing_category", sa.String(100), nullable=False),
        sa.Column("missing_color", sa.String(50), nullable=True),
        sa.Column("missing_season", sa.String(50), nullable=True),
        sa.Column("missing_occasion", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("priority_score", sa.Numeric(4, 2), nullable=False, server_default="0.5"),
        sa.Column("source_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("suggested_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_purchase_gaps_user_id", "purchase_gaps", ["user_id"])
    op.create_index("idx_purchase_gaps_resolved", "purchase_gaps", ["resolved"])
    op.create_index("idx_purchase_gaps_gap_type", "purchase_gaps", ["gap_type"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_purchase_gaps_gap_type")
    op.execute("DROP INDEX IF EXISTS idx_purchase_gaps_resolved")
    op.execute("DROP INDEX IF EXISTS idx_purchase_gaps_user_id")
    op.drop_table("purchase_gaps")

    op.execute("DROP INDEX IF EXISTS idx_packing_memory_embedding")
    op.execute("DROP INDEX IF EXISTS idx_packing_memory_destination")
    op.execute("DROP INDEX IF EXISTS idx_packing_memory_trip_id")
    op.execute("DROP INDEX IF EXISTS idx_packing_memory_user_id")
    op.drop_table("packing_memory")

    op.execute("DROP INDEX IF EXISTS idx_outfit_history_embedding")
    op.execute("DROP INDEX IF EXISTS idx_outfit_history_created_at")
    op.execute("DROP INDEX IF EXISTS idx_outfit_history_occasion")
    op.execute("DROP INDEX IF EXISTS idx_outfit_history_user_id")
    op.drop_table("outfit_history")

    op.execute("DROP INDEX IF EXISTS idx_fkd_embedding")
    op.execute("DROP INDEX IF EXISTS idx_fkd_title")
    op.execute("DROP INDEX IF EXISTS idx_fkd_category")
    op.drop_table("fashion_knowledge_documents")
