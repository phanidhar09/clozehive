# AGENTS.md

Guidance for AI coding agents (Claude Code, Cursor, etc.) working in the
ClozeHive repository. Humans should read [Readme.md](Readme.md) and
[docs/](docs/) first; this file is the quick operational contract for agents.

## What this is

ClozeHive is an AI wardrobe / personal-styling platform. Users build a digital
closet, compose outfits, get FANI-powered styling and packing help, track wear
analytics, and run RAG-grounded wardrobe insights — all grounded in their real
items and history.

**FANI** (Fashion AI Nurturing Individuality) is the built-in AI stylist: outfit
ratings (5-tier scale), Tip of the Day, conversational styling at `/ai-stylist`,
travel packing, wardrobe-gap detection, and **Shop with FANI** purchase advice.

The repo is a **polyglot monorepo** — React SPA plus Python (FastAPI)
services — orchestrated with Docker Compose locally and deployed on **Render**
(`render.yaml`).

## Architecture

Two topologies share one codebase:

| Topology | Entry | Notes |
|----------|-------|-------|
| **Production (Render)** | Browser → `VITE_API_URL` → api-gateway | No nginx, no `ai-worker`. Gateway serves the full `/api/v1` surface with `SERVE_MIGRATED_DOMAIN_ROUTES=true`. |
| **Local dev (Compose)** | Browser → nginx `:80` → frontend + api-gateway | Full stack: ai-agent, ai-worker, mailpit, one-shot migrate. Vision still in-process in the gateway. |

> **Reality check:** this is a **modular monolith** (`api-gateway`) plus a
> dedicated **ai-agent** for FANI reasoning. Standalone `closet-service` and
> `vision-service` were **retired** — the gateway owns wardrobe, vision, RAG
> context assembly, and the public API. Treat `ai-worker`, `mcp/*`, and
> Kafka/Redpanda as **optional** unless explicitly enabled.

### Service map

| Path | Stack | Responsibility |
|------|-------|----------------|
| `frontend/` | React 18 + Vite + TypeScript + Tailwind + Zustand | SPA, PWA. Pages in `src/pages/`, shared UI in `src/components/`, HTTP via `src/lib/api.ts`. |
| `services/api-gateway/` | FastAPI + SQLAlchemy (async) + Alembic | **The product backend.** Identity, wardrobe, intelligence, travel, platform domains; **vision pipeline in-process** (analyze, smart-ingest, bg-removal); RAG/embeddings; WebSocket hub; calls ai-agent for chat/outfit/packing. |
| `services/ai-agent/` | FastAPI + LangGraph (ReAct) | FANI LLM brain — **not public**. Gateway/worker reach it via `AI_AGENT_URL` + `X-Internal-Token`. Inline tools: `weather`, `outfit`, `packing`. Endpoints: `/api/v1/agent/chat`, `/chat/stream`, `/outfit`, `/packing`, `/vision/analyze`. |
| `services/ai-worker/` | ARQ (Redis queue) | Durable async AI jobs — **local dev only**, not on Render. Consumes redis-state db 3; proxies to ai-agent. Gated by `HEAVY_WORK_ASYNC` (**off by default**). |
| `services/mcp/` | MCP HTTP/SSE servers | Legacy/experimental (`--profile vision`). Default stack uses in-process tools. |
| `infra/`, `nginx/` | nginx, Postgres init, observability | Local edge proxy; prod has no nginx. |

### What runs where (agent cheat sheet)

| Capability | Owner | Integration |
|------------|-------|-------------|
| Auth, profile, trips, analytics, WS | api-gateway | Direct DB/Redis |
| Closet CRUD, outfits, planner, similarity | api-gateway | Postgres + pgvector |
| Vision upload / smart-ingest / bg-removal | api-gateway (in-process) | OpenAI/Gemini in `wardrobe/services/` |
| Embeddings for similarity/RAG | api-gateway (BackgroundTasks) | `similarity_service.schedule_embedding_update` |
| FANI chat, outfit gen, packing lists | api-gateway → **ai-agent** | `intelligence/services/ai_client.py` |
| Shopping check, purchase gaps, fashion RAG | api-gateway (in-process + pgvector) | `intelligence/services/` |
| Async outfit/packing/vision jobs | gateway `/jobs` → ai-worker → ai-agent | Dev only; prod runs sync in-process |

