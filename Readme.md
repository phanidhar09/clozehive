# ClozeHive

Canonical architecture:

- `frontend` — React + Vite
- `services/api-gateway` — public FastAPI API layer
- `services/ai-agent` — FastAPI + LangGraph AI orchestration
- `services/mcp/*` — independent MCP tool services

Legacy stacks were archived under `archive/legacy-2026-04-28`.

## Local Development

```sh
docker compose up --build
```

Health checks:

```sh
curl http://localhost:8000/health      # API gateway
curl http://localhost:8001/health      # AI agent
curl http://localhost:3001             # Frontend
```

For non-Docker development, start dependencies first, then run:

```sh
npm run dev:api
npm run dev:agent
npm run dev:frontend
```