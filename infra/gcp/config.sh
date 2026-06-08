# shellcheck shell=bash
# ─────────────────────────────────────────────────────────────────────────────
# Clozehive · Cloud Run deploy config — EDIT THESE, then `source config.sh`
# Every other script in this folder sources this file.
# ─────────────────────────────────────────────────────────────────────────────

# ── GCP project / location ───────────────────────────────────────────────────
export PROJECT_ID="${PROJECT_ID:-clozehive}"        # <-- your GCP project id
export REGION="${REGION:-us-central1}"              # Cloud Run + Artifact Registry region
export AR_REPO="${AR_REPO:-clozehive}"              # Artifact Registry repo name

# ── GCS bucket for uploads (must be globally unique) ─────────────────────────
export GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-clozehive-uploads-$PROJECT_ID}"

# ── Runtime service account (gets GCS + Secret Manager access) ───────────────
export RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-clozehive-run}"
export RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# ── Cloud Run service names ──────────────────────────────────────────────────
export SVC_API="clozehive-api"
export SVC_CLOSET="clozehive-closet"
export SVC_AGENT="clozehive-ai-agent"
export SVC_FRONTEND="clozehive-frontend"
export POOL_WORKER="clozehive-ai-worker"   # Cloud Run *worker pool* (no HTTP port)

# ── Derived: Artifact Registry image base ────────────────────────────────────
export IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}"

# ── Derived: deterministic Cloud Run service URLs ────────────────────────────
# Cloud Run URLs are stable: https://<service>-<project_number>.<region>.run.app
# We resolve the project number once so we can wire service-to-service URLs
# *before* the services exist (breaks the circular env dependency).
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null)"
export PROJECT_NUMBER
if [ -n "$PROJECT_NUMBER" ]; then
  export URL_API="https://${SVC_API}-${PROJECT_NUMBER}.${REGION}.run.app"
  export URL_CLOSET="https://${SVC_CLOSET}-${PROJECT_NUMBER}.${REGION}.run.app"
  export URL_AGENT="https://${SVC_AGENT}-${PROJECT_NUMBER}.${REGION}.run.app"
  export URL_FRONTEND="https://${SVC_FRONTEND}-${PROJECT_NUMBER}.${REGION}.run.app"
fi

# ── CORS / OAuth origins (set after frontend + api URLs are known) ───────────
export ALLOWED_ORIGINS="${URL_FRONTEND},${URL_API}"
export GOOGLE_REDIRECT_URI="${URL_API}/api/v1/auth/google/callback"

echo "✓ config loaded — project=$PROJECT_ID region=$REGION"
[ -z "$PROJECT_NUMBER" ] && echo "  ⚠  project number not resolved yet (run gcloud auth login / set PROJECT_ID)"
[ -n "$PROJECT_NUMBER" ] && echo "  api=$URL_API"
