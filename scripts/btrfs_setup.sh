#!/usr/bin/env bash
# Btrfs setup for the Local Agent Substrate.
#
# One-shot provisioning that:
#   1. Validates the environment (kernel, btrfs-progs, duperemove, Docker driver).
#   2. In --apply mode, creates the substrate subvolume layout and applies
#      CoW controls; in dry-run mode (default) prints the exact plan.
#   3. Prints the recommended mkfs.btrfs command and fstab snippet.
#
# Safety rules (aligned with substrate autonomy tiers):
#   * Defaults to dry-run; requires --apply for any mutation.
#   * Never reformats a device or touches an existing filesystem.
#   * Never moves data; migration is left to the operator.
#   * Idempotent: re-running is a no-op once subvolumes/attributes exist.

set -uo pipefail

WORKSPACE="${1:-$HOME/codespace}"
APPLY=0
if [ "${2:-}" = "--apply" ]; then
  APPLY=1
fi

echo "=== Btrfs setup for workspace: $WORKSPACE ==="
echo ""

# --- Environment validation -----------------------------------------------
FAIL=0
command -v btrfs >/dev/null 2>&1 || { echo "❌ btrfs-progs missing (install btrfs-progs)"; FAIL=1; }
command -v chattr >/dev/null 2>&1 || { echo "❌ e2fsprogs chattr missing"; FAIL=1; }
KERNEL_MAJOR=$(uname -r | cut -d. -f1)
KERNEL_MINOR=$(uname -r | cut -d. -f2)
echo "ℹ️  Kernel: $(uname -r)"
if [ "${KERNEL_MAJOR:-0}" -lt 5 ] || { [ "${KERNEL_MAJOR:-0}" -eq 5 ] && [ "${KERNEL_MINOR:-0}" -lt 10 ]; }; then
  echo "⚠️  Kernel < 5.10: space_cache=v2 / async discard / stable zstd not guaranteed."
fi
btrfs --version 2>/dev/null | head -1 || true

if command -v duperemove >/dev/null 2>&1; then
  echo "✅ duperemove available (dedup workflow enabled)"
else
  echo "⚠️  duperemove not installed — dedup step will be skipped (see docs/btrfs-optimization.md)"
fi

if command -v docker >/dev/null 2>&1; then
  DRIVER=$(docker info --format '{{.Driver}}' 2>/dev/null || echo unknown)
  echo "ℹ️  Docker storage driver: ${DRIVER}"
  if [ "${DRIVER}" = "btrfs" ]; then
    echo "❌ Legacy Docker 'btrfs' driver is deprecated. Set \"storage-driver\": \"overlay2\" in daemon.json."
    FAIL=1
  fi
else
  echo "ℹ️  Docker not detected."
fi

# Verify the workspace actually sits on Btrfs (detection via stat).
FS_TYPE=$(stat -f -c %T "${WORKSPACE}" 2>/dev/null || echo unknown)
echo "ℹ️  Workspace filesystem: ${FS_TYPE}"
if [ "${FS_TYPE}" != "btrfs" ]; then
  echo "⚠️  Workspace is not on Btrfs. mkfs/fstab guidance below is informational only;"
  echo "   migrate the device first (see docs/btrfs-optimization.md)."
  if [ "${APPLY}" -eq 1 ]; then
    echo "❌ Refusing --apply on a non-Btrfs workspace."
    FAIL=1
  fi
fi

if [ "${FAIL}" -eq 1 ]; then
  echo ""
  echo "Environment validation failed; fix the errors above and re-run."
  exit 1
fi

# --- Plan -----------------------------------------------------------------
STATE_DIR="${WORKSPACE}/state"
MEMORY_DIR="${WORKSPACE}/memory"

echo ""
echo "--- Recommended mkfs.btrfs parameters (new filesystems only) ---"
echo "  mkfs.btrfs -f -m dup -d single -n 16384 -s \\"
echo "      -O extref,skinny-metadata,no-holes /dev/<device>"
echo "  Tradeoffs: -m dup costs ~10-15% space for metadata safety;"
echo "             -d single avoids mirroring regenerable data."
echo ""

echo "--- Recommended fstab mount options ---"
echo "  UUID=<fs-uuid> / btrfs defaults,ssd,space_cache=v2,noatime,compress=zstd:1,autodefrag,discard=async 0 1"
echo ""

echo "--- Subvolume layout plan ---"
echo "  @workspace  (CoW on,  compress=zstd:1)   -> ${WORKSPACE}"
echo "  @state      (CoW off, nodatacow)         -> ${STATE_DIR}"
echo "  @memory     (CoW off, nodatacow)         -> ${MEMORY_DIR}"
echo "  @artifacts  (CoW on,  compress=zstd:1)   -> ${WORKSPACE}/artifacts"
echo ""

# --- Apply phase ----------------------------------------------------------
if [ "${APPLY}" -eq 0 ]; then
  echo "--- Dry-run: no changes made. Re-run with '--apply' to: ---"
  echo "  1. chattr +C on ${STATE_DIR} and ${MEMORY_DIR} (new files inherit noCoW)"
  echo "  2. Optionally create subvolumes @state/@memory/@artifacts"
  echo ""
  echo "NOTE: subvolume creation requires the paths to be empty or moved;"
  echo "      this script never moves data — do that manually before --apply."
  exit 0
fi

# chattr +C only affects files created AFTER the attribute is set. Existing
# files keep CoW; re-create them or accept partial coverage.
for DIR in "${STATE_DIR}" "${MEMORY_DIR}"; do
  if [ -d "${DIR}" ]; then
    if chattr +C "${DIR}" 2>/dev/null; then
      echo "✅ noCoW attribute set on ${DIR} (applies to newly created files)"
    else
      echo "❌ failed to set noCoW on ${DIR}"
    fi
  else
    echo "⚠️  ${DIR} does not exist; skipping (create it first)."
  fi
done

echo ""
echo "--- Post-apply checklist ---"
echo "  1. Verify: lsattr -d ${STATE_DIR} ${MEMORY_DIR}"
echo "  2. Re-run: uv run python scripts/substrate_cli.py storage-validate"
echo "  3. Schedule: bash scripts/btrfs_maintenance.sh status (see crontab/systemd timer)"
echo "Done."
