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
SUBSTRATE_ROOT="${SUBSTRATE_ROOT:-$HOME/codespace}"
CAPSULE_BACKUP_DIR="${CAPSULE_BACKUP_DIR:-$SUBSTRATE_ROOT/artifacts/capsule/backups}"
DB_SNAPSHOT_DIR="${DB_SNAPSHOT_DIR:-$SUBSTRATE_ROOT/artifacts/db-snapshots}"
EXCLUDE_FILE="${EXCLUDE_FILE:-$SUBSTRATE_ROOT/scripts/backup-excludes.txt}"

export RESTIC_REPOSITORY="$RESTIC_REPO"
export RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE"
export TMPDIR="$RESTIC_TMP"

if [ "${1:-}" = "--restore-list" ]; then
  restic snapshots 2>&1 | tail -15
  exit 0
fi

mkdir -p "$(dirname "$RESTIC_PASSWORD_FILE")" "$(dirname "$LOG")" "$RESTIC_TMP" "$CAPSULE_BACKUP_DIR"

# --- Mutual exclusion ------------------------------------------------------
# This job is currently double-scheduled (systemd restic-backup.timer AND the
# OpenClaw cron entry "Restic Backup"), so two invocations can start seconds
# apart and race on the same restic repository. Re-exec under flock so the
# second one exits immediately and cleanly rather than fighting for repo locks.
# See known_issues.duplicate_scheduling in system_registry.yaml.
LOCK_FILE="${BACKUP_LOCK_FILE:-$HOME/.cache/restic/backup.lock}"
if [ -z "${BACKUP_LOCK_HELD:-}" ] && command -v flock >/dev/null 2>&1; then
  mkdir -p "$(dirname "$LOCK_FILE")"
  # Re-run self as a CHILD of flock (not exec) so the exit code can be
  # inspected: flock returns 75 when the lock is already held.
  BACKUP_LOCK_HELD=1 flock --nonblock --conflict-exit-code 75 "$LOCK_FILE" "$0" "$@"
  rc=$?
  if [ "$rc" -eq 75 ]; then
    echo "[$(date -u +%FT%TZ)] another backup already running; this run exits cleanly (double-scheduled)" >> "$LOG"
    exit 0
  fi
  exit "$rc"
fi

if [ "${1:-}" = "--init" ]; then
  restic init 2>&1 | tail -4
  exit $?
fi
if [ "${1:-}" = "--dry-run" ]; then
  printf '%s\n' \
    "OpenClaw: verified native backup -> $CAPSULE_BACKUP_DIR" \
    "Restic repository: $RESTIC_REPO" \
    "Exclude file: $EXCLUDE_FILE $([ -f "$EXCLUDE_FILE" ] && echo '(present)' || echo '(MISSING)')" \
    "DB snapshots: $DB_SNAPSHOT_DIR" \
    "Mode: dry-run (no backup or prune executed)"
  exit 0
fi

# Critical, small, portable set — NOT the whole home (avoid OS images/binaries).
#
# Scope rationale (see docs/generated/backup-recovery.md):
#  - Host dotfiles + systemd units: needed to rebuild the service topology.
#  - Substrate code (substrate/, scripts/) and declarative config (*.yaml,
#    pyproject.toml, uv.lock): needed to rebuild the substrate itself.
#  - state/, memory/, .research/: accumulated state that is gitignored and
#    therefore has NO other copy. Bulk subtrees are pruned via EXCLUDE_FILE.
RAW_PATHS=( \
  "$HOME/.bashrc" "$HOME/.gitconfig" "$HOME/.npmrc" \
  "$HOME/.config/kilo" "$HOME/.config/chezmoi" "$HOME/.config/rclone" "$HOME/.config/systemd/user" \
  "$HOME/.local/share/chezmoi" \
  "$SUBSTRATE_ROOT/artifacts" "$SUBSTRATE_ROOT/scripts" "$SUBSTRATE_ROOT/substrate" \
  "$SUBSTRATE_ROOT/state" "$SUBSTRATE_ROOT/memory" "$SUBSTRATE_ROOT/.research" \
  "$SUBSTRATE_ROOT/docs" "$SUBSTRATE_ROOT/tests" "$SUBSTRATE_ROOT/chains" "$SUBSTRATE_ROOT/.kilo" \
  "$SUBSTRATE_ROOT/pyproject.toml" "$SUBSTRATE_ROOT/uv.lock" "$SUBSTRATE_ROOT/justfile" \
  "$SUBSTRATE_ROOT/mkdocs.yml" "$SUBSTRATE_ROOT/mise.toml" "$SUBSTRATE_ROOT/policy.jsonc" \
  "$SUBSTRATE_ROOT/workspace.yaml" "$SUBSTRATE_ROOT/agents.yaml" "$SUBSTRATE_ROOT/standards.yaml" \
  "$SUBSTRATE_ROOT/tool_profiles.yaml" "$SUBSTRATE_ROOT/integrations.yaml" \
  "$SUBSTRATE_ROOT/upstreams.yaml" "$SUBSTRATE_ROOT/config_sync_profiles.yaml" \
  "$SUBSTRATE_ROOT/crypto-rules.yaml" "$SUBSTRATE_ROOT/render_profiles.yaml" \
  "$SUBSTRATE_ROOT/research-targets.yaml" "$SUBSTRATE_ROOT/business-research-sources.yaml" \
  "$SUBSTRATE_ROOT/system_registry.yaml" \
)

# SQLite databases run in WAL mode and are written by live agents, so a raw
# file copy can capture a torn transaction. `VACUUM INTO` produces an
# internally consistent snapshot; those land under artifacts/, which is already
# in RAW_PATHS. The live .db files are still captured for redundancy, but the
# snapshots are the authoritative restore source.
if command -v sqlite3 >/dev/null 2>&1; then
  mkdir -p "$DB_SNAPSHOT_DIR"
  for db in "$SUBSTRATE_ROOT"/state/*.db; do
    [ -e "$db" ] || continue
    snap="$DB_SNAPSHOT_DIR/$(basename "$db")"
    rm -f "$snap"
    if sqlite3 "$db" "VACUUM INTO '$snap'" >>"$LOG" 2>&1; then
      echo "[$(date -u +%FT%TZ)] sqlite snapshot ok: $(basename "$db")" >> "$LOG"
    else
      echo "[$(date -u +%FT%TZ)] sqlite snapshot FAILED: $(basename "$db")" >> "$LOG"
    fi
  done
else
  echo "[$(date -u +%FT%TZ)] sqlite3 absent; databases captured as raw files only" >> "$LOG"
fi

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
# Remove only locks left behind by dead processes. The previous implementation
# used `restic unlock --remove-all`, which also strips locks held by a LIVE
# sibling backup — and this job is currently double-scheduled (systemd timer +
# OpenClaw cron), so a live sibling is a real scenario. See
# known_issues.duplicate_scheduling in system_registry.yaml.
restic unlock 2>/dev/null || true
EXCLUDE_ARGS=()
if [ -f "$EXCLUDE_FILE" ]; then
  EXCLUDE_ARGS+=(--exclude-file "$EXCLUDE_FILE")
else
  echo "[$(date -u +%FT%TZ)] WARNING: exclude file missing ($EXCLUDE_FILE); using inline fallback" >> "$LOG"
  EXCLUDE_ARGS+=(--exclude '**/.git/**' --exclude '**/node_modules/**'
                 --exclude '**/__pycache__/**' --exclude '**/.venv/**' --exclude '**/dist/**')
fi

restic backup "${PATHS[@]}" \
  "${EXCLUDE_ARGS[@]}" \
  --exclude-caches \
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
