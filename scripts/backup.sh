#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Clozehive PostgreSQL backup script
# Usage: ./scripts/backup.sh
# Creates timestamped .sql.gz dumps in ./backups/ for both DB domains.
# -----------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
PRIMARY_DB_CONTAINER="${PRIMARY_DB_CONTAINER:-clozehive-postgres-1}"
CLOSET_DB_CONTAINER="${CLOSET_DB_CONTAINER:-clozehive-postgres-closet-1}"
PRIMARY_DB_NAME="${POSTGRES_DB:-clozehive}"
CLOSET_DB_NAME="${CLOSET_POSTGRES_DB:-clozehive_closet}"
DB_USER="${POSTGRES_USER:-clozehive}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
BACKUP_CLOSET_DB="${BACKUP_CLOSET_DB:-true}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

backup_one() {
  local container="$1"
  local db_name="$2"
  local prefix="$3"
  local backup_file="$BACKUP_DIR/${prefix}_${TIMESTAMP}.sql.gz"

  echo "[backup] Dumping ${db_name} from ${container} -> ${backup_file}"
  docker exec "$container" pg_dump -U "$DB_USER" "$db_name" | gzip > "$backup_file"

  if [[ ! -s "$backup_file" ]]; then
    echo "[backup] ERROR: Backup file missing or empty: ${backup_file}"
    exit 1
  fi

  local backup_size
  backup_size="$(du -sh "$backup_file" | cut -f1)"
  echo "[backup] Complete: ${backup_file} (${backup_size})"

  if command -v aws >/dev/null 2>&1 && [[ -n "${S3_BACKUP_BUCKET:-}" ]]; then
    aws s3 cp "$backup_file" "s3://${S3_BACKUP_BUCKET}/backups/"
    echo "[backup] Uploaded: s3://${S3_BACKUP_BUCKET}/backups/"
  fi
}

backup_one "$PRIMARY_DB_CONTAINER" "$PRIMARY_DB_NAME" "clozehive_primary"

if [[ "$BACKUP_CLOSET_DB" == "true" ]]; then
  backup_one "$CLOSET_DB_CONTAINER" "$CLOSET_DB_NAME" "clozehive_closet"
fi

find "$BACKUP_DIR" -name "clozehive_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
echo "[backup] Removed backups older than ${RETENTION_DAYS} days"