**Data stores:** single PostgreSQL (`clozehive`) with **pgvector** for embeddings
and agent vector store — identity, wardrobe, trips, `ai_requests`, everything.
Two Redis roles — **cache** (`REDIS_URL`, evictable) and **state**
(`REDIS_STATE_URL`, non-evictable: OAuth CSRF, refresh tokens, rate limits, ARQ
queue db 3). Never put security/session state on the cache Redis.

## Domain map (api-gateway)

Put new endpoints in the matching domain under
`services/api-gateway/app/api/v1/<domain>/`. Each domain owns `routes`,
`schemas/`, `services/`, and often `repositories/`.

| Domain | Routers | Mounting |
|--------|---------|----------|
| **identity** | `auth`, `profile` | Always |
| **travel** | `weather`; `trips`, `packing_memory` | weather always; trips when migrated |
| **platform** | `health`, `admin`, `ws`, `rum`; `analytics` | health/ws always; analytics when migrated |
| **wardrobe** | `closet`, `closet_similarity`, `outfits`, `outfit_history`, `planner`, `smart_ingest`, `vision_pipeline` | Migrated* |
| **intelligence** | `ai`, `ai_chat`, `rag`, `fashion_rag`, `purchase_gaps`, `shopping_check`, `jobs` | Migrated* |
| **social** | `social` | **Not mounted** (Phase 2; `Groups` page is frontend-only stub) |

\* **Migrated** domains mount when `mount_migrated_routes` is true — dev/test by
default, production via `SERVE_MIGRATED_DOMAIN_ROUTES=true` in `render.yaml`.

Gateway AI routes stay thin: assemble closet/RAG/style context, then delegate
reasoning to ai-agent through `ai_client.py` (timeouts, retries, circuit
breaker). Do **not** add new direct-to-OpenAI stylist paths in the gateway
without a strong reason — extend ai-agent tools or the existing service layer.

## Core workflows

Trace these paths when debugging or extending features:

### 1. Authentication
`POST /api/v1/auth/*` → JWT + refresh in redis-state; Google OAuth CSRF via
`state_getdel`. Frontend: `src/pages/` auth routes + `src/lib/api.ts` refresh
interceptor.

### 2. Garment upload & vision
Upload page → `POST /analyze-vision/stream` (SSE) → in-process Gemini/OpenAI
in `wardrobe/services/vision_pipeline_service.py` →
`POST /save-analyzed-items` → closet rows + background embedding update.
Bulk path: `/smart-ingest/*` review sessions.

### 3. FANI stylist chat (streaming)
`/ai-stylist` → `POST /api/v1/ai-chat/stream` → gateway builds context (closet,
style memory, RAG) → `ai_client` → `POST /api/v1/agent/chat/stream` on
ai-agent → SSE tokens back to browser.

### 4. Outfit & packing
Outfit builder / trips → `/api/v1/ai/*` or `/trips/{id}/packing` → ai-agent
`/agent/outfit` or `/agent/packing` (weather tool uses OpenWeather with static
fallback). Packing preferences: `travel/services/packing_memory`.

### 5. Shop with FANI
`/shopping-check` → `/api/v1/shopping/*` — photo or product URL, SSRF-guarded
fetch, closet match + buy/skip verdict (`shopping_check_service`).

### 6. RAG & wardrobe intelligence
`/purchase-gaps`, `/rag/*`, `/fashion-knowledge` — pgvector retrieval over
fashion knowledge + closet embeddings (`app/rag/`).

### 7. Async AI jobs (dev only)
`POST /api/v1/jobs` → ARQ on redis-state → ai-worker → ai-agent → poll
`GET /jobs/{id}`. In prod (`HEAVY_WORK_ASYNC=false`), same flows run
synchronously in the gateway.

### 8. Real-time notifications
WebSocket `/api/v1/ws` on gateway; frontend `notificationStore` + toast UI.

