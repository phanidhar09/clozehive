# ─────────────────────────────────────────────────────────────────────────────
#  CLOZEHIVE — Developer Makefile
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help up stop down down-clean build migrate db-backup db-restore test test-api build-frontend test-frontend lint clean smoke health logs shell-api shell-db

# Prefer repo-root .venv when present (see services/api-gateway/requirements-dev.txt).
PYTHON := $(shell test -x $(CURDIR)/.venv/bin/python && echo $(CURDIR)/.venv/bin/python || echo python3)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker Compose ────────────────────────────────────────────────────────────

up: ## Start MVP stack (detached): postgres, redis, api-gateway, frontend, nginx
	docker compose up -d --build

stop: ## Stop containers, keep volumes intact  ← use this for daily dev
	docker compose down

down: ## Stop containers, keep volumes intact  ← same as stop (safe alias)
	docker compose down

down-clean: ## ⚠️  DANGER: stop AND delete all volumes (all data gone). Run db-backup first!
	@echo "⚠️  WARNING: This will DELETE all database data and uploaded images!"
	@echo "   Run 'make db-backup' first to save a copy."
	@read -p "   Type 'DELETE' to confirm: " CONFIRM && [ "$$CONFIRM" = "DELETE" ] || (echo "Cancelled." && exit 1)
	docker compose down -v
	@echo "✅ Volumes removed."

build: ## Rebuild all Docker images
	docker compose build --no-cache

logs: ## Tail logs for all services
	docker compose logs -f --tail=100

logs-api: ## Tail API gateway logs
	docker compose logs -f api-gateway

logs-agent: ## Tail AI agent logs
	docker compose logs -f ai-agent

logs-worker: ## Tail AI worker logs
	docker compose logs -f ai-worker

logs-kafka: ## Tail Redpanda logs
	docker compose logs -f redpanda kafka-topics

# ── Database ──────────────────────────────────────────────────────────────────

migrate: ## Run Alembic migrations
	docker compose run --rm migrate

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add column")
	docker compose exec api-gateway alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Roll back one migration
	docker compose exec api-gateway alembic downgrade -1

db-backup: ## Dump the database to ./backups/clozehive_TIMESTAMP.sql.gz
	@chmod +x scripts/backup.sh && ./scripts/backup.sh

db-restore: ## Restore from backup (usage: make db-restore FILE=backups/clozehive_xxx.sql.gz)
	@chmod +x scripts/restore.sh && ./scripts/restore.sh $(FILE)

db-status: ## Show row counts for all tables
	docker compose exec postgres psql -U clozehive -d clozehive -c \
	  "SELECT schemaname, relname AS table, n_live_tup AS rows FROM pg_stat_user_tables ORDER BY n_live_tup DESC;"

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## Run backend pytest + frontend Vitest
	$(MAKE) test-api test-frontend

test-api: ## Run API gateway tests
	cd services/api-gateway && $(PYTHON) -m pytest tests/ -v --tb=short

build-frontend: ## Build the frontend
	cd frontend && npm run build

test-frontend: ## Run frontend unit tests (Vitest)
	cd frontend && npm run test

# ── Linting ───────────────────────────────────────────────────────────────────

lint: ## Lint all Python services
	cd services/api-gateway && ruff check app/
	cd services/ai-agent && ruff check app/
	cd services/ai-worker && ruff check app/
	cd services/mcp && ruff check .

# ── Local dev (without Docker) ────────────────────────────────────────────────

dev-api: ## Start API gateway locally
	cd services/api-gateway && uvicorn app.main:app --reload --port 8000

dev-agent: ## Start AI agent locally
	cd services/ai-agent && uvicorn app.main:app --reload --port 8001

dev-frontend: ## Start frontend dev server
	cd frontend && npm run dev

dev-mcp-weather: ## Start weather MCP server locally
	cd services/mcp/weather && python server.py

# ── Utilities ─────────────────────────────────────────────────────────────────

shell-api: ## Shell into API gateway container
	docker compose exec api-gateway bash

shell-db: ## psql shell into PostgreSQL
	docker compose exec postgres psql -U clozehive -d clozehive

clean: ## Remove generated artifacts and local caches
	./scripts/clean-artifacts.sh

smoke: ## Validate Compose config and local service health
	./scripts/dev-smoke.sh

health: ## Check local service/container health
	./scripts/check-health.sh
