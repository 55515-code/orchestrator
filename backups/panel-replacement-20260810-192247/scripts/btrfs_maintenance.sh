#!/usr/bin/env bash
# Btrfs maintenance for the Local Agent Substrate.
#
# Subcommands:
#   status     - JSON report of filesystem + recommendation state (read-only).
#   defrag     - Compress + defrag CoW-enabled trees (read-mostly; safe).
#   dedup      - Offline dedup via duperemove on dedup candidates (I/O heavy).
#   snapshot   - Create a read-only snapshot of the workspace subvolume (--apply).
#
# Safety rules:
#   * Everything except `status` defaults to dry-run; requires --apply.
#   * Never targets state/ or memory/ (CoW-disabled volatile trees).
#   * Never runs dedup against active SQLite databases.
#   * Exits 0 on dry-run regardless of plan outcome.

set -uo pipefail

WORKSPACE="${WORKSPACE:-$HOME/codespace}"
COMMAND="${1:-status}"
APPLY=0
if [ "${2:-}" = "--apply" ]; then
  APPLY=1
fi

FS_TYPE=$(stat -f -c %T "${WORKSPACE}" 2>/dev/null || echo unknown)

if [ "${FS_TYPE}" != "btrfs" ]; then
  echo "{\"error\": \"workspace not on Btrfs\", \"workspace\": \"${WORKSPACE}\", \"fstype\": \"${FS_TYPE}\"}"
  exit 1
fi

case "${COMMAND}" in
  status)
    uv run python scripts/substrate_cli.py storage-status
    ;;
  defrag)
    TARGETS=("${WORKSPACE}/artifacts" "${WORKSPACE}/resources" "${WORKSPACE}/docs")
    if [ "${APPLY}" -eq 0 ]; then
      echo "--- dry-run: would defrag+compress (zstd:1) ---"
      for T in "${TARGETS[@]}"; do
        [ -d "${T}" ] && echo "  btrfs filesystem defrag -r -c zstd:1 ${T}"
      done
      echo "Re-run with --apply to execute."
      exit 0
    fi
    for T in "${TARGETS[@]}"; do
      if [ -d "${T}" ]; then
        echo "→ defrag ${T}"
        btrfs filesystem defrag -r -c zstd:1 "${T}" || echo "  ⚠️  defrag failed for ${T}"
      fi
    done
    echo "defrag complete."
    ;;
  dedup)
    if ! command -v duperemove >/dev/null 2>&1; then
      echo "{\"error\": \"duperemove not installed\"}"
      exit 1
    fi
    HASHFILE="${WORKSPACE}/state/btrfs-dedup-hashes.db"
    TARGET="${WORKSPACE}/artifacts"
    [ -d "${TARGET}" ] || { echo "{\"error\": \"${TARGET} missing\"}"; exit 1; }
    if [ "${APPLY}" -eq 0 ]; then
      echo "--- dry-run: would run ---"
      echo "  duperemove -r -h -d -B --hashfile=${HASHFILE} ${TARGET}"
      echo "Re-run with --apply to execute (schedule during low I/O windows)."
      exit 0
    fi
    echo "→ duperemove ${TARGET} (this can take a long time)"
    duperemove -r -h -d -B "--hashfile=${HASHFILE}" "${TARGET}"
    ;;
  snapshot)
    SNAP_ROOT="${SNAPSHOT_ROOT:-${WORKSPACE}/.snapshots}"
    LABEL=$(date -u +%Y%m%dT%H%M%SZ)
    if [ "${APPLY}" -eq 0 ]; then
      echo "--- dry-run: would create ---"
      echo "  btrfs subvolume snapshot -r ${WORKSPACE} ${SNAP_ROOT}/workspace-${LABEL}"
      echo "Re-run with --apply to execute."
      exit 0
    fi
    mkdir -p "${SNAP_ROOT}"
    btrfs subvolume snapshot -r "${WORKSPACE}" "${SNAP_ROOT}/workspace-${LABEL}"
    echo "✅ snapshot: ${SNAP_ROOT}/workspace-${LABEL}"
    # Rotation: keep newest N (default 7), delete older read-only snapshots.
    KEEP="${KEEP_SNAPSHOTS:-7}"
    COUNT=$(ls -1d "${SNAP_ROOT}"/workspace-* 2>/dev/null | wc -l)
    if [ "${COUNT}" -gt "${KEEP}" ]; then
      for OLD in $(ls -1d "${SNAP_ROOT}"/workspace-* 2>/dev/null | head -n $((COUNT - KEEP))); do
        echo "→ rotate ${OLD}"
        btrfs subvolume delete "${OLD}"
      done
    fi
    ;;
  *)
    echo "usage: $0 {status|defrag|dedup|snapshot} [--apply]" >&2
    exit 1
    ;;
esac
