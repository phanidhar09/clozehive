"""Initial PostgreSQL schema for CLOZEHIVE.

Revision ID: 001
Create Date: 2025-01-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("google_id", sa.String(255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_username", "users", ["username"])

    # ── user_credentials ───────────────────────────────────────────────────────
    op.create_table(
        "user_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── refresh_tokens ────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    # ── follows ───────────────────────────────────────────────────────────────
    op.create_table(
        "follows",
        sa.Column("follower_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("following_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("follower_id", "following_id"),
    )
    op.create_index("idx_follows_follower_id", "follows", ["follower_id"])
    op.create_index("idx_follows_following_id", "follows", ["following_id"])

    # ── groups ────────────────────────────────────────────────────────────────
    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_private", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("invite_code", sa.String(20), nullable=False, unique=True),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_groups_owner_id", "groups", ["owner_id"])

    # ── group_members ─────────────────────────────────────────────────────────
    op.create_table(
        "group_members",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )
    op.create_index("idx_group_members_user_id", "group_members", ["user_id"])

    # ── closet_items ──────────────────────────────────────────────────────────
    op.create_table(
        "closet_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("color", sa.String(100), nullable=True),
        sa.Column("fabric", sa.String(100), nullable=True),
        sa.Column("pattern", sa.String(100), nullable=True),
        sa.Column("season", sa.String(50), nullable=True),
        sa.Column("occasion", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("eco_score", sa.Numeric(3, 1), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("size", sa.String(20), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("wear_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_worn", sa.Date, nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_closet_items_user_id", "closet_items", ["user_id"])
    op.create_index("idx_closet_items_category", "closet_items", ["category"])

    # ── outfits ───────────────────────────────────────────────────────────────
    op.create_table(
        "outfits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("occasion", sa.String(100), nullable=True),
        sa.Column("item_ids", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("style_score", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── update_at trigger ─────────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    for table in ("users", "groups", "closet_items"):
        op.execute(f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    for table in ("outfits", "closet_items", "group_members", "groups", "follows", "refresh_tokens", "user_credentials", "users"):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;")
