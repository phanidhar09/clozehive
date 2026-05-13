# ClozeHive

ClozeHive is a wardrobe intelligence app: digital closet, outfit building, travel
and packing ideas, analytics, and an AI stylist backed by your own items. The
stack is a **React + Vite** frontend, a **FastAPI** API gateway (auth, closet,
embeddings, outfits, trips, analytics, smart ingest), **LangGraph**-style AI
orchestration in the **ai-agent** service, optional **Kafka / Redpanda** for
async AI jobs via **ai-worker**, and small **MCP** tool services (weather,
vision, outfit, packing) that can still be run under a Docker profile for
legacy setups.

**Repository:** [github.com/phanidhar09/clozehive](https://github.com/phanidhar09/clozehive)

The local folder may still be named `closetiq-integrated`; **ClozeHive** is the
product name used in docs and env templates.

**Environment variables, Docker, GCP, migrations, tests, troubleshooting:** see **[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)**.

## Architecture

```mermaid
flowchart LR
  Browser[Frontend] --> ApiGateway[API Gateway]
  ApiGateway --> Postgres[(Postgres + pgvector)]
  ApiGateway --> Redis[(Redis)]
  ApiGateway --> OpenAI[OpenAI / Weather APIs]
```

**Phase 1 default `docker compose up`** runs only the gateway stack above.
Optional Compose profiles add **Redpanda**, **ai-agent**, **ai-worker**, and/or **legacy MCP** services when you need LangGraph tools or Kafka async jobs (see [Local setup with Docker](#local-setup-with-docker)).

## Service responsibilities

| Area | Role |
|------|------|
| `frontend` | React app; Vite dev server or static build. In **Docker**, host port defaults to **3001** → container **3000** (`FRONTEND_HOST_PORT`). |
| `services/api-gateway` | Public API: JWT + Google OAuth, closet CRUD, vector search, outfits, trips, analytics, health, rate limiting, security headers, Kafka producers, optional Firestore paths. |
| `services/ai-agent` | FastAPI + LangGraph agent; MCP tools **optional** (`ENABLE_MCP_TOOLS`, default off in Compose). Chat works LLM-only without mcp-* containers. |
| `services/ai-worker` | Kafka consumer for background AI request handling. |
| `services/mcp/*` | Optional MCP microservices (weather, vision, outfit, packing). |
| `nginx/` | Reverse proxy / TLS-oriented config for production-style hosting. |
| `infra/` | Postgres init, Kafka topic scripts, local infra glue. |

Legacy stacks, if present, live under `archive/`.

## Local setup with Docker

1. Copy the environment template and fill in secrets:

   ```sh
   cp .env.example .env
   ```

   For frontend-only overrides (e.g. `VITE_API_URL`, feature flags), you can use
   `frontend/.env.example` → `frontend/.env`.

2. Start the stack (**MVP — postgres, redis, api-gateway, frontend, nginx, migrate**):

   ```sh
   make up
   ```

   Or: `docker compose up --build` (add `-d` to detach).

   **Optional AI stack** (Redpanda, Kafka topics, Redpanda Console, ai-agent). Set `KAFKA_ENABLED=true` in `.env` when you need the gateway to publish Kafka events. Ai-agent defaults to **LLM-only chat** (`ENABLE_MCP_TOOLS=false`); no mcp-* containers required:

   ```sh
   docker compose --profile ai up --build
   ```

   For **MCP-backed** routes on ai-agent (`/api/v1/agent/outfit`, `/packing`, `/vision/analyze`), set **`ENABLE_MCP_TOOLS=true`** and start legacy MCP (tool hosts must resolve):

   ```sh
   docker compose --profile ai --profile legacy-mcp up --build
   ```

   **Background worker** (pulls in Redpanda + ai-agent automatically):

   ```sh
   docker compose --profile worker up --build
   ```

   **Legacy MCP** containers (for ai-agent tool URLs `http://mcp-*` — combine with `--profile ai` when testing the agent):

   ```sh
   docker compose --profile legacy-mcp up --build
   ```

3. Run migrations (if the `migrate` service has not already applied them):

   ```sh
   make migrate
   ```

4. Check health:

   ```sh
   make health
   ```

### Useful URLs (default Docker / local)

| Service | URL |
|---------|-----|
| Frontend | `http://localhost:3001` (override with `FRONTEND_HOST_PORT`) |
| API gateway | `http://localhost:8000` — `/health`, `/live`, `/ready` |
| OpenAPI docs | `http://localhost:8000/docs` |
| AI agent | `http://localhost:8001/health` (only with `--profile ai` or `--profile worker`) |
| Redpanda Console | `http://localhost:8080` (same) |

**Port note:** `.env.example` uses `FRONTEND_PORT=3000` and `VITE_API_URL` for
**host-side** Vite dev; the **Compose** frontend mapping defaults to **3001** on
the host so it does not clash with other tools. Align `VITE_API_URL` and
`ALLOWED_ORIGINS` with whichever origin you actually use.

### Optional legacy MCP stack

Standalone MCP containers are behind the `legacy-mcp` profile. The **ai-agent**
service is behind `--profile ai` / `--profile worker`; MCP hostnames only resolve
when that profile (and usually `legacy-mcp`) is active:

```sh
docker compose --profile ai --profile legacy-mcp up -d
```

## Production-oriented compose

For a slimmer deployment (nginx, API gateway, Postgres, Redis, Certbot-oriented
pieces), see `docker-compose.prod.yml` and `nginx/nginx.conf`. Adjust env vars
for your provider; helper scripts live under `scripts/` (e.g. deploy, backup,
restore, LetsEncrypt init). Production compose disables Kafka by default
(`KAFKA_ENABLED: "false"` in that file)—enable and wire brokers if you need
async workers in prod.

## Local setup without Docker

Start Postgres (with pgvector), Redis, and Redpanda, then:

```sh
npm --prefix frontend install
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r services/api-gateway/requirements-dev.txt
pip install -r services/ai-agent/requirements.txt
```

Run services in separate terminals:

```sh
make dev-api        # API gateway :8000
make dev-agent      # AI agent :8001
make dev-frontend   # Vite (see frontend/package.json for port)
```

## Environment variables

Use **`.env.example`** as the source of truth. Commonly customized values:

- **`OPENAI_API_KEY`** — direct stylist chat/streaming, image analysis (vision), and embeddings.
- **`OPENAI_MODEL`** / **`OPENAI_MAX_TOKENS`** — chat and vision model defaults (`gpt-4o`, `1024`).
- **`JWT_SECRET`** — use a long random value; never ship the dev default.
- **`DATABASE_URL`** — host dev often uses Postgres on **`5433`** (see example).
- **`REDIS_URL`** — host dev often uses **`6382`** (Compose default; override with **`REDIS_HOST_PORT`**).
- **`ENABLE_MCP_TOOLS`** — ai-agent only; default **false** in Compose. Set **true** with legacy MCP for direct tool HTTP routes on the agent.
- **`KAFKA_BOOTSTRAP_SERVERS`** — `redpanda:9092` inside Docker, `localhost:19092` from the host (only when Redpanda profile is enabled).
- **`ALLOWED_ORIGINS`** — must include your real frontend origin(s).
- **Google OAuth** — `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
- **Frontend** — `VITE_API_URL`, **`VITE_HIDE_NON_MVP`** (toggle non-MVP nav).
- **Optional** — OpenWeather, Sentry, Firebase / Firestore.

Never commit a real `.env` file.

## Testing (Phase 1 / MVP regression)

**API gateway** tests use **in-memory SQLite**, **fake Redis**, an **in-memory cache**
(for closet preview sessions), and **stubbed** `ai_client.generate_packing_list` (no
HTTP to ai-agent, **no OpenAI**, **no GCS**, **no weather**). Embeddings are no-ops.

```sh
cd services/api-gateway
python3 -m venv .venv && source .venv/bin/activate   # or use repo-root .venv
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v --tb=short
```

From repo root: `make test-api`.

**Frontend** (Vitest + Testing Library):

```sh
cd frontend && npm ci && npm run test
```

From repo root: `make test-frontend`. Run both: `make test`.

Coverage includes auth (register / login / refresh), closet CRUD + ownership +
preview/confirm flow, and trips + packing persistence. See `tests/conftest.py` and
`tests/integration/` in `services/api-gateway`.

## Common commands

```sh
make help             # list Makefile targets
make up               # build and start Docker services (detached)
make stop             # compose down (keep volumes)
make down             # compose down and remove volumes
make logs             # tail service logs
make migrate          # Alembic via migrate container
make test-api         # pytest in services/api-gateway (SQLite + mocks; no cloud)
make test-frontend    # Vitest in frontend/
make test             # test-api + test-frontend
make build-frontend   # production build
make smoke            # compose config + health checks
make clean            # clean generated artifacts (see scripts/clean-artifacts.sh)
```

## Verification

```sh
docker compose config
docker compose config --quiet
make smoke
make build-frontend
```

### Dependency audits

```sh
npm audit --prefix frontend
pip install pip-audit && pip-audit -r services/api-gateway/requirements.txt
```

### API health endpoints

- **`GET /live`** — process is up (liveness).
- **`GET /ready`** — DB and Redis when `REDIS_CHECK_ON_READY=true`.
- **`GET /health`** — aggregate JSON for operators.

### Tests

```sh
cd services/api-gateway
python -m pytest tests/ -v --tb=short
```

## Troubleshooting

- **OpenAI errors** — Confirm `OPENAI_API_KEY` in `.env`; if you use **`--profile ai`**, restart `ai-agent` (and vision MCP with `legacy-mcp` if you use it).
- **Redpanda** — Only started with `--profile ai` or `--profile worker`; `docker compose ps` and `docker compose logs redpanda kafka-topics`.
- **API → AI agent** — Optional: with profiles enabled, `AI_AGENT_URL` should be `http://ai-agent:8001`. Without ai-agent, trip packing falls back to the gateway.
- **Browser → API** — `VITE_API_URL` should match reachable host URL (often
  `http://localhost:8000`).
- **CORS** — Ensure `ALLOWED_ORIGINS` includes the exact frontend origin.
- **Stale build output** — `make clean`, then rebuild what you need.
