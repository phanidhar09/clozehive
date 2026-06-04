# closet-service Cutover Runbook

Step-by-step to move the wardrobe domain off api-gateway and onto **closet-service**
(its own DB), then flip traffic. Everything is **dual-stack** until step 7 — the
gateway keeps serving until you reload nginx, so you can bail out at any point
before then with zero impact.

Run all commands from the repo root. `docker compose` examples assume the
service DNS names inside the compose network.

> **Golden rule:** do not bring up `nginx` with the new config until the closet
> baseline schema exists, data is migrated, and closet-service passes a smoke
> test on `:8003`. nginx is the cutover.

---

## 0. Prerequisites

In `.env` confirm these are set (compose injects them into **both** services):

- `JWT_SECRET` — **must be the same value** for api-gateway and closet-service,
  or every closet-service request 401s. (Compose uses one `${JWT_SECRET}` for
  both, so just don't override it per-service.)
- `INTERNAL_SERVICE_TOKEN` — non-empty; gates the internal `/internal/users/*`
  calls (user-detail lookup + account-deletion purge).
- `POSTGRES_USER`, `POSTGRES_PASSWORD` — reused for `postgres-closet`.
- `OPENAI_API_KEY`, `GCS_*`, `GEMINI_API_KEY` — same as gateway (closet-service
  now owns vision/embeddings/AI).

Build images:

```bash
docker compose build closet-service migrate-closet
```

---

## 1. Bring up the databases

```bash
docker compose up -d postgres postgres-closet redis
docker compose ps          # wait until postgres + postgres-closet are healthy
```

`postgres-closet` runs `init.sql` on first boot (enables `vector`, `pgcrypto`,
`pg_trgm`).

---

## 2. Ensure the gateway schema is current (idempotent)

```bash
docker compose run --rm migrate          # alembic upgrade head on the gateway DB
```

---

## 3. Create the closet-service baseline schema

The 13 tables are defined by the ORM models; generate the baseline migration
**once** by autogenerating against the live `postgres-closet`, then apply it.

```bash
# generate (writes to services/closet-service/alembic/versions/ on the host)
docker compose run --rm --no-deps closet-service \
  alembic revision --autogenerate -m "baseline closet schema"

# review the generated file, then apply
docker compose run --rm migrate-closet   # alembic upgrade head on clozehive_closet
```

**Verify** (expect 13 tables, no FK to a users table):

```bash
docker compose exec postgres-closet \
  psql -U "$POSTGRES_USER" -d clozehive_closet -c "\dt"
```

---

## 4. Smoke-test closet-service in isolation (still not routed)

```bash
docker compose up -d closet-service
curl -fsS http://localhost:8003/health && echo OK
```

Then hit a real authed route directly (JWT is shared, so a gateway-issued token
works). Get a token by logging in via the gateway, then:

```bash
TOKEN="<paste an access token>"
curl -fsS http://localhost:8003/api/v1/closet/ -H "Authorization: Bearer $TOKEN"
```

A `200` with an (empty, pre-migration) list confirms auth + DB wiring.

---

## 5. Migrate the data (read-only window)

`ON CONFLICT (id) DO NOTHING` makes this safe to re-run, but it only catches new
**inserts** on a second pass — it will not propagate **updates** to rows already
copied. So the clean approach is a short window where the source isn't being
written:

```bash
# (recommended) pause writes: stop the gateway briefly so no new closet rows land
docker compose stop api-gateway

docker compose run --rm --no-deps \
  -e SOURCE_DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB" \
  -e TARGET_DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres-closet:5432/clozehive_closet" \
  closet-service python scripts/migrate_data.py
```

The script prints per-table source/target counts and a parity summary. **Confirm
`✓ All tables copied; target row counts >= source.`** before continuing.

> Large dataset / want minimal downtime? Run the ETL once *before* the window
> (no downtime) to copy the bulk, then run it again inside the window to catch
> inserts. Accept that in-window row *updates* need the window to be short.

---

## 6. Bring up the rest of the stack

```bash
docker compose up -d api-gateway ai-agent ai-worker vision-service frontend
```

---

## 7. Cutover — reload nginx

nginx resolves upstreams at start, so `closet-service` must already be running
(it is, from step 4).

```bash
docker compose up -d nginx          # picks up the new infra/nginx/nginx.conf
# or, if nginx was already running:  docker compose exec nginx nginx -s reload
```

From this moment, `/api/v1/{closet,outfits,trips,ai,ai-chat,analytics,shopping,
rag,fashion-knowledge,purchase-gaps}` go to **closet-service**; auth/profile/
weather/social/ws/jobs stay on the gateway.

---

## 8. Post-cutover smoke test (through nginx, port 80)

Do this **before** letting users back in:

- [ ] Log in (gateway) → `200`, token issued.
- [ ] `GET /api/v1/closet/` → your migrated items appear.
- [ ] Upload an item (vision) → analyze-preview → confirm → item saved.
- [ ] AI stylist chat (`/api/v1/ai-chat/stream`) → streams a response.
- [ ] Create a trip + generate packing (`/api/v1/trips/...`).
- [ ] Analytics page loads (`/api/v1/analytics/...`).
- [ ] **Delete a throwaway account** → confirm its rows are gone from
      `clozehive_closet` (the purge seam):

```bash
docker compose logs api-gateway | grep closet_data_purged
docker compose exec postgres-closet \
  psql -U "$POSTGRES_USER" -d clozehive_closet \
  -c "SELECT count(*) FROM closet_items WHERE user_id='<deleted-uuid>';"   # expect 0
```

If all green, you're cut over. Keep both DBs intact and **do not run Phase 5**
(decommission) until closet-service has been stable for a while.

---

## Rollback (fast, while still safe)

The gateway still has all the code and (pre-cutover) data, so rollback is a
one-file change:

1. In `infra/nginx/nginx.conf`, repoint the two closet blocks back to the
   gateway — change both `proxy_pass http://closet_service;` lines (the SSE
   block and the general closet-domain block) to `proxy_pass http://api_gateway;`.
2. `docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload`
3. `docker compose start api-gateway` (if you stopped it in step 5).

**Caveat:** rollback is clean only if done before users have written new data to
closet-service. Once closet-service has accepted writes, rolling back to the
gateway DB loses those writes (you'd need a reverse ETL). This is exactly why
step 8 verifies everything *before* reopening to users.

---

## After a stable soak → Phase 5

Only once you're confident: remove the moved routers/services/models from
api-gateway, back up and drop the moved tables from the gateway DB, and trim the
now-unused heavy deps (faiss/vision/gemini) from the gateway `requirements.txt`.
That step is irreversible and removes the rollback path — do it last.
```