## Product use cases (where to look)

| Use case | Frontend | Backend |
|----------|----------|---------|
| Home / Tip of the Day / OOTD | `pages/Dashboard.tsx`, `components/dashboard/` | `intelligence/`, `platform/analytics` |
| Closet & similarity | `pages/Closet.tsx`, `ClosetMatch.tsx` | `wardrobe/closet`, `closet_similarity` |
| Scan & add (vision) | `pages/Upload.tsx` | `wardrobe/vision_pipeline`, `smart_ingest` |
| Outfit builder & saved looks | `pages/OutfitBuilder.tsx`, `SavedOutfits.tsx` | `wardrobe/outfits`, `outfit_history` |
| Weekly planner | `pages/WeeklyPlanner.tsx` | `wardrobe/planner` |
| FANI stylist chat | `pages/AIStylistChat.tsx` | `intelligence/ai_chat`, ai-agent |
| Travel & packing | `pages/TravelPlanner.tsx`, `components/travel/` | `travel/trips`, ai-agent packing |
| Closet insights / analytics | `pages/Analytics.tsx` | `platform/analytics` |
| Wardrobe gaps | `pages/PurchaseGaps.tsx` | `intelligence/purchase_gaps` |
| Shop with FANI | `pages/ShoppingCheck.tsx` | `intelligence/shopping_check` |
| Profile & settings | `pages/Profile.tsx` | `identity/profile` |
| Onboarding / style profile | onboarding flow in dashboard | `identity/services/style_profile_context` |

Non-MVP routes can be hidden with `VITE_HIDE_NON_MVP` (`frontend/src/App.tsx`).

## Setup & common commands

Use the **Makefile** — `make help` lists everything.

```bash
make up              # full stack (detached); migrate runs on startup
make stop            # stop containers, keep data  ← daily dev
make health          # container health checks
make migrate         # re-run Alembic manually
make migrate-create MSG="describe change"
make test            # gateway pytest + frontend Vitest
make test-api        # gateway only
make test-frontend   # Vitest only
make lint            # ruff across Python services
make smoke           # compose validation + health
make logs-api        # also logs-agent, logs-worker, logs-kafka
make db-backup       # before destructive ops
```

**Local URLs (defaults):** nginx `http://localhost` · frontend direct
`http://localhost:3001` · API `http://localhost:8000/docs` · ai-agent
`http://localhost:8001/health` · Mailpit `http://localhost:8025`

Local dev without Docker: `make dev-api` (:8000), `make dev-agent` (:8001),
`make dev-frontend` (:3000). Set `VITE_API_URL` if origins differ.

Optional profiles:

```bash
docker compose --profile vision up --build   # legacy mcp-vision
# Kafka/Redpanda: KAFKA_ENABLED=true — see docs/ENVIRONMENT.md (off by default)
```

Frontend (`frontend/`):

```bash
npm run dev          # :3000
npm run typecheck    # run after TS changes
npm run lint         # zero-warnings policy
npm run test         # vitest
npm run test:e2e     # playwright
```

Backend (`services/api-gateway/`):

```bash
python -m pytest tests/ -v --tb=short
ruff check app/ && ruff format app/
mypy app --ignore-missing-imports
```

Backend tests are organized by domain: `tests/identity/`, `tests/wardrobe/`,
`tests/intelligence/`, `tests/travel/`, `tests/platform/`.

## Code conventions

### Backend (Python)

- **Python 3.12**, FastAPI, fully **async** SQLAlchemy. Never block the event
  loop — use `httpx`/async drivers, not `requests` or sync I/O on request paths.
- Lint/format with **ruff**; type-check with **mypy**. CI fails on violations.
- Logging is **structlog** — `logger = structlog.get_logger("name")` with
  structured key/values; never bare f-strings. Do **not** log secrets, tokens,
  passwords, or raw PII.
- Heavy/slow work (embeddings, vision) belongs **off the request path**: use
  `schedule_embedding_update(background_tasks, ...)` or the ARQ queue when
  `HEAVY_WORK_ASYNC=true` — never a blocking call inside the handler.
