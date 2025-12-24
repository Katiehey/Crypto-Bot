#!/bin/bash
set -e

BACKUP_DIR="backups"
LOG_FILE="logs/recovery.log"

# If no argument given, pick the latest backup
if [ -z "$1" ]; then
  LATEST_BACKUP=$(ls -t ${BACKUP_DIR}/bot_backup_*.tar.gz 2>/dev/null | head -n 1)
  if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup files found in ${BACKUP_DIR}/"
    exit 1
  fi
  BACKUP_FILE="$LATEST_BACKUP"
else
  BACKUP_FILE="$1"
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "❌ Error: Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "🗂 Restoring from backup: $BACKUP_FILE"

# Extract into project root
tar -xzf "$BACKUP_FILE" -C .

# Log the restore event
echo "$(date '+%Y-%m-%d %H:%M:%S') Restored from $BACKUP_FILE" >> "$LOG_FILE"

echo "✅ Restore complete. Restart container to apply restored state/config."
 