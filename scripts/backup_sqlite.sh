#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${DB_PATH:-./data/leads.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "SQLite database not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/leads-$TIMESTAMP.sqlite3"

cp "$DB_PATH" "$BACKUP_FILE"
echo "Backup created: $BACKUP_FILE"