- Compare secrets with `hmac.compare_digest`, never `==`.

### Frontend (TypeScript / React)

- Functional components + hooks. Shared state: `src/store/` (Zustand).
- All HTTP through `src/lib/api.ts` (axios + 401-refresh) — no ad-hoc clients.
- Tailwind; shared primitives in `src/components/ui/`, layout in
  `src/components/layout/`.
- Observability: Sentry (`@sentry/react`), web-vitals → gateway `/rum`.
- `npm run typecheck` and `npm run lint` must pass (zero eslint warnings).

## Database & migrations

- Single Postgres DB; schema changes need **Alembic**:
  `make migrate-create MSG="..."`, review, then `make migrate`.
- Never hand-edit applied migrations.
- `make db-backup` before destructive work. `make down-clean` deletes volumes —
  only with explicit user confirmation.

## Security

- OAuth CSRF state on **state** Redis, consumed atomically (`state_getdel`).
  Link Google identity only when email is **verified**.
- Keep `gcp-sa.json`, `.env`, credentials out of commits. See
  `.env.example`, [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md), [SECURITY.md](SECURITY.md).
- Shopping-check URL fetch is SSRF-guarded — preserve those checks when extending.

## Testing expectations

- Add or update tests alongside behavior changes.
- Backend: `services/api-gateway/tests/<domain>/`.
- Frontend: `*.test.ts(x)` next to components/pages.
- Before declaring done, run relevant `make test` / `npm run test` and
  `lint`/`typecheck`. Report failures with output — do not claim green without
  running them.

### Self-fixing test loop (Claude Code)

`scripts/run-tests.sh` mirrors the CI checks in `.github/workflows/ci.yml`
(backend-lint + both Python pytest suites) through each service's own `.venv`,
so local green predicts CI green. Prints `ALL GREEN ✓` only when everything passes:

```bash
scripts/run-tests.sh            # lint + both test suites (CI order)
scripts/run-tests.sh lint       # ruff check + ruff format --check + mypy + drift
scripts/run-tests.sh tests      # both pytest suites, no lint
scripts/run-tests.sh gateway    # api-gateway pytest only
scripts/run-tests.sh agent      # ai-agent pytest only
LF=1 scripts/run-tests.sh …     # re-run last-failed only (fast inner loop)
```

Lint needs the CI-pinned tools in the gateway venv (the runner prints the install
line if missing): `.venv/bin/python -m pip install 'ruff==0.15.16' 'mypy==2.1.0'`.
Not mirrored locally: frontend CI, ai-worker tests, coverage gates, docker builds —
push to confirm those. CI runs ai-agent on **Python 3.11**; the local ai-agent venv
may differ (3.14), so 3.11-only failures only show up in CI.

The `/fix-tests` slash command (`.claude/commands/fix-tests.md`) is one iteration
of a self-fixing loop: run the suites, then fix the single highest-priority
root cause (never weaken or skip a test to go green). Drive it with `/loop`:

```
/loop /fix-tests            # self-paced; iterates until ALL GREEN, one fix per pass
/loop /fix-tests gateway    # scope to a single service
/loop 5m /fix-tests         # poll every 5 min (e.g. while CI churns)
```

## Working agreements for agents

- Match surrounding style; grep `services/` and `src/lib/` before adding helpers.
- Keep changes scoped. Flag unrelated issues rather than fixing inline.
- Commit/push only when explicitly asked. Branch off `main` first.
- Don't add dependencies without need — check existing `package.json` /
  `requirements*.txt` first.
- When touching AI flows, trace **gateway → ai_client → ai-agent** end-to-end.
- When touching uploads/vision, stay in **gateway wardrobe** services — there is
  no separate vision microservice.

## Further reading

| Doc | Contents |
|-----|----------|
| [Readme.md](Readme.md) | Product overview, API surface, frontend routes |
| [docs/SERVICES.md](docs/SERVICES.md) | Every wired service, workflows, sequence diagrams |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Env vars, Docker, GCP, Kafka flag |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operations and troubleshooting |
| [SECURITY.md](SECURITY.md) | Security policy |
