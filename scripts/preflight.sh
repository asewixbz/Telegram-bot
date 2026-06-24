#!/usr/bin/env bash
set -euo pipefail

missing=()

if [[ -z "${BOT_TOKEN:-}" ]]; then
  missing+=("BOT_TOKEN")
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Missing required environment variables: ${missing[*]}" >&2
  exit 1
fi

mkdir -p "${DB_DIR:-./data}" "${BACKUP_DIR:-./backups}"

echo "Preflight OK"
if [[ -z "${MANAGER_CHAT_ID:-}" ]]; then
  echo "Warning: MANAGER_CHAT_ID is not set; manager notifications will be disabled." >&2
fi
if [[ -z "${ADMIN_IDS:-}" ]]; then
  echo "Warning: ADMIN_IDS is not set; admin commands will be available to all users." >&2
fi
