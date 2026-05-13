# ClozeHive — Environment & deployment guide

This document lists **required and optional** configuration, **how variables flow** in Docker vs host dev vs cloud, and **troubleshooting**. Templates live in:

| Location | Purpose |
|----------|---------|
| Repo root `.env.example` | **Primary** template for `docker compose` and shared values |
| `services/api-gateway/.env.example` | Service-local overrides when running the gateway without Compose |
| `frontend/.env.example` | Vite build/dev (`VITE_*` only) |
| `services/ai-agent/.env.example` | Optional AI agent (`--profile ai`) |

**Convention:** Copy the relevant example to `.env` (never commit real `.env`). The API gateway loads **repo root `.env` first**, then a `.env` in the current working directory (see `app/core/config.py`).

---

## 1. Required variables (backend — API gateway)

These are enforced by `Settings` in `services/api-gateway/app/core/config.py` (or are required for a working MVP).

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Async SQLAlchemy URL: `postgresql+asyncpg://user:password@host:port/dbname`. `postgres://` URLs from some hosts are auto-normalized to `postgresql+asyncpg://`. |
| `REDIS_URL` | Redis for cache, OAuth CSRF state, refresh-token sessions, closet preview staging. Example: `redis://localhost:6382/0` (host) vs `redis://redis:6379/0` (inside Compose). |
| `JWT_SECRET` | HMAC secret for access/refresh tokens. **Production:** must be ≥ 32 characters (`Settings` validation). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Short-lived JWT lifetime (default `15`). |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime (default `7`). |
| `OPENAI_API_KEY` | Chat, vision, embeddings (and similar) when not fully mocked. MVP features may degrade without it. |
| `GCS_BUCKET_NAME` | Set to use **Google Cloud Storage** for uploads; **leave empty** for local disk (`upload_dir`). |
| `GCS_CREDENTIALS_FILE` **or** `GCS_CREDENTIALS_JSON` | When using GCS: path to service-account JSON (preferred in Docker) **or** one-line JSON string. `GCS_PROJECT_ID` optional depending on setup. |
| `ALLOWED_ORIGINS` | Comma-separated browser origins for CORS (e.g. `https://app.example.com,https://www.example.com`). **Production** must not rely on `localhost` only. |
| `ENVIRONMENT` | `development` \| `staging` \| `production`. Enables stricter checks when `production`. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google OAuth; redirect URI must match the Google Cloud console exactly. **Redis must work** for OAuth CSRF state. |

**Also set for real deployments:**

| Variable | Description |
|----------|-------------|
| `FRONTEND_URL` | Where the SPA lives; used after OAuth and in links. |
| `AI_AGENT_URL` | Base URL of ai-agent (Compose default `http://ai-agent:8001`; host dev `http://localhost:8001`). |

---

## 2. Frontend (Vite)

Variables must be prefixed with `VITE_` to be exposed to the browser.

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | **Yes** (for real API calls) | Public URL of the API gateway **as the browser sees it**, e.g. `http://localhost:8000` or `https://api.yourdomain.com`. |
| `VITE_HIDE_NON_MVP` | No | Feature flag for nav/routes (default `true` in examples). |

Docker Compose often maps the frontend to **host port 3001**; ensure `ALLOWED_ORIGINS` and user bookmarks match the origin you actually use.

---

## 3. Optional variables

### 3.1 MCP / ai-agent

| Variable | Description |
|----------|-------------|
| `ENABLE_MCP_TOOLS` | When `true`, ai-agent connects to MCP HTTP/SSE tool URLs (requires reachable `mcp-*` services). Default `false` = LLM-only agent. |
| `MCP_WEATHER_URL`, `MCP_VISION_URL`, `MCP_OUTFIT_URL`, `MCP_PACKING_URL` | Defaults like `http://mcp-weather:8010/sse` for Docker; override for custom hosts. |

### 3.2 Kafka / Redpanda

| Variable | Description |
|----------|-------------|
| `KAFKA_ENABLED` | Gateway: enable Kafka producers/async routes when `true`. MVP Compose often sets `false`. |
| `KAFKA_BOOTSTRAP_SERVERS` | e.g. `redpanda:9092` in Compose, `localhost:19092` from host with `--profile ai`. |

### 3.3 Observability

| Variable | Description |
|----------|-------------|
| `SENTRY_DSN` | Error reporting (optional). |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT` | Tracing for OpenAI/LangChain paths (optional). |

### 3.4 Other useful gateway flags

See root `.env.example` for pool tuning (`DB_POOL_*`), `REDIS_CHECK_ON_READY`, `CLOSET_PREVIEW_TTL_SECONDS`, Gemini keys, OpenWeather, Firebase, etc.

---

## 4. Setup: local Docker (MVP)

1. `cp .env.example .env` at repo root and fill secrets (`JWT_SECRET`, `OPENAI_API_KEY`, Google OAuth, etc.).
2. Optional: `cp frontend/.env.example frontend/.env` if you need non-default `VITE_API_URL` for Vite on the host.
3. `make up` or `docker compose up --build -d`.
4. Migrations: `make migrate` (or rely on the `migrate` one-shot service if your compose stack runs it).
5. Health: `make health` or `curl http://localhost:8000/health`.

**Port reminders (defaults):**

- API: `8000` on host
- Frontend container: `3001` → `3000` in container (`FRONTEND_HOST_PORT`)
- Postgres: `5433` → `5432`
- Redis: `6382` → `6379`

Use a single root `.env` so Compose substitutes variables consistently.

---

## 5. Setup: local without Docker

