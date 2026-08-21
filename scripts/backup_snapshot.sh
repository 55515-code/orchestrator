#!/usr/bin/env bash
# restic snapshot backup of critical config + code, encrypted, to configurable target.
# Target via RESTIC_REPO env (default local:/home/ahron/.backups/restic).
# For a distributed/offsite target, use Cloudflare R2 (S3 backend):
#   RESTIC_REPO=s3:https://<accountid>.r2.cloudflarestorage.com/substrate-backups
set -uo pipefail

RESTIC_REPO="${RESTIC_REPO:-local:/home/ahron/.backups/restic}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.config/restic/password}"
LOG="$HOME/.config/restic/backup.log"
# Use a disk-backed scratch dir: /tmp is a small tmpfs that can fill up
# (e.g. desktop memfd pressure), which previously failed ENOSPC mid-snapshot.
RESTIC_TMP="${RESTIC_TMP:-$HOME/.cache/restic/tmp}"
CAPSULE_BACKUP_DIR="${CAPSULE_BACKUP_DIR:-$HOME/codespace/artifacts/capsule/backups}"

export RESTIC_REPOSITORY="$RESTIC_REPO"
export RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE"
export TMPDIR="$RESTIC_TMP"

if [ "${1:-}" = "--restore-list" ]; then
  restic snapshots 2>&1 | tail -15
  exit 0
fi

mkdir -p "$(dirname "$RESTIC_PASSWORD_FILE")" "$(dirname "$LOG")" "$RESTIC_TMP" "$CAPSULE_BACKUP_DIR"
if [ "${1:-}" = "--init" ]; then
  restic init 2>&1 | tail -4
  exit $?
fi
if [ "${1:-}" = "--dry-run" ]; then
  printf '%s\n' \
    "OpenClaw: verified native backup -> $CAPSULE_BACKUP_DIR" \
    "Restic repository: $RESTIC_REPO" \
    "Mode: dry-run (no backup or prune executed)"
  exit 0
fi

# Critical, small, portable set — NOT the whole home (avoid OS images/binaries).
RAW_PATHS=( \
  "$HOME/.bashrc" "$HOME/.gitconfig" "$HOME/.npmrc" \
  "$HOME/.config/kilo" "$HOME/.config/chezmoi" "$HOME/.config/rclone" "$HOME/.config/systemd/user" \
  "$HOME/.local/share/chezmoi" \
  "$HOME/codespace/automation" "$HOME/codespace/artifacts" "$HOME/codespace/scripts" "$HOME/codespace/substrate" \
)

# OpenClaw's native backup safely captures its SQLite databases and emits a
# manifest-bearing archive. Back up that verified archive with restic instead
# of copying live database files directly.
if command -v openclaw >/dev/null 2>&1 && [ -d "$HOME/.openclaw" ]; then
  if ! openclaw backup create --verify --no-include-workspace \
    --output "$CAPSULE_BACKUP_DIR" >> "$LOG" 2>&1; then
    echo "[$(date -u +%FT%TZ)] OpenClaw verified backup FAILED" >> "$LOG"
    exit 1
  fi
fi

# Filter out missing paths to avoid restic warnings and failed snapshots.
PATHS=()
for p in "${RAW_PATHS[@]}"; do
  if [ -e "$p" ]; then
    PATHS+=("$p")
  else
    echo "[$(date -u +%FT%TZ)] skip missing path: $p" >> "$LOG"
  fi
done

echo "[$(date -u +%FT%TZ)] restic backup start" >> "$LOG"
# Unlock stale repository locks (exit 3) before backup.
restic unlock --remove-all 2>/dev/null || true
restic backup "${PATHS[@]}" \
  --exclude '**/.git/**' --exclude '**/node_modules/**' --exclude '**/__pycache__/**' \
  --exclude '**/.venv/**' --exclude '**/dist/**' \
  --verbose=0 2>&1 | tail -6 >> "$LOG"
BACKUP_STATUS=${PIPESTATUS[0]}

if [ "$BACKUP_STATUS" -ne 0 ] && [ "$BACKUP_STATUS" -ne 3 ]; then
  echo "[$(date -u +%FT%TZ)] backup FAILED (exit $BACKUP_STATUS); skipping prune" >> "$LOG"
  tail -10 "$LOG"
  exit 1
fi

echo "[$(date -u +%FT%TZ)] prune" >> "$LOG"
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 3 --prune 2>&1 | tail -3 >> "$LOG"
echo "[$(date -u +%FT%TZ)] complete" >> "$LOG"
tail -10 "$LOG"
