"""Add planned_outfits: one weather-aware planned outfit per user per day.

Mirror of api-gateway migration 030 (weekly outfit calendar). No FK to users —
the users table lives in the api-gateway database; cleanup happens via the
internal purge seam.

Revision ID: 0002_planned_outfits
Revises: 7ec4e74c47bb
Create Date: 2026-06-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_planned_outfits"
down_revision: Union[str, None] = "7ec4e74c47bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planned_outfits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
