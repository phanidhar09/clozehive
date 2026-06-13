"""Add planned_outfits: one weather-aware planned outfit per user per day.

Backs the weekly outfit calendar — FANI generates a 7-day plan from the local
forecast and the user's closet; users can override single days, and marking a
day as worn feeds wear_count / outfit history.

Revision ID: 030
Revises: 029
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_outfits",
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
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("item_ids", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("occasion", sa.String(100), nullable=True),
        sa.Column("weather_condition", sa.String(100), nullable=True),
        sa.Column("temp_high", sa.Numeric(5, 1), nullable=True),
        sa.Column("temp_low", sa.Numeric(5, 1), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="fani"),
        sa.Column("is_worn", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "plan_date", name="uq_planned_outfits_user_date"),
    )
    op.create_index("idx_planned_outfits_user_id", "planned_outfits", ["user_id"])
    op.create_index("idx_planned_outfits_plan_date", "planned_outfits", ["plan_date"])


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_planned_outfits_plan_date")
    op.execute("DROP INDEX IF EXISTS idx_planned_outfits_user_id")
    op.drop_table("planned_outfits")
