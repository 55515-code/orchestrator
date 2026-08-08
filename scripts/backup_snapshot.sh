#!/usr/bin/env bash
# restic snapshot backup of home, encrypted, to a configurable target.
#
# Target is set via RESTIC_REPO env (default: Cloudflare R2 via S3 backend).
# R2 is the recommended decentralized target (free tier, no egress fees).
#
# Usage:
#   RESTIC_REPO=s3:https://<accountid>.r2.cloudflarestorage.com/substrate-backups \
#     scripts/backup_snapshot.sh                 # run backup
#   scripts/backup_snapshot.sh --restore-list    # list snapshots
#   scripts/backup_snapshot.sh --init            # init repo (first time)
set -uo pipefail

# --- Configuration (override via env) ---
RESTIC_REPO="${RESTIC_REPO:-s3:https://${CF_R2_ACCOUNT_ID}.r2.cloudflarestorage.com/substrate-backups}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.config/restic/password}"
IGNORE_FILE="${IGNORE_FILE:-$HOME/.config/restic/ignore}"
LOG="$HOME/.config/restic/backup.log"

mkdir -p "$(dirname "$IGNORE_FILE")" "$(dirname "$RESTIC_PASSWORD_FILE")" "$(dirname "$LOG")"

# --- R2 credentials (from env, never hardcoded) ---
export RCLONE_S3_ACCESS_KEY_ID="${CF_R2_ACCESS_KEY_ID:-}"
export RCLONE_S3_SECRET_ACCESS_KEY="${CF_R2_SECRET_ACCESS_KEY:-}"

# --- Default ignore list (large binaries, caches, build outputs, secrets) ---
cat > "$IGNORE_FILE" <<'IGN'
node_modules/
.venv/
.direnv/
dist/
.astro/
work/
aosp-eos-asteroids/
eos-asteroids/
state/
memory/
.git/
.kilo/node_modules/
.cache/
Downloads/
.local/share/Trash/
.config/restic/
.config/rclone/
.config/age/
.ssh/
IGN

restic_env() {
  export RESTIC_REPOSITORY="$RESTIC_REPO"
  export RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE"
  export AWS_ACCESS_KEY_ID="$RCLONE_S3_ACCESS_KEY_ID"
  export AWS_SECRET_ACCESS_KEY="$RCLONE_S3_SECRET_ACCESS_KEY"
}

if [ "${1:-}" = "--restore-list" ]; then
  restic_env
  restic snapshots 2>&1 | tail -20
  exit 0
fi

if [ "${1:-}" = "--init" ]; then
  restic_env
  if [ ! -f "$RESTIC_PASSWORD_FILE" ] || [ ! -s "$RESTIC_PASSWORD_FILE" ]; then
    echo "Restic password file is empty/missing: $RESTIC_PASSWORD_FILE" >&2
    echo "Generate it with:  head -c 32 /dev/urandom | base64 > $RESTIC_PASSWORD_FILE && chmod 600 $RESTIC_PASSWORD_FILE" >&2
    echo "Then run:  RESTIC_REPO=... scripts/backup_snapshot.sh --init" >&2
    exit 1
  fi
  restic init 2>&1 | tail -5
  exit $?
fi

# --- Backup ---
restic_env
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] && [[ "$RESTIC_REPO" != file:* ]]; then
  echo "WARNING: R2 credentials not set (CF_R2_ACCESS_KEY_ID / CF_R2_SECRET_ACCESS_KEY)." >&2
  echo "Backup will fail unless you export them or use a file: repo." >&2
fi

echo "[$(date -u +%FT%TZ)] restic backup start ($RESTIC_REPO)" >> "$LOG"
restic backup "$HOME" \
  --exclude-file="$IGNORE_FILE" \
  --exclude-caches \
  --verbose=1 2>&1 | tail -8 >> "$LOG"

echo "[$(date -u +%FT%TZ)] prune old snapshots" >> "$LOG"
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 3 --prune 2>&1 | tail -4 >> "$LOG"
echo "[$(date -u +%FT%TZ)] backup complete" >> "$LOG"
tail -12 "$LOG"
