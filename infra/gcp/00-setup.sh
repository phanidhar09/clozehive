#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# One-time GCP setup: APIs, Artifact Registry, GCS bucket, runtime SA + IAM.
# Idempotent — safe to re-run.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

echo "▶ Enabling APIs…"
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project "$PROJECT_ID"

echo "▶ Artifact Registry repo ($AR_REPO)…"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location "$REGION" \
  --description="Clozehive service images" --project "$PROJECT_ID"

echo "▶ GCS uploads bucket ($GCS_BUCKET_NAME)…"
gcloud storage buckets describe "gs://$GCS_BUCKET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1 || \
gcloud storage buckets create "gs://$GCS_BUCKET_NAME" \
  --location "$REGION" --uniform-bucket-level-access --project "$PROJECT_ID"
# Public-read for uploaded images (matches Render's public-URL model).
# Skip this line if you set GCS_SIGNED_URLS=true instead (private bucket).
gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET_NAME" \
  --member=allUsers --role=roles/storage.objectViewer --project "$PROJECT_ID" || true

echo "▶ Runtime service account ($RUNTIME_SA)…"
gcloud iam service-accounts describe "$RUNTIME_SA" --project "$PROJECT_ID" >/dev/null 2>&1 || \
gcloud iam service-accounts create "$RUNTIME_SA_NAME" \
  --display-name="Clozehive Cloud Run runtime" --project "$PROJECT_ID"

echo "▶ Granting runtime SA access to bucket + secrets…"
gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET_NAME" \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/storage.objectAdmin --project "$PROJECT_ID"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor >/dev/null

echo "✓ setup complete. Next: ./01-secrets.sh"
