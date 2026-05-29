"""Add virtual_tryon_sessions table.

Revision ID: 026
Revises: 025
Create Date: 2026-05-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "virtual_tryon_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Optionally linked to a specific closet item (the garment being tried on).
        sa.Column(
            "closet_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("closet_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # URL of the user's photo (stored in GCS or as a signed upload URL)
        sa.Column("person_image_url", sa.Text, nullable=False),
        # URL of the garment image (GCS or external)
        sa.Column("garment_image_url", sa.Text, nullable=False),
        # pending | processing | completed | failed
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # fal.ai async request ID — used to poll the queue endpoint
        sa.Column("fal_request_id", sa.String(255), nullable=True),
        # Final result image URL (GCS) — set when status = completed
        sa.Column("result_image_url", sa.Text, nullable=True),
        # Error detail when status = failed
        sa.Column("error_message", sa.Text, nullable=True),
        # User-visible label ("Beach Holiday Look", etc.)
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_vt_sessions_user_id", "virtual_tryon_sessions", ["user_id"])
    op.create_index("ix_vt_sessions_status", "virtual_tryon_sessions", ["status"])
    op.create_index(
        "ix_vt_sessions_closet_item_id", "virtual_tryon_sessions", ["closet_item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_vt_sessions_closet_item_id", table_name="virtual_tryon_sessions")
    op.drop_index("ix_vt_sessions_status", table_name="virtual_tryon_sessions")
    op.drop_index("ix_vt_sessions_user_id", table_name="virtual_tryon_sessions")
    op.drop_table("virtual_tryon_sessions")
