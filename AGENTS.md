# AGENTS.md

Guidance for AI coding agents (Claude Code, Cursor, etc.) working in the
ClozehHive repository. Humans should read [Readme.md](Readme.md) and
[docs/](docs/) first; this file is the quick operational contract for agents.

## What this is

ClozehHive is an AI wardrobe / personal-styling app: users upload closet items,
get AI outfit suggestions, packing lists, and a stylist chat. It is a
**polyglot monorepo** — a React frontend plus several Python (FastAPI)
microservices — orchestrated with Docker Compose locally and deployed on
**Render** (`render.yaml`).

## Architecture

| Path | Stack | Responsibility |
|------|-------|----------------|
| `frontend/` | React 18 + Vite + TypeScript + Tailwind | SPA, PWA, served via nginx |
| `services/api-gateway/` | FastAPI + SQLAlchemy (async) + Alembic | The application. Auth, closet, outfits, trips, analytics, RAG, the public `/api/v1` surface, **and the image-detection / background-removal vision pipeline in-process**. Most AI (stylist chat, outfit scoring, vision) runs here directly against OpenAI/Gemini — not via `ai-agent`. |
| `services/ai-agent/` | FastAPI + LangGraph | FANI agent with inline tools. Currently used only by the WebSocket floating chat and the conditional packing path; its `/outfit` and `/vision/analyze` endpoints are unused (the gateway owns those). |
| `services/ai-worker/` | ARQ (Redis queue) | Durable background AI jobs, gated by `HEAVY_WORK_ASYNC` (**off by default**, not in `render.yaml`). When enabled it proxies back to `ai-agent`. |
| `services/mcp/` | MCP servers | Optional/legacy tool servers (e.g. vision), only under the `--profile vision` compose profile. |
| `infra/`, `nginx/` | nginx, configs | Edge / reverse proxy |

> **Reality check:** the docs above once described a fuller microservice mesh. In
> practice this is a **modular monolith** (`api-gateway`) plus a lightly-used
> `ai-agent`. The former `closet-service` and `vision-service` splits were
> retired and deleted; the gateway is the sole owner of the closet + vision
> stack. Treat `ai-worker` and `mcp/*` as optional/dormant unless explicitly
> enabled.

**Data stores:** PostgreSQL (primary + closet DB, optional read replica via
`DATABASE_READ_URL`); two Redis roles — **cache** (`REDIS_URL`, evictable) and
**state** (`REDIS_STATE_URL`, non-evictable: OAuth CSRF state, refresh tokens,
rate limits, ARQ queue). Never put security/session state on the cache Redis.

## Setup & common commands

Use the **Makefile** — it is the source of truth. `make help` lists everything.

```bash
make up              # start full stack (docker compose, detached)
make stop            # stop containers, keep data  ← daily dev
make migrate         # run Alembic migrations
make test            # backend pytest + frontend Vitest
make lint            # ruff across all Python services
make logs-api        # tail a service's logs (also logs-agent, logs-worker)
```

Local dev without Docker: `make dev-api` (port 8000), `make dev-agent` (8001),
`make dev-frontend` (3000).

Frontend (run inside `frontend/`):

```bash
npm run dev          # vite dev server on :3000
npm run typecheck    # tsc --noEmit  ← run after TS changes
npm run lint         # eslint, zero-warnings policy
npm run test         # vitest run
npm run test:e2e     # playwright
```

Backend (run inside `services/api-gateway/`):

```bash
python -m pytest tests/ -v --tb=short
ruff check app/                       # lint
ruff format app/                      # format
mypy app --ignore-missing-imports     # types
```

## Code conventions

### Backend (Python)

- **Python 3.12**, FastAPI, fully **async** SQLAlchemy. Never block the event
  loop — use `httpx`/async drivers, not `requests` or sync I/O in request paths.
- The api-gateway uses **domain-oriented vertical slices** under
  `app/api/v1/<domain>/` (`identity`, `wardrobe`, `intelligence`, `social`,
  `travel`, `platform`). Each domain owns its `routes`, `schemas/`,
  `services/`, and `repositories/`. Put new endpoints in the matching domain,
  not in a flat module.
- Lint/format with **ruff**; type-check with **mypy**. CI fails on violations.
- Logging is **structlog** — `logger = structlog.get_logger("name")` and log
  structured key/values (`logger.warning("event_name", error=..., user_id=...)`),
  never bare f-strings. Do **not** log secrets, tokens, passwords, or raw PII.
- Heavy/slow work (embeddings, vision) belongs **off the request path**: use
  `schedule_embedding_update(background_tasks, ...)` or the ARQ queue, never a
  synchronous call inside the handler.

### Frontend (TypeScript / React)

- Functional components + hooks. State via the store in `src/store/`.
- All HTTP goes through `src/lib/api.ts` (axios with the 401-refresh
  interceptor) — do not create ad-hoc axios instances.
- Tailwind for styling; shared primitives live in `src/components/`.
- `npm run typecheck` and `npm run lint` must pass (zero eslint warnings).

## Database & migrations

- Schema changes require an **Alembic migration**:
  `make migrate-create MSG="describe change"`, review the generated file, then
  `make migrate`. Never hand-edit applied migrations.
- `make db-backup` before anything destructive. `make down-clean` deletes all
  volumes — only with an explicit, confirmed request.

## Security (this app is auth-heavy — treat it carefully)

- Compare secrets/tokens with `hmac.compare_digest`, never `==`.
- OAuth CSRF state lives on the **state** Redis and must be consumed atomically
  (`state_getdel`). Only link a Google identity to an existing account when the
  email is **verified**.
- Keep `gcp-sa.json`, `.env`, and any credentials out of commits. Configuration
  is via env vars (see `.env.example` and [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)).
- See [SECURITY.md](SECURITY.md) for the full policy.

## Testing expectations

- Add or update tests alongside code changes. Backend tests live in
  `services/api-gateway/tests/<domain>/`; frontend tests sit next to the code
  (`*.test.ts(x)`).
- Before declaring a task done, run the relevant `make test` / `npm run test`
  and `lint`/`typecheck`. Report failures with their output — do not claim
  green without running them.

## Working agreements for agents

- Match the surrounding code's style, naming, and structure; prefer reusing the
  existing helper over re-implementing one (grep `services/` and `src/lib/`).
- Keep changes scoped to the request. Flag unrelated issues rather than
  fixing them inline.
- Commit/push only when explicitly asked. Branch off `main` first.
- Don't add dependencies without need; check `package.json` / `requirements*.txt`
  for something that already does the job.
