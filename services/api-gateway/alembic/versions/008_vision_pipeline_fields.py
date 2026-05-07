"""Add vision pipeline fields to closet_items.

Revision ID: 008
Revises: 007_add_closet_embedding_hnsw
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("closet_items", sa.Column("original_image_url", sa.Text, nullable=True))
    op.add_column("closet_items", sa.Column("processed_image_url", sa.Text, nullable=True))
    op.add_column("closet_items", sa.Column("background_removed", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("closet_items", sa.Column("background_removal_status", sa.String(20), nullable=True))
    op.add_column("closet_items", sa.Column("analysis_source", sa.String(50), nullable=True))
    op.add_column("closet_items", sa.Column("confidence_score", sa.Numeric(4, 2), nullable=True))
    op.add_column("closet_items", sa.Column("scan_batch_id", sa.String(36), nullable=True))
    op.create_index("idx_closet_items_scan_batch_id", "closet_items", ["scan_batch_id"])


def downgrade() -> None:
    op.drop_index("idx_closet_items_scan_batch_id", "closet_items")
    op.drop_column("closet_items", "scan_batch_id")
    op.drop_column("closet_items", "confidence_score")
    op.drop_column("closet_items", "analysis_source")
    op.drop_column("closet_items", "background_removal_status")
    op.drop_column("closet_items", "background_removed")
    op.drop_column("closet_items", "processed_image_url")
    op.drop_column("closet_items", "original_image_url")
