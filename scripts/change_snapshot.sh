#!/usr/bin/env bash
# change_snapshot.sh — quiet wrapper for the automated change-snapshot cycle.
#
# Runs the substrate snapshot CLI against every configured repository and
# appends a compact log line per cycle. Emits nothing to the console: all
# output goes to state/change-snapshots/change-snapshots.log so the cycle
# never clutters the journal or a terminal.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/state/change-snapshots"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/change-snapshots.log"

{
  echo "[$(date -u +%FT%TZ)] change-snapshot cycle start"
  cd "$ROOT" && uv run --quiet python -m substrate.cli snapshot
  rc=$?
  echo "[$(date -u +%FT%TZ)] change-snapshot cycle end rc=$rc"
} >>"$LOG" 2>&1

exit "$rc"
