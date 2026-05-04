#!/usr/bin/env bash
set -euo pipefail

# Change these before running.
DOMAIN="${DOMAIN:-closetiq.example.com}"
EMAIL="${EMAIL:-admin@example.com}"

# Stop nginx so certbot standalone can bind to port 80 for initial issuance.
docker compose -f docker-compose.prod.yml stop nginx || true

# Request the first certificate. Replace DOMAIN and EMAIL above or pass them as env vars:
#   DOMAIN=app.example.com EMAIL=ops@example.com ./scripts/init-letsencrypt.sh
docker compose -f docker-compose.prod.yml run --rm --service-ports certbot certonly \
  --standalone \
  --preferred-challenges http \
  --agree-tos \
  --no-eff-email \
  --email "${EMAIL}" \
  -d "${DOMAIN}"

# Start nginx with the newly mounted certificate.
docker compose -f docker-compose.prod.yml up -d nginx

# Add this to the host crontab for renewal after confirming certbot works:
# 0 12 * * * cd /path/to/closetiq-integrated && docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
#
# Add this to the host crontab for daily database backups:
# 0 2 * * * /path/to/project/scripts/backup.sh >> /var/log/closetiq-backup.log 2>&1
echo "Certificate issued for ${DOMAIN}. Add the renewal cron line from this script after deployment."
