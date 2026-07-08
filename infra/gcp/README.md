# Deploying Clozehive to Google Cloud Run

> **Live production runs on Render** (`render.yaml`). This GCP Cloud Run path is
> an alternative deployment kept for portability; update it in lockstep with the
> Render blueprint.

Re-platforms the existing containers (the same ones in `docker-compose.yml` /
`render.yaml`) onto Cloud Run. The api-gateway owns the wardrobe domain (the
former `closet-service` was retired). Backing stores are **serverless add-ons**:

| Piece | Where | Notes |
|-------|-------|-------|
| Frontend, api-gateway | Cloud Run **services** | HTTP, autoscaling |
| Postgres | **Neon** | `db-url-core` — identity + wardrobe |
| Redis ×2 | **Upstash** | `redis-cache-url` (evictable) + `redis-state-url` (noeviction) |
| Uploads | **GCS bucket** | auth via runtime service account (ADC), no JSON key |

`min-instances=1` on api-gateway (always warm) and on the worker pool.

## Prerequisites

1. `gcloud` CLI installed and `gcloud auth login` done.
2. A GCP project with billing enabled.
3. A **Neon** account → create a project, then a database (e.g.
   `clozehive_core`). Copy the connection string.
4. An **Upstash** account → create **two Redis databases**. Set the cache one's
   eviction to `allkeys-lru` and the state one to `noeviction`. Copy both
   `rediss://` URLs.
5. A **Google OAuth client** (you likely already have one from Render).

## Steps

```bash
cd infra/gcp

# 1. Point config at your project (edit PROJECT_ID / REGION at minimum)
$EDITOR config.sh

# 2. Fill in your secrets
cp secrets.env.example secrets.env
$EDITOR secrets.env          # Neon URLs, Upstash URLs, OpenAI/Google keys…

# 3. Run the four scripts in order
./00-setup.sh    # APIs, Artifact Registry, GCS bucket, runtime SA + IAM
./01-secrets.sh  # push secrets.env → Secret Manager (auto-gens JWT/internal token)
./02-build.sh    # Cloud Build → 4 images in Artifact Registry
./03-deploy.sh   # deploy 3 services + worker pool, fully wired
```

The deploy prints the frontend + API URLs at the end.

## After first deploy

- **Google OAuth**: add `https://clozehive-api-<NUM>.<region>.run.app/api/v1/auth/google/callback`
  to *Authorized redirect URIs* and the frontend URL to *Authorized JavaScript
  origins*. `03-deploy.sh` echoes the exact values.
- **Custom domain** (optional): `gcloud run domain-mappings create --service clozehive-frontend --domain app.yourdomain.com`. Then add the domain to `ALLOWED_ORIGINS` / OAuth and redeploy.
- **DB migrations** run on startup (`RUN_MIGRATIONS_ON_STARTUP=true`), same as
  Render free-tier mode — no separate migration job needed.

## Day-2 operations

- **Redeploy after code change**: `./02-build.sh && ./03-deploy.sh`
  (or `TAG=$(git rev-parse --short HEAD) ./02-build.sh ./03-deploy.sh` for
  immutable tags + easy rollback).
- **Rotate a secret**: edit `secrets.env`, `./01-secrets.sh`, then redeploy the
  affected service (Cloud Run pins `:latest` at deploy time).
- **Logs**: `gcloud run services logs read clozehive-api --region <region>`.
- **Rollback**: `gcloud run services update-traffic clozehive-api --to-revisions <REV>=100`.

## Cost shape

Pay-per-use except api-gateway `min-instances=1`, which bills continuously
(~a few $/mo at idle). Neon + Upstash have free tiers. GCS is pennies.
Scale-to-zero on the frontend.
