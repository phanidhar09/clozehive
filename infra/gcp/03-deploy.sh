#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Deploy the 3 HTTP services + the ARQ worker pool to Cloud Run.
# Service-to-service URLs are wired from the deterministic URLs in config.sh,
# so order doesn't matter and there's no circular dependency.
# Idempotent — re-run to roll out a new image or env change.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
TAG="${TAG:-latest}"
D='^##^'   # env-var delimiter so values may contain commas (ALLOWED_ORIGINS)

COMMON=( --region "$REGION" --project "$PROJECT_ID"
         --service-account "$RUNTIME_SA" --execution-environment gen2 )

OPENAI_COMMON="OPENAI_MODEL=gpt-4o##OPENAI_API_BASE_URL=https://api.openai.com/v1##OPENAI_MAX_TOKENS=1024"

# ── api-gateway (public, always-warm) ────────────────────────────────────────
echo "▶ deploy $SVC_API"
gcloud run deploy "$SVC_API" --image "$IMAGE_BASE/api-gateway:$TAG" "${COMMON[@]}" \
  --port 8000 --allow-unauthenticated --min-instances 1 --max-instances 5 \
  --memory 1Gi --cpu 1 --timeout 300 --concurrency 80 \
  --set-env-vars "${D}ENVIRONMENT=production##SERVE_MIGRATED_DOMAIN_ROUTES=true##DEBUG=false##LOG_LEVEL=INFO##REDIS_CHECK_ON_READY=true##SHUTDOWN_DRAIN_SECONDS=5##ENABLE_METRICS=true##OTEL_ENABLED=false##OTEL_SERVICE_NAME=api-gateway##KAFKA_ENABLED=false##${OPENAI_COMMON}##OPENAI_EMBEDDING_MODEL=text-embedding-3-small##ACCESS_TOKEN_EXPIRE_MINUTES=15##REFRESH_TOKEN_EXPIRE_DAYS=7##COOKIE_SECURE=true##COOKIE_SAMESITE=Lax##VISION_PREVIEW_FAST=true##RAG_VECTOR_STORE=pgvector##AI_TIMEOUT_SECONDS=90##RUN_MIGRATIONS_ON_STARTUP=true##FAIL_ON_STARTUP_MIGRATION_ERROR=true##HEAVY_WORK_ASYNC=true##AI_AGENT_URL=${URL_AGENT}##FRONTEND_URL=${URL_FRONTEND}##ALLOWED_ORIGINS=${ALLOWED_ORIGINS}##GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI}##GCS_BUCKET_NAME=${GCS_BUCKET_NAME}##GCS_PROJECT_ID=${PROJECT_ID}" \
  --set-secrets "DATABASE_URL=db-url-core:latest,REDIS_URL=redis-cache-url:latest,REDIS_STATE_URL=redis-state-url:latest,ARQ_REDIS_URL=redis-state-url:latest,JWT_SECRET=jwt-secret:latest,INTERNAL_SERVICE_TOKEN=internal-service-token:latest,OPENAI_API_KEY=openai-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest,OPENWEATHER_API_KEY=openweather-api-key:latest,GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,SENTRY_DSN=sentry-dsn:latest"

# ── ai-agent (public surface; protected by internal token) ───────────────────
echo "▶ deploy $SVC_AGENT"
gcloud run deploy "$SVC_AGENT" --image "$IMAGE_BASE/ai-agent:$TAG" "${COMMON[@]}" \
  --port 8001 --allow-unauthenticated --min-instances 0 --max-instances 3 \
  --memory 1Gi --cpu 1 --timeout 300 --concurrency 40 \
  --set-env-vars "${D}ENVIRONMENT=production##DEBUG=false##LOG_LEVEL=INFO##OPENAI_MODEL=gpt-4o##OPENAI_EMBEDDING_MODEL=text-embedding-3-small##OPENAI_API_BASE_URL=https://api.openai.com/v1##VECTOR_STORE=pgvector##ENABLE_MCP_TOOLS=false##ENABLE_MCP_VISION=false" \
  --set-secrets "DATABASE_URL=db-url-core:latest,REDIS_URL=redis-cache-url:latest,INTERNAL_SERVICE_TOKEN=internal-service-token:latest,OPENAI_API_KEY=openai-api-key:latest,OPENWEATHER_API_KEY=openweather-api-key:latest"

# ── frontend (nginx static SPA; VITE_API_URL baked at build time) ────────────
echo "▶ deploy $SVC_FRONTEND"
gcloud run deploy "$SVC_FRONTEND" --image "$IMAGE_BASE/frontend:$TAG" "${COMMON[@]}" \
  --port 3000 --allow-unauthenticated --min-instances 0 --max-instances 3 \
  --memory 256Mi --cpu 1 --concurrency 200

# ── ai-worker (ARQ) — Cloud Run worker pool, no HTTP port, CPU always on ──────
echo "▶ deploy worker pool $POOL_WORKER"
gcloud beta run worker-pools deploy "$POOL_WORKER" --image "$IMAGE_BASE/ai-worker:$TAG" \
  --region "$REGION" --project "$PROJECT_ID" --service-account "$RUNTIME_SA" \
  --min-instances 1 --max-instances 3 --memory 1Gi --cpu 1 \
  --set-env-vars "${D}ENVIRONMENT=production##LOG_LEVEL=INFO##AI_AGENT_URL=${URL_AGENT}##GATEWAY_INTERNAL_URL=${URL_API}" \
  --set-secrets "DATABASE_URL=db-url-core:latest,REDIS_URL=redis-state-url:latest,INTERNAL_SERVICE_TOKEN=internal-service-token:latest,OPENAI_API_KEY=openai-api-key:latest"

echo
echo "✓ deploy complete."
echo "  Frontend : $URL_FRONTEND"
echo "  API      : $URL_API"
echo
echo "Post-deploy: add $GOOGLE_REDIRECT_URI to your Google OAuth client's"
echo "Authorized redirect URIs, and $URL_FRONTEND to Authorized JS origins."
