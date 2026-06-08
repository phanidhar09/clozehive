#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Build + push all 5 images to Artifact Registry via Cloud Build.
# Each backend service builds from its own dir (matches its Dockerfile context).
# The frontend builds with VITE_API_URL baked in (browser calls api-gateway).
# Run from repo root context; paths below are repo-relative.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
REPO_ROOT="$(cd ../.. && pwd)"
TAG="${TAG:-latest}"

build_backend() {
  local svc_dir="$1" image="$2"
  echo "▶ building $image"
  gcloud builds submit "$REPO_ROOT/$svc_dir" \
    --tag "$image:$TAG" --project "$PROJECT_ID" --region "$REGION"
}

build_backend services/api-gateway    "$IMAGE_BASE/api-gateway"
build_backend services/closet-service  "$IMAGE_BASE/closet-service"
build_backend services/ai-agent        "$IMAGE_BASE/ai-agent"
build_backend services/ai-worker       "$IMAGE_BASE/ai-worker"

echo "▶ building frontend (VITE_API_URL=$URL_API)"
gcloud builds submit "$REPO_ROOT/frontend" \
  --config ./cloudbuild.frontend.yaml \
  --substitutions "_IMAGE=$IMAGE_BASE/frontend:$TAG,_VITE_API_URL=$URL_API" \
  --project "$PROJECT_ID" --region "$REGION"

echo "✓ all images pushed. Next: ./03-deploy.sh"
