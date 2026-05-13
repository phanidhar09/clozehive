#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

check_url() {
  local name="$1"
  local url="$2"

  printf "%-16s" "$name"
  curl -fsS "$url" >/dev/null
  echo "ok"
}

check_url_optional() {
  local name="$1"
  local url="$2"
  local hint="$3"

  printf "%-16s" "$name"
  if curl -fsS --connect-timeout 2 --max-time 5 "$url" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "skip (${hint})"
  fi
}

check_url "api-gateway" "http://localhost:8000/health"
check_url "api-gateway-live" "http://localhost:8000/live"
check_url "api-gateway-ready" "http://localhost:8000/ready"
check_url_optional "ai-agent" "http://localhost:8001/health" "use docker compose --profile ai"
check_url "frontend" "http://localhost:${FRONTEND_HOST_PORT:-3001}"

if command -v docker >/dev/null 2>&1; then
  docker compose ps
fi
