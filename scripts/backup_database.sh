#!/usr/bin/env bash
# ==============================================================================
# Database backup script using pg_dump
# ==============================================================================

set -euo pipefail

BACKUP_DIR="/var/backups/medicine-safety"
DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/medicine_safety_$DATE.sql.gz"
DB_NAME="medicine_safety"
DB_USER="medicine_user"

mkdir -p "$BACKUP_DIR"

echo "Creating database backup of $DB_NAME..."
pg_dump -U "$DB_USER" -h localhost "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "✓ Backup created at $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Keep last 14 days of backups
echo "Cleaning up backups older than 14 days..."
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +14 -delete

echo "Backup process finished."
