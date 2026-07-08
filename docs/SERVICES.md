# Clozehive — Services & Workflows

This document covers every service that is **actually wired and running**.
Two topologies exist and are both documented:

- **Production (Render)** — the deployed blueprint (`render.yaml`). No nginx; the
  frontend calls the api-gateway directly. The gateway is the **sole owner of the
  wardrobe domain** and runs the vision pipeline and all AI in-process.
- **Local dev (`docker compose up --build`)** — the same services behind nginx
  (gateway, frontend). Vision and AI run in-process inside the gateway, matching
  production.

Optional/unwired components are listed at the end.

> **History:** there used to be separate `closet-service` (:8003) and
> `vision-service` (:8002) processes — the former owned the wardrobe domain against
> its own Postgres, the latter did image analysis/background removal against
> `postgres-closet`. There were also separate `ai-agent` (:8001, LLM brain) and
> `ai-worker` (ARQ async-job consumer) services. All were **retired**: the gateway
> always carried copies of those routers (and prod already served them in-process),
> the AI now runs in-process against OpenAI/Gemini, and the async job path was never
> reached in production. The wardrobe domain, vision pipeline, and all AI now live
> only in the api-gateway.

---

## 1. System Overview

### Production (Render) — canonical

```mermaid
flowchart LR
    B[Browser] --> GW[api-gateway :8000<br/>SERVE_MIGRATED_DOMAIN_ROUTES=true]
    GW --> PG[(clozehive-db<br/>identity + wardrobe + pgvector)]
    GW --> R[(redis cache)]
    GW --> RS[(redis-state<br/>OAuth/refresh/rate-limit)]
```

The frontend's `VITE_API_URL` points at the gateway, which serves the **entire**
`/api/v1` surface — identity, travel/weather, platform, **and** the wardrobe +
intelligence domains (closet, outfits, trips, ai, ai-chat, analytics, rag, …).
Vision ingestion and all AI generation (chat, outfit, packing) run **in-process
in the gateway** against OpenAI/Gemini; embedding generation runs in-process via
BackgroundTasks.

### Local dev (`docker compose up`) — full stack

```mermaid
flowchart LR
    B[Browser] --> N[nginx :80]
    N -->|"/"| FE[frontend :3000]
    N -->|"all /api/v1 incl. analyze-vision,<br/>smart-ingest, remove-background, ai"| GW[api-gateway :8000]
    GW --> PG[(postgres<br/>identity + wardrobe + pgvector)]
    GW --> R[(redis cache)]
    GW --> RS[(redis-state<br/>OAuth/refresh/rate-limit)]
```

In dev the wardrobe/intelligence routers (including the vision pipeline and AI)
mount automatically (`mount_migrated_routes` defaults on outside production), and
nginx proxies all `/api/v1` prefixes to the gateway. The dev stack mirrors
production: there is no separate vision database, AI service, or worker process,
so the full upload→closet→AI flow runs against one `postgres`.

**Databases:** `postgres` (clozehive) holds **everything the gateway owns** —
identity/auth/platform **and** the wardrobe domain (items, outfits, trips,
embeddings, style memory / RAG vector store). `pgvector/pgvector:pg16` enables
embedding search.

**Two-Redis split:** `redis` (allkeys-lru, evictable) is pure cache;
`redis-state` (noeviction) holds data that must survive memory pressure —
OAuth CSRF/code state, refresh tokens, and rate-limit counters.

---

## 2. nginx (reverse proxy, `:80`) — dev stack only

Single public entry point for the local stack (prod on Render has no nginx).
Config: `infra/nginx/nginx.conf`.

Responsibilities:
- **Routing** (most-specific first):
  - `/api/v1/analyze-vision/stream` → api-gateway (in-process vision), SSE mode (no buffering, no read timeout)
  - `/api/v1/(analyze-vision|save-analyzed-items|smart-ingest)` → api-gateway (in-process vision)
  - `/api/v1/closet/{id}/remove-background` → api-gateway (in-process vision)
  - `/api/v1/(ai/*|ai-chat)/(stream|async)` → api-gateway, SSE mode
  - `/api/v1/(closet|outfits|trips|ai|ai-chat|analytics|shopping|rag|fashion-knowledge|purchase-gaps)` → api-gateway (120 s read timeout for long AI generations)
  - `/api/v1/ws` → api-gateway, WebSocket upgrade (24 h timeouts)
  - `/api/` (everything else: auth, profile, weather, admin, rum) → api-gateway
  - `/uploads/` → api-gateway (garment images)
  - `/assets/` → frontend, cached 1 year immutable; `/` → frontend SPA shell, `no-cache`
- **Rate limiting:** 30 r/s general API, 5 r/s auth, 10 r/s AI endpoints (per IP)
- **Security headers**, gzip, JSON access logs with request IDs
- `/metrics` restricted to private networks only

---

## 3. frontend (React SPA, `:3000` container / `:3001` host)

