# closet-service

Owns the CLOZEHIVE wardrobe domain and the closet-data-heavy AI features
(closet, vision, embeddings, RAG, outfits, trips, packing, style profile, AI
stylist chat, shopping check, analytics). Backed by its **own** Postgres
(`clozehive_closet`).

Requests are authenticated by validating the gateway-issued JWT locally with the
**shared `JWT_SECRET`** — there is no per-request call to api-gateway. The
`users` table lives in the api-gateway DB; tables here carry a plain
`user_id UUID` column with **no foreign key**. Cleanup on account deletion is
handled by an internal purge seam (added in Phase 4), not `ON DELETE CASCADE`.

> Split status: **Phase 0–1 complete** (skeleton boots + schema defined).
> Domain routers/services are moved in Phase 2; routing cutover is Phase 4.
> See `~/.claude/plans/cheeky-tickling-hoare.md` for the full plan.

## One-time: generate the baseline migration

The 13 tables are defined by the ORM models in `app/models/`. Generate the
baseline alembic revision **against a running `postgres-closet`** (autogenerate
guarantees the migration matches the models):

```bash
# from repo root, with postgres-closet up:
docker compose up -d postgres-closet

docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres-closet:5432/clozehive_closet" \
  closet-service \
  alembic revision --autogenerate -m "baseline closet schema"
```

Review the generated file in `alembic/versions/`, then it is applied
automatically by the `migrate-closet` container on every `docker compose up`
(or manually: `alembic upgrade head`).

## One-time: migrate existing data (Phase 3)

After the baseline schema exists, copy the 13 closet-domain tables from the
gateway DB into `clozehive_closet` with the idempotent ETL:

```bash
docker compose run --rm --no-deps \
  -e SOURCE_DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/clozehive" \
  -e TARGET_DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres-closet:5432/clozehive_closet" \
  closet-service python scripts/migrate_data.py
```

It copies in FK order, uses `ON CONFLICT (id) DO NOTHING` (safe to re-run), and
prints source/target row counts per table. Run it during a brief read-only
window (or do a second pass before the Phase 4 cutover) so writes to the source
during the copy aren't missed. See `scripts/migrate_data.py` for details.

## Run locally

```bash
docker compose up --build closet-service        # boots on :8003 (health: /health, /live, /ready)
```

closet-service is **not yet routed by nginx** (Phase 4). Until then, reach it
directly on `http://localhost:8003`.
