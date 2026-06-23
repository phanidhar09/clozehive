# ClozeHive 

**Launch the app:** https://cloze-hive.onrender.com — sign up or log in to start.
**Marketing site:** https://clozehive.netlify.app (overview & features)

ClozeHive is a **wardrobe intelligence** application: a digital closet, outfit building, **FANI**-powered AI styling, travel and packing help, analytics, and **RAG**-enhanced insights grounded in your items and history. The stack is a **React + Vite + TypeScript** SPA, a **FastAPI** API gateway (auth, closet, outfits, trips, analytics, AI orchestration entrypoints, and in-process image-analysis/background-removal vision pipeline), a **LangGraph-style ai-agent** with **MCP** tool servers, **PostgreSQL + pgvector**, **Redis**, and **nginx** as the single browser entrypoint in Docker.

**Repository:** [github.com/phanidhar09/clozehive](https://github.com/phanidhar09/clozehive)

**Environment variables, Docker, GCP, migrations, tests, and troubleshooting:** see **[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)**.

---

## Meet FANI

**FANI (Fashion AI Nurturing Individuality)** is ClozeHive's built-in AI stylist. FANI powers outfit recommendations, daily style tips, wardrobe gap detection, AI chat, and packing suggestions — available as a floating chat on every page and as a full-screen stylist at `/ai-stylist`.

---

## Features (high level)

| Area | What you get |
|------|----------------|
| **Home** | Daily FANI Tip of the Day (day-of-week rotation), Style at a Glance strip (Most Worn / Never Worn / Closet Gaps), 6-item quick action grid, Outfit of the Day with 5-tier FANI rating. |
| **Closet** | CRUD, metadata, images (local disk or GCS), preview/confirm upload flows, **similar items**, background removal (vision path). |
| **Outfits** | Outfit builder, saved outfits, outfit history APIs for RAG. |
| **FANI AI Stylist** | Structured **AI Stylist Chat** (`/ai-stylist`); FANI floating chat available on every page. |
| **Outfit Rating** | 5-tier FANI rating system: Needs Improvement → Average → Good → Excellent → Best Fit — each tier shows star count, color badge, and a stylist note. |
| **Travel** | Trips, packing lists; gateway can use **ai-agent** / MCP packing tools; packing memory APIs. |
| **Intelligence** | **RAG** routes: fashion knowledge, closet similarity, purchase gaps, unified `/rag/*`, embeddings in Postgres/pgvector. |
| **Profile & Settings** | LinkedIn-style settings page — Display Name, Location & Weather, FANI Preferences, Privacy. Profile hover dropdown gives quick access to Saved Outfits, Closet Insights, and Wardrobe Gaps. |
| **Real-time** | **WebSocket** notifications (`/api/v1/ws`) for in-app updates. |
| **Auth** | JWT + refresh, **Google OAuth** (Redis-backed CSRF state). |
| **Optional integrations** | Legacy/advanced profiles (for example `mcp-vision`) can be enabled when needed; default MVP stack runs without external MCP tool containers. |

---

## Architecture

```mermaid
flowchart TB
  subgraph browser [Client]
    U[User Browser]
    SPA[SPA bundle]
  end

  subgraph edge [Edge / Web]
    N[nginx :80 (single entrypoint)]
    FE[frontend :3000 (Vite app)]
  end

  subgraph app [Application Services]
    GW[api-gateway :8000<br/>auth, closet, outfits, trips, RAG, WS hub<br/>+ in-process vision: analyze, smart-ingest, bg removal]
    AG[ai-agent :8001<br/>FANI agent + inline tools]
  end

  subgraph state [State + Storage]
    PG[(Postgres + pgvector<br/>source of truth)]
    RD[(Redis<br/>cache + sessions + staging)]
    UP[(uploads volume / GCS)]
  end

  subgraph optional [Optional Profiles]
    MV[mcp-vision :8011<br/>legacy/experimental]
    MIG[migrate one-shot<br/>alembic upgrade head]
  end

  U --> N
  N -->|/| FE
  FE --> SPA
  N -->|/api/v1/* (general)| GW
  N -->|/api/v1/analyze-vision*, /smart-ingest,\n/closet/*/remove-background| GW
  N -->|/uploads/*| GW
  N -->|/api/v1/ws| GW

  GW --> PG
  GW --> RD
  GW --> UP
  GW -->|AI_AGENT_URL + X-Internal-Token| AG
  AG --> PG
  AG --> RD
  MIG --> PG
  AG -. legacy profile .-> MV
```

- **Default `docker compose up`** starts `postgres`, `redis`, `ai-agent`, `api-gateway`, `frontend`, `nginx`, and one-shot `migrate`.
- **nginx** is the single browser entrypoint: serves SPA traffic, proxies `/api` traffic (including vision-heavy endpoints) to `api-gateway`, proxies `/uploads`, and upgrades `/api/v1/ws`.
- **api-gateway** calls **ai-agent** over internal HTTP (`AI_AGENT_URL`) and can attach `X-Internal-Token` for service-to-service auth.
- **ai-agent** runs weather/outfit/packing tools inline (in-process) by default; no external MCP containers are required for normal local MVP runs.

## How Services Are Wired

| Flow | Wiring |
|------|--------|
| Browser → API | Frontend uses relative `/api/v1` by default; browser hits `nginx` first, which proxies all `/api` paths to `api-gateway`. |
| Auth + app data | `api-gateway` owns auth/session APIs and core business routes (closet, outfits, trips, analytics, RAG, shopping check), backed by Postgres + Redis. |
| Real-time notifications | Browser WebSocket connects to `/api/v1/ws`; nginx upgrades and forwards to gateway WebSocket router. |
| AI chat / outfit / packing | Gateway AI routes assemble user/closet/RAG context, then call `ai-agent` via `app/services/ai_client.py`. |
| Vision ingestion | Vision-heavy endpoints run **in-process inside `api-gateway`** (the `vision_pipeline` / `smart_ingest` routers): detection + background-removal pipeline, backed by Postgres/Redis for persistence/cache. |
| Shared state | Postgres is the source of truth; Redis is used for caching, preview sessions, token/session helpers, and fast cross-request state. |

---

## Service responsibilities

| Service | Role |
|---------|------|
| `frontend` | React app (Vite). In Docker, host port defaults to **3001** → container **3000** (`FRONTEND_HOST_PORT`). |
| `nginx` | Single entry **:80** — API, vision paths, uploads, WS, frontend. |
| `services/api-gateway` | Public API: auth, profile, closet, outfits, trips, analytics, AI routes, RAG routers, WebSocket hub, and ARQ job producers when `HEAVY_WORK_ASYNC` is enabled. Also runs the **vision pipeline in-process** (analyze/stream, smart ingest, background removal) using OpenAI/Gemini per config. |
| `services/ai-agent` | FANI agent service used by gateway AI routes. Default behavior is inline LangGraph tools (`weather`, `outfit`, `packing`) inside the service. |
| `services/mcp/*` | Optional/legacy MCP HTTP/SSE servers (for non-default profiles or experiments). |
| `services/ai-worker` | Background worker code (not part of the default `docker-compose.yml` MVP stack). |
| `infra/` | Postgres init, nginx config (legacy Kafka/Redpanda topic scripts remain but the async path now uses ARQ + Redis). |

Legacy or archive material, if present, may live under `archive/`.

---

## Local setup with Docker

1. **Copy env template** and fill secrets:

   ```sh
   cp .env.example .env
   ```

   For Vite-only overrides, use `frontend/.env.example` → `frontend/.env`.

2. **Start the stack:**

   ```sh
   make up
   ```

   Or: `docker compose up --build` (add `-d` to detach).

   The **migrate** service runs **Alembic** so the DB schema is applied on startup; you can still run `make migrate` if you need to re-apply manually.

3. **Optional: legacy MCP vision server** (heavier / experimental): Compose profile **`vision`**:

   ```sh
   docker compose --profile vision up --build
   ```

4. **Health checks:**

   ```sh
   make health
   ```

### Useful URLs (defaults)

| What | URL |
|------|-----|
| **Recommended entry** (nginx) | `http://localhost` |
| Frontend (direct to container map) | `http://localhost:3001` (`FRONTEND_HOST_PORT`) |
| API gateway (direct) | `http://localhost:8000` — `/live`, `/ready`, `/health`, `/docs` |
| OpenAPI | `http://localhost:8000/docs` |
| ai-agent (direct) | `http://localhost:8001/health` |

**Ports:** Postgres is **`5433`→5432** and Redis **`6382`→6379** on the host by default (see `.env.example`) to avoid clashes with local installs.

**CORS / origins:** `ALLOWED_ORIGINS` must include the exact origin users open (e.g. `http://localhost` vs `http://localhost:3001`).

---

## API surface (v1)

Routers are mounted under **`/api/v1`** (see `services/api-gateway/app/api/v1/router.py`), including:

- **Auth** — register, login, refresh, Google OAuth callback
- **Profile**
- **Closet** — items, preview flows, similarity
- **Outfits** + **outfit history** (RAG)
- **Trips** + **packing memory**
- **Analytics**
- **AI** — FANI stylist/outfit/trip helpers (streaming/long-timeout paths configured in nginx)
- **AI chat** — persisted FANI chat (`/api/v1/ai-chat/*`)
- **Weather**
- **Admin**
- **Fashion RAG**, **purchase gaps**, **unified RAG**
- **WebSocket** — `/api/v1/ws` for notifications

Vision-specific paths (e.g. analyze stream, smart ingest, remove-background) run **in-process inside `api-gateway`** and share the same `/api/v1/...` URL shape to the browser (nginx applies longer read timeouts to these routes).

---

## Production-oriented compose

For a slimmer or production-tuned layout, see `docker-compose.prod.yml` and nginx-oriented docs in-repo. Adjust env vars for your provider; helper scripts may live under `scripts/` (deploy, backup, restore, LetsEncrypt).

---

## Local setup without Docker

You need **Postgres (with pgvector)**, **Redis**, and matching `DATABASE_URL` / `REDIS_URL`. Then:

```sh
npm --prefix frontend install
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r services/api-gateway/requirements-dev.txt
pip install -r services/ai-agent/requirements.txt
```

Run processes in separate terminals (examples):

```sh
make dev-api           # API gateway :8000 (includes the in-process vision pipeline)
make dev-agent         # AI agent :8001
make dev-frontend      # Vite on :3000 (see frontend/package.json)
```

Point `VITE_API_URL` at your gateway if the frontend origin differs from the API.

---

## Environment variables

Use **`.env.example`** as the source of truth. Commonly customized:

| Variable | Notes |
|----------|--------|
| `OPENAI_API_KEY` | Chat, embeddings, much of vision/analysis. |
| `GEMINI_API_KEY` | Optional for the gateway's vision/analysis paths when configured. |
| `JWT_SECRET` | Strong random value in production (≥ 32 chars). |
| `DATABASE_URL` | Host dev often uses Postgres on **5433** per example. |
| `REDIS_URL` | Host dev often **6382**; OAuth requires working Redis. |
| `ENABLE_MCP_TOOLS` | **ai-agent** toggle for external MCP URLs in legacy setups. Inline tools work without external MCP containers. |
| `ALLOWED_ORIGINS` | Must list real SPA origins. |
| Google OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. |
| GCS | `GCS_BUCKET_NAME` + credentials for cloud image storage (optional for local disk). |
| Frontend | `VITE_API_URL`, `VITE_HIDE_NON_MVP`. |

Never commit a real `.env` or service-account JSON.

---

## Testing

**API gateway** — pytest with SQLite/fakes for many tests (see `services/api-gateway/tests/`):

```sh
cd services/api-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v --tb=short
```

From repo root: `make test-api`.

**Frontend** — Vitest + Testing Library:

```sh
cd frontend && npm ci && npm run test
```

From repo root: `make test-frontend`. Both: `make test`.

---

## Common commands

```sh
make help             # Makefile targets
make up               # docker compose up -d --build
make stop             # docker compose down (keep volumes)
make down-clean       # confirm + docker compose down -v (destructive)
make logs             # tail logs
make migrate          # Alembic via migrate container
make test-api         # gateway pytest
make test-frontend    # Vitest
make test             # both
make build-frontend   # production Vite build
make smoke            # compose validation + health
make clean            # scripts/clean-artifacts.sh
```

---

## Verification & health

```sh
docker compose config
docker compose config --quiet
make smoke
make build-frontend
```

**Gateway endpoints:**

- `GET /live` — process up
- `GET /ready` — DB (and Redis if `REDIS_CHECK_ON_READY=true`)
- `GET /health` — aggregated JSON

### Dependency audits

```sh
npm audit --prefix frontend
pip install pip-audit && pip-audit -r services/api-gateway/requirements.txt
```

---

## Troubleshooting (quick)

- **OpenAI / model errors** — `OPENAI_API_KEY` in `.env`; restart **api-gateway** and **ai-agent** after changes.
- **FANI / ai-agent** — In current MVP wiring, ai-agent runs inline tools by default; check `docker compose logs ai-agent api-gateway` first. If using legacy MCP profile, also verify the relevant `mcp-*` service health.
- **Vision timeouts** — nginx sets longer read timeouts for AI and vision; check **api-gateway** logs and `GEMINI_API_KEY` / OpenAI quotas.
- **WebSockets** — Ensure clients hit a URL nginx proxies (e.g. `ws://localhost/api/v1/ws?...` through **:80**) or align direct **:8000** dev with `ALLOWED_ORIGINS`.
- **Stale builds** — `make clean`, then rebuild images or `npm run build` as needed.

---

## Frontend routes (reference)

| Route | Description |
|-------|-------------|
| `/dashboard` | **Home** — FANI Tip of Day, Style at a Glance, Outfit of the Day with rating, quick actions, recent closet items |
| `/closet` | Browse and manage all wardrobe items |
| `/outfit-builder` | Mix & match items into outfits |
| `/upload` | Scan & add new clothing via FANI vision analysis |
| `/ai-stylist` | Full-screen FANI AI Stylist Chat |
| `/travel` | Travel packing planner |
| `/analytics` | Closet Insights — wear analytics & trends |
| `/purchase-gaps` | Wardrobe Gaps — missing wardrobe essentials |
| `/saved-outfits` | FANI-curated saved looks |
| `/profile` | Profile view with avatar, stats, outfit history |
| `/profile?tab=settings` | LinkedIn-style Settings — display name, location, FANI preferences, privacy |

**Navigation:** The top navbar avatar triggers a hover dropdown with quick links to Saved Outfits, Closet Insights, Wardrobe Gaps, View Profile, and Settings. The sidebar covers primary navigation (Home, My Closet, Outfit Builder, Add to Closet, Travel Packing).

Non-MVP areas (e.g. groups, avatar editor, classic stylist) may be hidden when `VITE_HIDE_NON_MVP` is enabled — see `frontend/src/App.tsx`.
