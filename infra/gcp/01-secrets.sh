#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Push every value from secrets.env into Secret Manager (create or add version).
# Idempotent — re-run to rotate a secret (adds a new :latest version).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

[ -f ./secrets.env ] || { echo "✗ create infra/gcp/secrets.env from secrets.env.example first"; exit 1; }
# shellcheck disable=SC1091
set -a; source ./secrets.env; set +a

# Auto-generate shared secrets if left blank.
: "${JWT_SECRET:=$(openssl rand -hex 32)}"
: "${INTERNAL_SERVICE_TOKEN:=$(openssl rand -hex 32)}"

put_secret() {
  local name="$1" value="$2"
  [ -z "$value" ] && { echo "  – skip $name (empty)"; return; }
  if gcloud secrets describe "$name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- --project "$PROJECT_ID" >/dev/null
  else
    printf '%s' "$value" | gcloud secrets create "$name" --data-file=- --replication-policy=automatic --project "$PROJECT_ID" >/dev/null
  fi
  echo "  ✓ $name"
}

echo "▶ Writing secrets to Secret Manager…"
put_secret db-url-core            "$DB_URL_CORE"
put_secret db-url-closet          "$DB_URL_CLOSET"
put_secret redis-cache-url        "$REDIS_CACHE_URL"
put_secret redis-state-url        "$REDIS_STATE_URL"
put_secret jwt-secret             "$JWT_SECRET"
put_secret internal-service-token "$INTERNAL_SERVICE_TOKEN"
put_secret openai-api-key         "$OPENAI_API_KEY"
put_secret gemini-api-key         "$GEMINI_API_KEY"
put_secret openweather-api-key    "$OPENWEATHER_API_KEY"
put_secret google-client-id       "$GOOGLE_CLIENT_ID"
put_secret google-client-secret   "$GOOGLE_CLIENT_SECRET"
put_secret sentry-dsn             "$SENTRY_DSN"

echo "✓ secrets done. Next: ./02-build.sh"
