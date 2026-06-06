#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BRANCH="${DEPLOY_BRANCH:-main}"
REMOTE_NAME="${DEPLOY_REMOTE:-origin}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
RUN_HEALTH_CHECK="${RUN_HEALTH_CHECK:-true}"

echo "[deploy] Fetching latest code from ${REMOTE_NAME}/${BRANCH}"
git fetch "$REMOTE_NAME" "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only "$REMOTE_NAME" "$BRANCH"

echo "[deploy] Pulling latest container images (if any)"
docker compose -f "$COMPOSE_FILE" pull || true

echo "[deploy] Building and starting services"
docker compose -f "$COMPOSE_FILE" up -d --build

if [[ "$RUN_MIGRATIONS" == "true" ]]; then
  echo "[deploy] Running migrations"
  docker compose -f "$COMPOSE_FILE" run --rm migrate
  docker compose -f "$COMPOSE_FILE" run --rm migrate-closet
fi

if [[ "$RUN_HEALTH_CHECK" == "true" ]]; then
  echo "[deploy] Running health checks"
  ./scripts/check-health.sh
fi

echo "[deploy] Deployment complete"