Vite + React + TypeScript, served by its own nginx inside the container
(proxies `/api` and `/uploads` to the gateway when `VITE_API_URL` is empty). In
production `VITE_API_URL` is the gateway's Render URL.

Pages wired to the backend:

| Page | Backend it talks to |
|---|---|
| Dashboard, Onboarding (incl. Style Profile) | api-gateway |
| Upload | api-gateway (analyze + SSE stream + save, all in-process vision) |
| Closet, ClosetMatch | api-gateway (CRUD, similarity) |
| OutfitBuilder, SavedOutfits | api-gateway |
| AIStylist, AIStylistChat | api-gateway `/ai`, `/ai-chat` (SSE streaming) |
| TravelPlanner | api-gateway (trips, packing, weather) |
| Analytics | api-gateway |
| PurchaseGaps, ShoppingCheck | api-gateway |
| Profile, ForgotPassword/ResetPassword, OAuth callback | api-gateway (identity) |

Observability: Sentry (`@sentry/react`) + web-vitals RUM posted to the
gateway's `/rum` endpoint.

---

## 4. api-gateway (FastAPI, `:8000`) — the wardrobe owner

Owns the **entire `/api/v1` surface**: identity, travel-weather, platform, **the
wardrobe domain, and the intelligence (closet-data AI) domain**, including all
in-process AI generation (`/ai/*`, `/ai-chat/*`). Database: `postgres` (clozehive;
asyncpg + SQLAlchemy, Alembic migrations via the run-once `migrate` container).

### Always-mounted routers (`app/api/v1/router.py`)

| Domain | Routes | Notes |
|---|---|---|
| **identity** | `/auth/*` (register, login, refresh, Google OAuth callback), `/profile` | JWT (shared `JWT_SECRET`); refresh tokens + OAuth CSRF state in redis-state |
| **travel** | `/weather`, `/trips/*` | Trip CRUD + AI packing; live OpenWeather forecast |
| **platform** | `/health`, `/admin`, `/rum`, `/ws` | `/ws` = notification WebSocket; `/rum` ingests web-vitals |

### Wardrobe + intelligence routers

These mount when `mount_migrated_routes` is true — which is **dev/test by
default, and production via the explicit `SERVE_MIGRATED_DOMAIN_ROUTES=true`
override** in `render.yaml`. They are the live owner of these prefixes (there is
no separate service anymore).

| Area | Routes | What it does |
|---|---|---|
| Closet | `/closet/*` | Item CRUD, image metadata, availability |
| Similarity | `/closet/similarity`, match | pgvector embedding search over closet items |
| Outfits | `/outfits/*` | Outfit CRUD + AI outfit generation (in-process) |
| Outfit history | wear tracking | Logs/queries what was worn when (feeds RAG) |
| Planner | `/planner/*` | Weekly weather-aware outfit calendar |
| Smart ingest | `/smart-ingest/*` | Bulk ingest sessions (in-process vision) |
| Vision pipeline | `/analyze-vision`, `/save-analyzed-items` | In-process garment analysis + save |
| AI | `/ai/*` (incl. `/stream`) | Outfit/packing/stylist generation — **in-process** (OpenAI/Gemini) |
| AI Chat | `/ai-chat/*` (SSE stream) | Conversational stylist with closet context (in-process, gated + grounded) |
| Shopping check | `/shopping/*` | In-store "should I buy this?" advisor |
| Purchase gaps | `/purchase-gaps` | Detects wardrobe gaps worth buying |
| RAG | `/rag/*`, `/fashion-knowledge` | Retrieval over fashion knowledge + closet (pgvector) |
| Analytics | `/analytics` | Closet usage stats |
| Internal | `app/api/internal.py` | `GET /internal/users/{id}` seam, guarded by `INTERNAL_SERVICE_TOKEN` |

Important behavior:
- Serves `/uploads/*` garment images (shared `uploads` volume; GCS optional).
- Embedding generation runs **in-process** via FastAPI BackgroundTasks
  (`similarity_service.schedule_embedding_update` → `update_item_embedding_job`).
- On account deletion the user row CASCADE-deletes their closet data in the same
  DB; a legacy cross-service purge seam exists but is a no-op (`CLOSET_SERVICE_URL`
  unset).
- Observability: Prometheus `/metrics`, optional Sentry + OpenTelemetry.

---

## 5. Vision pipeline (in api-gateway) — retired standalone service

There is no separate `vision-service` process anymore. Image analysis, smart
ingest, and background removal run **in-process inside the api-gateway** via its
wardrobe routers (see §4: *Smart ingest*, *Vision pipeline*). This matches
production, where the standalone service was never deployed.

The routes (`/analyze-vision`, `/analyze-vision/stream`, `/save-analyzed-items`,
`/smart-ingest`, `/closet/{id}/remove-background`) are served by the gateway and
write to the same `postgres` (clozehive) DB the gateway reads from.

