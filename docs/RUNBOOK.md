# ClozeHive — Operations Runbook

This document helps operators and developers run the stack locally, verify quality, deploy, debug common failures, and roll back safely.

---

## 1. Local development

### Prerequisites

- **Node.js** 20+ (match CI) and **npm** (this repo uses `package-lock.json` in `frontend/`).
- **Python** 3.11+ for the API gateway and **pip**.
- **Docker** and **Docker Compose** (recommended for PostgreSQL, Redis, and multi-service dev).
- **Git**.

### Environment variables

- Root **`.env`** and **`frontend/.env`** / **`services/api-gateway/.env`** — see **`.env.example`** at the repo root for canonical names.
- Frontend: `VITE_API_URL` must point at the gateway (e.g. `http://localhost:8000`) so uploads and API calls resolve correctly.
- Gateway: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, AI keys, and storage/GCP variables as required for your environment.

### Install

```bash
# Frontend
cd frontend && npm ci

# API gateway (virtualenv recommended)
cd services/api-gateway && pip install -r requirements.txt
```

### Start services

**Option A — Docker Compose (typical)**

**Phase 1 MVP (default):** postgres, redis, api-gateway, frontend, nginx, migrate

```bash
docker compose up --build
```

**Optional LangGraph agent + Redpanda + topic setup + Redpanda Console** — set `KAFKA_ENABLED=true` in `.env` so the API gateway publishes Kafka events:

```bash
docker compose --profile ai up --build
```

**Optional Kafka consumer worker** (also starts Redpanda, topics, and ai-agent):

```bash
docker compose --profile worker up --build
```

**Legacy MCP tool containers** (needed for ai-agent default `http://mcp-*` URLs; often used with `--profile ai`):

```bash
docker compose --profile legacy-mcp up --build
```

Validate the merged file: `docker compose config` (or `docker compose config --quiet`).

**Option B — Frontend + API locally**

```bash
# Terminal 1 — API (from services/api-gateway, with venv activated)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — SPA
cd frontend && npm run dev
```

### Database migrations

From `services/api-gateway` (with `DATABASE_URL` set):

```bash
alembic upgrade head
```

### Redis / Postgres via Docker

If you only need data stores:

```bash
docker compose up postgres redis
```

(Use the service names defined in your compose file.)

---

## 2. Quality checks

| Area        | Command (from `frontend/`) | Notes                          |
|------------|----------------------------|--------------------------------|
| Lint       | `npm run lint`             | ESLint with `--max-warnings 0` |
| Typecheck  | `npm run typecheck`        | `tsc --noEmit`                 |
| Tests      | `npm run test`             | Vitest single run              |
| Watch      | `npm run test:watch`       | Optional                       |
| Coverage   | `npm run test:coverage`    | Optional                       |
| Build      | `npm run build`            | Vite production build          |

**Backend (api-gateway):**

- Lint: `flake8 services/api-gateway/app --config services/api-gateway/.flake8`
- Types: `mypy services/api-gateway/app --ignore-missing-imports`
- Tests: `pytest services/api-gateway/tests/unit/ -v`

---

## 3. Deployment

- **Build frontend:** `cd frontend && npm ci && npm run build` — output in `frontend/dist`.
- **Run gateway:** production ASGI server (e.g. `uvicorn app.main:app --host 0.0.0.0 --port 8000`) or your platform’s command; ensure **`DATABASE_URL`**, **Redis**, **secrets**, and **CORS** match the deployed frontend origin.
- **Migrations:** run `alembic upgrade head` against the target database before or as part of release (with a maintenance window if needed).
- **Health:** confirm the gateway health route (as defined in `app/main.py`) returns success after deploy.
- **Ports:** on **Cloud Run** and other PaaS targets, ensure the process listens on the platform-assigned port and that health checks hit an HTTP path that does not require auth.

---

## 4. Common failures and fixes

| Symptom | Likely cause | What to do |
|--------|--------------|------------|
| Frontend build fails | Type error, missing env, or dependency drift | Run `npm run typecheck` and `npm run build` locally; run `npm ci` (not `npm install`) in CI. |
| TypeScript errors | Strict mode or API type drift | Fix types or align `frontend/src/types` with gateway schemas. |
| ESLint fails | New code or warnings treated as errors | Run `npm run lint` locally; fix or narrowly document suppressions. |
| API connection / CORS | Wrong `VITE_API_URL` or gateway CORS config | Align origin and `VITE_API_URL`; verify gateway allows the SPA origin. |
| DB connection errors | Bad `DATABASE_URL`, network, or TLS | Test from the same network as the app; verify credentials and DB availability. |
| Migration errors | Out-of-order migrations or dirty DB | Inspect Alembic history; restore from backup before re-running destructive steps. |
| Redis errors | Redis down or wrong `REDIS_URL` | Start Redis; confirm URL and auth. |
| Upload / storage errors | Missing bucket/credentials or wrong path | Verify GCS (or other) credentials and that `/uploads` or signed URLs match deployment. |
| GCS / GCP credentials | Invalid JSON key or wrong project | Mount or inject service account; never commit keys (use `gcp-sa.json.template` patterns). |
| PaaS “no open ports” / probe failures | App not listening on `$PORT` | Bind to `0.0.0.0` and the platform port; fix health check path. |
| Docker daemon not running | Local Docker stopped | Start Docker Desktop / daemon. |
| Port conflicts | Another process on 3000/8000 | Change Vite port or gateway port in env/compose. |

---

## 5. Rollback plan

- **Frontend:** redeploy the previous build artifact or git tag; keep `dist` or container image history.
- **Backend:** redeploy previous container/image; ensure env vars unchanged.
- **Database:** avoid destructive migrations without backup; to roll back a migration, use a **downgrade** only if the team maintains reversible migrations and you have verified data safety. **Take a backup before** any production migration.

---

## 6. Production checklist

- [ ] Secrets and service account JSON are **not** committed.
- [ ] All required **environment variables** set in each environment.
- [ ] **Migrations** applied and verified.
- [ ] **Health** endpoint responds.
- [ ] **Auth** routes remain protected; tokens and refresh flow tested.
- [ ] **Upload storage** durable and URLs resolve from the client.
- [ ] **Lint, typecheck, tests, build** green on CI.
- [ ] **CI** workflow runs real lint/test/build (no skipped “fake” steps).

---

## 7. CI reference

The **GitHub Actions** workflow (`.github/workflows/ci.yml`) runs:

1. Backend: flake8 + mypy  
2. Frontend: `npm ci` → `npm run lint` → `npm run typecheck` → `npm run test` → `npm run build`  
3. Backend: pytest with Postgres + Redis services  
4. Docker image builds for gateway and frontend  

Failure in any required step fails the pipeline.