1. Install Postgres (**pgvector** extension), Redis, and Python 3.11+ (or match the gateway Dockerfile).
2. From repo root: create `.env` from `.env.example`; point `DATABASE_URL` and `REDIS_URL` at **localhost** ports (not `postgres`/`redis` hostnames).
3. `pip install -r services/api-gateway/requirements-dev.txt` (or requirements + dev).
4. `cd services/api-gateway && alembic upgrade head` (see [§10 Troubleshooting](#10-troubleshooting) if `alembic` is missing).
5. Run gateway: `uvicorn app.main:app --reload --port 8000` from `services/api-gateway`.
6. Frontend: `cd frontend && npm ci && npm run dev`; set `VITE_API_URL=http://localhost:8000` (or your gateway port).

Start **ai-agent** separately if needed: `services/ai-agent` with its `.env` and `ENABLE_MCP_TOOLS` / `DATABASE_URL` / `REDIS_URL` aligned with your stack.

---

## 6. GCP: Cloud SQL (Postgres)

1. Create a **Postgres** instance (PostgreSQL 15+); enable the **pgvector** extension if you use embeddings:

   `CREATE EXTENSION IF NOT EXISTS vector;`

2. Use **Cloud SQL Auth Proxy** or **private IP + VPC** for secure access. The connection string in `DATABASE_URL` must be reachable from where the gateway runs (Cloud Run, GKE, VM, or local proxy).
3. Format:

   `postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/clozehive`

   when using the proxy on `127.0.0.1`, or the instance **Unix socket / private IP** form per Google’s docs.
4. Ensure **PostgreSQL user/password** match `DATABASE_URL` and firewall/authorized networks allow the client (see troubleshooting below).

---

## 7. GCP: private GCS bucket

1. Create a bucket; for **public object URLs** the bucket/object ACLs (or signed URLs) must match your product design. The gateway uses `gcs_bucket_name`; when set, uploads use GCS instead of local disk.
2. **Credentials (pick one):**

   - **`GCS_CREDENTIALS_FILE`**: path to JSON (in Docker, mount the file and set e.g. `/run/secrets/gcp-sa.json`).
   - **`GCS_CREDENTIALS_JSON`**: single-line JSON (`jq -c . key.json`) — avoid shell quoting issues.

3. On **GCP** (Cloud Run, GCE with default SA), Application Default Credentials may work without a file if the service account has **Storage Object Admin** (or tighter custom role) on the bucket.

---

## 8. Alembic migrations

- **Docker:** `docker compose exec api-gateway alembic upgrade head` (service name may vary; use the running gateway container).
- **Host:** `cd services/api-gateway && alembic upgrade head` with the same `DATABASE_URL` as runtime.
- **Production:** run `alembic upgrade head` in your deploy pipeline or maintenance window before switching traffic.

Ensure the working directory contains `alembic.ini` and `alembic/versions/`.

---

## 9. Tests (no cloud required)

Gateway integration tests use SQLite in-memory + mocks (see `services/api-gateway/tests/conftest.py`).

```sh
cd services/api-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest tests/ -v --tb=short
```

From repo root: `make test-api`. Frontend: `cd frontend && npm ci && npm run test`. See root `Readme.md` **Testing** section.

---

## 10. Troubleshooting

### `alembic: command not found`

- Run **`python -m alembic`** instead of `alembic`, or activate a venv where `requirements-dev.txt` was installed.
- In Docker, run **`alembic`** inside the **api-gateway** image (see [§8](#8-alembic-migrations)).

### Cloud SQL: connection denied / timeouts

- **Authorized networks:** instance must allow your client IP (or use proxy / private IP only from the right VPC).
- **SSL / proxy:** Cloud SQL often requires the **Auth Proxy** or SSL certs — verify the connection string matches the method you use.
- **Credentials:** wrong `DATABASE_URL` user/password or database name.

### GCS: `Unable to load PEM` / permission errors

- **File path:** inside containers, host paths like `/Users/...` are invalid — mount JSON into the container and set `GCS_CREDENTIALS_FILE` to the **in-container** path.
- **JSON in `.env`:** use **one line**, no extra quotes; large keys can get corrupted in `.env` — prefer **file mount**.
- **IAM:** service account needs roles on the target bucket.

### PaaS: no open ports / unhealthy service

- The web process must **listen on the platform-assigned `PORT`** and bind to `0.0.0.0` if the host requires it.
- **Health check:** use an HTTP path that returns **200** without auth (e.g. `/health`).
- Allow enough **startup time** for migrations or cold start before the first probe.

### Redis unavailable / `/ready` fails

- **`REDIS_URL`:** wrong host (`redis` vs `localhost`), port (container `6379` vs host-mapped `6382`), or DB index.
- Set **`REDIS_CHECK_ON_READY=false`** only for quick local experiments without Redis (not for production).
- **OAuth / refresh:** without Redis, token refresh and OAuth CSRF flows can break — fix Redis first.

### Token refresh failures (401 loops, logout)

- **CORS:** browser origin must be listed in **`ALLOWED_ORIGINS`**.
- **Redis:** refresh token storage must match the same **`REDIS_URL`** across workers/instances.
- **Clock skew:** large skew between client/server can expire JWTs early.
- **`VITE_API_URL`:** must point to the **same API** instance that issued tokens (no mixed staging/prod URLs).

---

## 11. Quick reference — Pydantic env names

The gateway maps `DATABASE_URL` → `database_url`, `JWT_SECRET` → `jwt_secret`, etc. (case-insensitive). Defaults for JWT:

- `ACCESS_TOKEN_EXPIRE_MINUTES` (default `15`)
- `REFRESH_TOKEN_EXPIRE_DAYS` (default `7`)

When in doubt, grep `services/api-gateway/app/core/config.py` for the field name and uppercase it for the environment variable.
