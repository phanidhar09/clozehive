# ─────────────────────────────────────────────────────────────────────────────
#  CLOZEHIVE — Developer Makefile
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help up down build migrate test lint clean logs shell-api shell-db

# Prefer repo-root .venv when present (see services/api-gateway/requirements-dev.txt).
PYTHON := $(shell test -x $(CURDIR)/.venv/bin/python && echo $(CURDIR)/.venv/bin/python || echo python3)

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker Compose ────────────────────────────────────────────────────────────

up: ## Start all services (detached)
	docker compose up -d --build

down: ## Stop all services and remove volumes
	docker compose down -v

build: ## Rebuild all Docker images
	docker compose build --no-cache

logs: ## Tail logs for all services
	docker compose logs -f --tail=100

logs-api: ## Tail API gateway logs
	docker compose logs -f api-gateway

logs-agent: ## Tail AI agent logs
	docker compose logs -f ai-agent

# ── Database ──────────────────────────────────────────────────────────────────

migrate: ## Run Alembic migrations
	docker compose run --rm migrate

migrate-create: ## Create a new migration (usage: make migrate-create MSG="add column")
	docker compose exec api-gateway alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Roll back one migration
	docker compose exec api-gateway alembic downgrade -1

# ── Testing ───────────────────────────────────────────────────────────────────

test: ## Run all tests
	$(MAKE) test-api test-frontend

test-api: ## Run API gateway tests
	cd services/api-gateway && $(PYTHON) -m pytest tests/ -v --tb=short

test-frontend: ## Run frontend tests
	cd frontend && npm run build

# ── Linting ───────────────────────────────────────────────────────────────────

lint: ## Lint all Python services
	cd services/api-gateway && ruff check app/
	cd services/ai-agent && ruff check app/
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

clean: ## Remove __pycache__, .pyc, dist, build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "dist" -not -path "*/node_modules/*" -exec rm -rf {} + 2>/dev/null; true
