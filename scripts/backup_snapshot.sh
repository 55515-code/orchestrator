#!/usr/bin/env bash
# restic snapshot backup of home -> Proton Drive (via rclone), encrypted.
# Usage: scripts/backup_snapshot.sh [--restore-list]
set -uo pipefail

REPO="rclone:proton:restic"
IGNORE="$HOME/.config/restic/ignore"
LOG="$HOME/.config/restic/backup.log"
mkdir -p "$(dirname "$IGNORE")" "$(dirname "$LOG")"

cat > "$IGNORE" <<'IGN'
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
IGN

if [ "${1:-}" = "--restore-list" ]; then
  restic -r "$REPO" snapshots 2>&1 | tail -20
  exit 0
fi

echo "[$(date -u +%FT%TZ)] restic backup start" >> "$LOG"
restic -r "$REPO" backup "$HOME" \
  --exclude-file="$IGNORE" \
  --exclude-caches \
  --verbose=1 2>&1 | tail -8 >> "$LOG"

echo "[$(date -u +%FT%TZ)] prune old snapshots" >> "$LOG"
restic -r "$REPO" forget --keep-daily 7 --keep-weekly 4 --keep-monthly 3 --prune 2>&1 | tail -4 >> "$LOG"
echo "[$(date -u +%FT%TZ)] backup complete" >> "$LOG"
tail -12 "$LOG"
