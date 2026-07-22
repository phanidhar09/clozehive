"""Backfill saved outfits into outfit_history.

The Saved Outfits page reads ``outfit_history``, but outfits saved via
POST /outfits/ (Dashboard "Save Look", Outfit Builder) or
POST /ai-chat/save-outfit only landed in the ``outfits`` table — so every
pre-existing save is invisible on that page. The save endpoints now mirror
into outfit_history going forward; this migration backfills the rows that
were saved before the fix.

For each ``outfits`` row, insert an ``outfit_history`` row (was_saved=true)
unless the user already has a history row covering the same item set — in
that case just flip its was_saved flag. Inserted rows carry no embedding
(they list fine; they're simply absent from vector similarity search).

Data-only and idempotent. Downgrade is a no-op: backfilled rows are
indistinguishable from organic ones by design, and deleting history is
worse than keeping it.

Revision ID: 038
Revises: 037
Create Date: 2026-07-16
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    history = bind.execute(
        sa.text("SELECT id, user_id, selected_item_ids, was_saved FROM outfit_history")
    ).fetchall()
    # user_id -> list of (history_id, frozenset(item_ids), was_saved)
    by_user: dict[str, list[tuple[str, frozenset, bool]]] = {}
    for row in history:
        items = row.selected_item_ids or []
        if isinstance(items, str):  # driver may return jsonb as text
            items = json.loads(items)
        by_user.setdefault(str(row.user_id), []).append(
            (str(row.id), frozenset(str(i) for i in items), bool(row.was_saved))
        )

    outfits = bind.execute(
        sa.text(
            "SELECT user_id, name, occasion, item_ids, explanation, style_score, created_at "
            "FROM outfits ORDER BY created_at"
        )
    ).fetchall()

    for outfit in outfits:
        item_ids = [str(i) for i in (outfit.item_ids or [])]
        if not item_ids:
            continue
        uid = str(outfit.user_id)
        wanted = frozenset(item_ids)

        matched = False
        for hist_id, hist_items, was_saved in by_user.get(uid, []):
            if hist_items == wanted:
                matched = True
                if not was_saved:
                    bind.execute(
                        sa.text("UPDATE outfit_history SET was_saved = true WHERE id = :id"),
                        {"id": hist_id},
                    )
                break
        if matched:
            continue

        bind.execute(
            sa.text(
                "INSERT INTO outfit_history "
                "(user_id, occasion, selected_item_ids, matching_score, "
                " recommendation_text, improvement_tips, was_saved, created_at) "
                "VALUES (:user_id, :occasion, CAST(:items AS jsonb), :score, "
                "        :text, '[]'::jsonb, true, :created_at)"
            ),
            {
                "user_id": uid,
                "occasion": outfit.occasion,
                "items": json.dumps(item_ids),
                "score": outfit.style_score,
                "text": outfit.explanation or outfit.name,
                "created_at": outfit.created_at,
            },
        )
        # Register so a duplicate outfits row doesn't insert twice
        by_user.setdefault(uid, []).append(("", wanted, True))


def downgrade() -> None:
    # Data-only backfill — see module docstring.
    pass