Key internals (`app/api/v1/wardrobe/services/`): `vision_pipeline_service`
(parallelized detection + an OOM-guarded `img.draft()` reduced-scale JPEG decode),
`gemini_service` / `fashion_analysis_service` (model calls),
`background_removal_service`, `similarity_service` + `item_vision_enrichment`
(embeddings for closet matching). The CI drift gate
(`scripts/check_service_drift.py`) no longer pins any pairs — the gateway owns the
sole copy.

---

## 6. AI (in api-gateway) — retired standalone ai-agent / ai-worker

There is no separate `ai-agent` LLM service or `ai-worker` async-job consumer
anymore. The stylist chat, outfit generation, and trip packing all run
**in-process inside the api-gateway**:

- **Chat** (`/ai-chat/stream`): `ai_stylist_streaming.stream_chat_message` runs
  the model router + RAG pipeline over OpenAI/Gemini and streams SSE, behind the
  grounding gate and semantic cache.
- **Outfit** (`/ai/*`): `outfit_service.generate_outfits`.
- **Packing** (`/trips/*`, `/ai/packing`): `packing_service.generate_packing_list`
  — the single, closet-grounded, activity/bag-size-aware implementation.
- **Vision**: `vision_service` / `fashion_analysis_service` (see §5).

Personalization data (durable style memory, RAG corpus) lives in `postgres` via
pgvector. The async job path (`/ai/jobs/*` + an ARQ worker) was removed: it had
no frontend caller and was never deployed in production.

---

## 7. Data & infrastructure services

| Service | Image | Role |
|---|---|---|
| `postgres` (host `:5433`) | pgvector/pg16 | Everything the gateway owns: identity, auth, platform, **wardrobe domain** (incl. vision-ingested items), style memory / RAG vector store |
| `redis` (host `:6382`) | redis:7 | Cache — evictable (allkeys-lru). db0 gateway (incl. vision + AI response cache) |
| `redis-state` (host `:6383`) | redis:7 | **Non-evictable** (noeviction): OAuth state, refresh tokens, rate limits, WS tickets |
| `migrate` | run-once | Alembic `upgrade head` against `postgres` on every `compose up` |

---

## 8. Core workflows

### 8.1 Authentication

```mermaid
sequenceDiagram
    participant FE as frontend
    participant GW as api-gateway
    participant RS as redis-state
    FE->>GW: POST /api/v1/auth/login (or Google OAuth)
    GW->>RS: store refresh token / OAuth CSRF state
    GW-->>FE: access JWT + refresh token
    Note over FE: JWT sent on every request; validated<br/>locally in the gateway (shared JWT_SECRET)
```

### 8.2 Garment upload & analysis (production / in-process)

```mermaid
sequenceDiagram
    participant FE as Upload page
    participant GW as api-gateway
    participant LLM as Gemini / OpenAI Vision
    participant DB as postgres (clozehive)
    FE->>GW: POST /api/v1/analyze-vision/stream (photos)
    GW->>LLM: parallel per-image analysis
    GW-->>FE: SSE progress events per item
    FE->>GW: POST /api/v1/save-analyzed-items
    GW->>DB: insert closet items (+ in-process embeddings)
```

(Bulk path: `smart-ingest` creates a review session — analyze many photos,
user reviews/edits, then commits. This runs identically in dev and prod: all
in-process in the gateway.)

### 8.3 AI stylist chat (streaming)

```mermaid
sequenceDiagram
    participant FE as AIStylistChat
    participant GW as api-gateway
    participant LLM as OpenAI / Gemini
    FE->>GW: POST /api/v1/ai-chat/stream
    GW->>GW: build context: closet items, style memory, RAG (pgvector)
    GW->>LLM: model-routed chat completion
    LLM-->>GW: token stream
    GW->>GW: grounding gate + semantic cache
    GW-->>FE: SSE tokens
```

### 8.4 Trip packing

1. User creates a trip in TravelPlanner → `POST /trips` (api-gateway).
2. Packing generation runs in-process (`packing_service.generate_packing_list`):
   the weather layer fetches a live OpenWeather forecast for the destination
   (static climate profile fallback when no API key), and every outfit item is
   grounded against the user's real closet.
3. Packing-memory service stores user preferences to improve future lists.

### 8.5 Observability

- **Prometheus**: the gateway exposes `/metrics` (nginx blocks public access).
- **Sentry**: frontend + gateway (DSN optional).
- **RUM**: frontend web-vitals → gateway `/api/v1/platform/rum`.
- **LangSmith**: optional LLM tracing for the gateway's OpenAI/Gemini calls (env-gated).
- **WebSocket** (`/api/v1/ws` on the gateway): real-time notification channel.

---

## 9. Not part of the running system (excluded by design)

These exist in the repo but are **not wired** into the default stack:

- **`mcp-vision`** (`services/mcp/vision`) — legacy MCP vision server; the default
  stack runs vision analysis in-process inside the api-gateway instead.
- **Social domain** (`api-gateway/app/api/v1/social`, Groups page) — router is
  commented out (`# Non-MVP: Phase 2`); no backend routes are mounted.
