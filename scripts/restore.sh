#!/bin/bash
set -euo pipefail

BACKUP_FILE="${1:-}"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: ./scripts/restore.sh path/to/backup.sql.gz"
  echo ""
  echo "Available backups:"
  ls -lht ./backups/*.sql.gz 2>/dev/null || echo "No backups found"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "WARNING: This will overwrite the current database."
echo "Backup to restore: $BACKUP_FILE"
read -p "Type 'yes' to confirm: " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo "Restore cancelled"
  exit 0
fi

DB_CONTAINER="${DB_CONTAINER:-closetiq-db-1}"
DB_NAME="${POSTGRES_DB:-closetiq}"
DB_USER="${POSTGRES_USER:-postgres}"

echo "Restoring database..."
gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" "$DB_NAME"
echo "Restore complete"
