"""Add purge_outbox for the account-deletion saga (durable cross-service purge).

Transactional outbox: a row is written in the same transaction as the user
deletion, so the intent to purge downstream data (closet-service) is never lost
even if the inline purge call fails. A reconciliation sweep retries pending rows
until they succeed or exhaust attempts (then 'failed' for manual intervention).

Deliberately NO foreign key to users — the user row is gone by design; this
record must outlive it.

Revision ID: 028
Revises: 027
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purge_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        # No FK — the user is deleted; this is just the subject id to purge.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target", sa.String(40), nullable=False),  # e.g. "closet_service"
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),  # pending|done|failed
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # The sweep scans by status; index it.
    op.create_index("ix_purge_outbox_status", "purge_outbox", ["status"])


def downgrade() -> None:
    op.drop_table("purge_outbox")
