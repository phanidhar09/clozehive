#!/usr/bin/env bash
set -euo pipefail

git pull

pushd frontend >/dev/null
npm ci
npm run build
popd >/dev/null

# Copy the built SPA into the nginx shared volume.
container_id="$(docker create -v closetiq-integrated_frontend-dist:/usr/share/nginx/html alpine:3.20 true)"
docker cp frontend/dist/. "${container_id}:/usr/share/nginx/html"
docker rm "${container_id}" >/dev/null

docker compose -f docker-compose.prod.yml build api-gateway
docker compose -f docker-compose.prod.yml up -d api-gateway nginx
docker compose -f docker-compose.prod.yml exec api-gateway alembic upgrade head
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

echo "Deployment complete."
