#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  ClozéHive — PostgreSQL backup script
#  Usage: ./scripts/backup.sh
#  Creates a timestamped .sql.gz dump in ./backups/
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
DB_CONTAINER="${DB_CONTAINER:-clozehive-postgres-1}"
DB_NAME="${POSTGRES_DB:-clozehive}"
DB_USER="${POSTGRES_USER:-clozehive}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/clozehive_$TIMESTAMP.sql.gz"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"

echo "📦 Starting backup → $BACKUP_FILE"
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ ! -s "$BACKUP_FILE" ]; then
  echo "❌ ERROR: Backup file is empty or missing"
  exit 1
fi

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "✅ Backup complete: $BACKUP_FILE ($BACKUP_SIZE)"

# Optional: upload to S3 if configured
if command -v aws &> /dev/null && [ -n "${S3_BACKUP_BUCKET:-}" ]; then
  aws s3 cp "$BACKUP_FILE" "s3://$S3_BACKUP_BUCKET/backups/"
  echo "☁️  Uploaded to S3: s3://$S3_BACKUP_BUCKET/backups/"
fi

# Remove backups older than RETENTION_DAYS
find "$BACKUP_DIR" -name "clozehive_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
echo "🧹 Cleaned up backups older than $RETENTION_DAYS days"
