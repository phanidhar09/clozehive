"""Add shopping_checks table for in-store buy/skip recommendations.

Revision ID: 024
Revises: 023
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("item_analysis", postgresql.JSONB, nullable=True),
        sa.Column("matched_items", postgresql.JSONB, nullable=True),
        sa.Column("buy_score", sa.Float, nullable=True),
        sa.Column("buy_recommendation", sa.String(20), nullable=True),
        sa.Column("closet_boost_pct", sa.Float, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("purchase_decision", sa.Boolean, nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_shopping_checks_user_id", "shopping_checks", ["user_id"])
    op.create_index("ix_shopping_checks_created_at", "shopping_checks", ["created_at"])
    op.create_index("ix_shopping_checks_purchase_decision", "shopping_checks", ["purchase_decision"])


def downgrade() -> None:
    op.drop_table("shopping_checks")
