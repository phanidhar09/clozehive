"""Phase 3 ETL — copy the closet domain from the gateway DB into closet-service's DB.

One-time (idempotent) migration of the 13 closet-domain tables from the
api-gateway database (``clozehive``) into the closet-service database
(``clozehive_closet``). Safe to re-run: every insert is
``ON CONFLICT (id) DO NOTHING``, so already-copied rows are skipped.

Tables are copied in foreign-key dependency order (intra-domain FKs are kept in
the target schema). ``user_id`` columns have no FK in the target, so rows copy
even though the users themselves live only in the gateway DB.

Usage (from repo root, with both Postgres containers up):

    docker compose up -d postgres postgres-closet migrate-closet   # ensure target schema exists

    SOURCE_DATABASE_URL="postgresql://USER:PASS@localhost:5433/clozehive" \\
    TARGET_DATABASE_URL="postgresql://USER:PASS@localhost:5434/clozehive_closet" \\
    python services/closet-service/scripts/migrate_data.py

Or inside the compose network (service DNS names, default port 5432):

    docker compose run --rm --no-deps \\
      -e SOURCE_DATABASE_URL="postgresql://USER:PASS@postgres:5432/clozehive" \\
      -e TARGET_DATABASE_URL="postgresql://USER:PASS@postgres-closet:5432/clozehive_closet" \\
      closet-service python scripts/migrate_data.py

IMPORTANT: run during a brief read-only window (or accept that rows written to
the source between this copy and the Phase 4 cutover will need a second pass),
otherwise late writes on the source are missed.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

try:
    from pgvector.asyncpg import register_vector
except ModuleNotFoundError:  # pgvector not installed in this interpreter
    register_vector = None  # type: ignore

# FK-dependency order: a table appears after every table it references.
TABLES: list[str] = [
    "trips",
    "closet_items",
    "outfits",
    "user_style_profiles",
    "fashion_knowledge_documents",
    "purchase_gaps",
    "outfit_history",
    "packing_plans",     # → trips
    "packing_memory",    # → trips, packing_plans
    "ai_chat_sessions",
    "daily_nudges",
    "ai_chat_messages",  # → ai_chat_sessions
    "outfit_feedback",   # → outfits
]

BATCH = 1000


def _normalize(url: str) -> str:
    """asyncpg wants a plain postgresql:// DSN (no +asyncpg, no sqlmode params)."""
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
    return url.split("?", 1)[0]


async def _target_columns(conn: asyncpg.Connection, table: str) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
        """,
        table,
    )
    return [r["column_name"] for r in rows]


async def _copy_table(source: asyncpg.Connection, target: asyncpg.Connection, table: str) -> tuple[int, int, int]:
    cols = await _target_columns(target, table)
    if not cols:
        raise RuntimeError(f"target table '{table}' has no columns — run migrate-closet first")

    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"${i}" for i in range(1, len(cols) + 1))
    insert_sql = (
        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) '
        f"ON CONFLICT (id) DO NOTHING"
    )

    src_total = await source.fetchval(f'SELECT count(*) FROM "{table}"')
    before = await target.fetchval(f'SELECT count(*) FROM "{table}"')

    moved = 0
    async with source.transaction():
        cursor = await source.cursor(f'SELECT {col_list} FROM "{table}"')
        while True:
            rows = await cursor.fetch(BATCH)
            if not rows:
                break
            await target.executemany(insert_sql, [tuple(r) for r in rows])
            moved += len(rows)

    after = await target.fetchval(f'SELECT count(*) FROM "{table}"')
    inserted = after - before
    print(f"  {table:<28} source={src_total:<7} target_before={before:<7} "
          f"read={moved:<7} inserted={inserted:<7} target_after={after}")
    return src_total, inserted, after


async def main() -> int:
    src_url = os.environ.get("SOURCE_DATABASE_URL")
    tgt_url = os.environ.get("TARGET_DATABASE_URL")
    if not src_url or not tgt_url:
        print("ERROR: set SOURCE_DATABASE_URL and TARGET_DATABASE_URL", file=sys.stderr)
        return 2

    source = await asyncpg.connect(_normalize(src_url))
    target = await asyncpg.connect(_normalize(tgt_url))
    if register_vector is not None:
        # Round-trips pgvector embedding columns as Python lists on both ends.
        # If a DB lacks the extension (no vector type), skip — tables without
        # vector columns still copy fine; tables with them require the extension
        # (the baseline migration enables it, so production always has it).
        for label, conn in (("source", source), ("target", target)):
            try:
                await register_vector(conn)
            except Exception as exc:  # noqa: BLE001
                print(f"  note: pgvector codec not registered on {label} ({exc}) — "
                      f"continuing; vector columns require the extension", file=sys.stderr)

    print(f"Migrating {len(TABLES)} tables: {src_url.split('@')[-1]} -> {tgt_url.split('@')[-1]}\n")
    mismatches: list[str] = []
    try:
        for table in TABLES:
            src_total, _inserted, target_after = await _copy_table(source, target, table)
            if target_after < src_total:
                mismatches.append(f"{table} (source={src_total} > target={target_after})")
    finally:
        await source.close()
        await target.close()

    print()
    if mismatches:
        print("PARITY WARNING — target has fewer rows than source for:")
        for m in mismatches:
            print(f"  - {m}")
        return 1
    print("✓ All tables copied; target row counts >= source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
