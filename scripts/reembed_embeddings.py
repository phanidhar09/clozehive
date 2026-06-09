#!/usr/bin/env python3
"""Re-embed pgvector columns after an embedding-model change.

Why
───
ClozeHive standardised every service on ``text-embedding-3-small``. Any vectors
previously written by ``text-embedding-ada-002`` are the SAME dimensionality
(1536) — so no schema migration is needed — but they live in a *different* vector
space. Mixing the two silently degrades cosine similarity (old items never match
new queries well). This script regenerates the affected embeddings so the whole
corpus shares one space.

What it does
────────────
For each known embedding table present in the target database, it rebuilds the
embedding-input text from the row's own columns, calls OpenAI with the configured
model, and writes the new vector back — in batches, resumably.

Two databases
─────────────
The wardrobe domain (``closet_items``) and the RAG tables can live in different
databases after the closet-service split. Run this once per database, pointing
``DATABASE_URL`` at each:

    # main gateway DB (RAG tables)
    DATABASE_URL=postgresql://clozehive:clozehive@localhost:5433/clozehive \
        python scripts/reembed_embeddings.py --tables outfit_history,packing_memory,\
fashion_knowledge_documents,user_style_memory

    # closet-service DB (wardrobe)
    DATABASE_URL=postgresql://clozehive:clozehive@localhost:5434/clozehive_closet \
        python scripts/reembed_embeddings.py --tables closet_items

Tables not present in the connected DB are skipped automatically, so you can also
just run with the default table set against each DB.

Usage
─────
    OPENAI_API_KEY=sk-... EMBEDDING_MODEL=text-embedding-3-small \
        python scripts/reembed_embeddings.py [options]

Options
    --tables a,b,c     Restrict to these tables (default: all known tables).
    --batch-size N      Rows per fetch/embed batch (default 100).
    --only-null         Only rows where embedding IS NULL (default: re-embed ALL).
    --dry-run           Report counts and the text it would embed; write nothing.
    --limit N           Stop after N rows (smoke testing).

Idempotent: safe to re-run. Rows are processed by ascending id; on failure the
already-committed batches stay done, so you can just run it again.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass

import asyncpg
from openai import AsyncOpenAI

EMBED_DIM = 1536


@dataclass(frozen=True)
class TableSpec:
    """How to (re)build the embedding-input text for one table, in SQL.

    ``text_sql`` is a SQL expression over the row that yields the string to embed.
    Keeping it in SQL keeps the script self-contained and DB-driven; arrays are
    flattened with array_to_string and NULLs coalesced away.
    """

    id_col: str
    text_sql: str
    embedding_col: str = "embedding"


# Mirrors each service's item_to_embedding_text() closely enough that a re-embed
# lands rows in the new model's space. Exact phrasing is refreshed by the live
# builder whenever a row is next edited; what matters here is the model.
TABLE_SPECS: dict[str, TableSpec] = {
    "closet_items": TableSpec(
        id_col="id",
        text_sql=(
            "concat_ws('. ', "
            "name, category, color, brand, fabric, pattern, size, notes, "
            "array_to_string(season, ', '), "
            "array_to_string(occasion, ', '), "
            "array_to_string(tags, ', '))"
        ),
    ),
    "outfit_history": TableSpec(
        id_col="id",
        text_sql="concat_ws('. ', occasion, recommendation_text)",
    ),
    "packing_memory": TableSpec(
        id_col="id",
        text_sql="concat_ws('. ', destination, purpose, user_feedback)",
    ),
    "fashion_knowledge_documents": TableSpec(
        id_col="id",
        text_sql="concat_ws('. ', title, category, season, occasion, content)",
    ),
    "purchase_gaps": TableSpec(
        id_col="id",
        text_sql=(
            "concat_ws('. ', gap_type, missing_category, missing_color, "
            "missing_season, missing_occasion, reason)"
        ),
    ),
    "user_style_memory": TableSpec(
        id_col="id",
        text_sql="content",
    ),
}


def _pg_dsn(url: str) -> str:
    # asyncpg wants a plain postgresql:// DSN (no +asyncpg / +psycopg driver tag).
    for tag in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(tag):
            return "postgresql://" + url[len(tag):]
    return url


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", table))


async def _column_is_vector(conn: asyncpg.Connection, table: str, col: str) -> bool:
    """True when the column is a real pgvector column (not the TEXT fallback)."""
    udt = await conn.fetchval(
        "SELECT udt_name FROM information_schema.columns "
        "WHERE table_name = $1 AND column_name = $2",
        table,
        col,
    )
    return udt == "vector"


async def _embed(client: AsyncOpenAI, model: str, text: str) -> list[float]:
    resp = await client.embeddings.create(model=model, input=text[:8000])
    vec = resp.data[0].embedding
    if len(vec) != EMBED_DIM:
        raise SystemExit(
            f"Model {model!r} returned {len(vec)} dims; expected {EMBED_DIM}. "
            "Aborting — a different dimension needs a schema migration first."
        )
    return [float(v) for v in vec]


async def reembed_table(
    conn: asyncpg.Connection,
    client: AsyncOpenAI,
    model: str,
    table: str,
    spec: TableSpec,
    *,
    batch_size: int,
    only_null: bool,
    dry_run: bool,
    limit: int | None,
) -> tuple[int, int]:
    """Returns (rows_seen, rows_written)."""
    if not await _table_exists(conn, table):
        print(f"  • {table}: not in this database — skipped")
        return (0, 0)
    if not await _column_is_vector(conn, table, spec.embedding_col):
        print(f"  • {table}: {spec.embedding_col} is not a vector column (pgvector "
              "missing?) — skipped")
        return (0, 0)

    where = f"WHERE {spec.embedding_col} IS NULL" if only_null else ""
    total = await conn.fetchval(f"SELECT count(*) FROM {table} {where}")
    print(f"  • {table}: {total} candidate row(s){' [NULL only]' if only_null else ''}")

    seen = written = 0
    last_id = "00000000-0000-0000-0000-000000000000"
    while True:
        if limit is not None and seen >= limit:
            break
        fetch_n = batch_size
        if limit is not None:
            fetch_n = min(fetch_n, limit - seen)
        rows = await conn.fetch(
            f"""
            SELECT {spec.id_col} AS id, ({spec.text_sql}) AS embed_text
            FROM {table}
            {where + ' AND' if where else 'WHERE'} {spec.id_col} > $1::uuid
            ORDER BY {spec.id_col}
            LIMIT $2
            """,
            last_id,
            fetch_n,
        )
        if not rows:
            break
        for row in rows:
            seen += 1
            last_id = str(row["id"])
            text = (row["embed_text"] or "").strip()
            if not text:
                continue
            if dry_run:
                if seen <= 3:
                    print(f"      [dry-run] {table}#{last_id[:8]} ← {text[:80]!r}")
                written += 1
                continue
            vec = await _embed(client, model, text)
            await conn.execute(
                f"UPDATE {table} SET {spec.embedding_col} = $1::vector "
                f"WHERE {spec.id_col} = $2",
                _vector_literal(vec),
                row["id"],
            )
            written += 1
        print(f"      …{seen}/{total} processed")
    return (seen, written)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Re-embed pgvector columns.")
    parser.add_argument("--tables", default=",".join(TABLE_SPECS))
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--only-null", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL is required.", file=sys.stderr)
        return 2
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: OPENAI_API_KEY is required (or use --dry-run).", file=sys.stderr)
        return 2

    requested = [t.strip() for t in args.tables.split(",") if t.strip()]
    unknown = [t for t in requested if t not in TABLE_SPECS]
    if unknown:
        print(f"ERROR: unknown table(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Known: {', '.join(TABLE_SPECS)}", file=sys.stderr)
        return 2

    print(f"Re-embedding with model={model!r} dry_run={args.dry_run} "
          f"only_null={args.only_null}")
    client = AsyncOpenAI(api_key=api_key) if api_key else None  # type: ignore[arg-type]
    conn = await asyncpg.connect(_pg_dsn(db_url))
    grand_seen = grand_written = 0
    try:
        for table in requested:
            seen, written = await reembed_table(
                conn, client, model, table, TABLE_SPECS[table],
                batch_size=args.batch_size,
                only_null=args.only_null,
                dry_run=args.dry_run,
                limit=args.limit,
            )
            grand_seen += seen
            grand_written += written
    finally:
        await conn.close()
        if client is not None:
            await client.close()

    verb = "would re-embed" if args.dry_run else "re-embedded"
    print(f"\nDone. {verb} {grand_written} row(s) across {len(requested)} table(s) "
          f"({grand_seen} seen).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
