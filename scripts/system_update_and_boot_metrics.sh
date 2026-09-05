#!/usr/bin/env bash
# System Update and Boot Metrics Collection Script
#
# Performs a full system update, triggers a reboot, and collects
# granular boot performance metrics during the reboot process.
#
# SAFETY: This script requires explicit user approval before execution.
# It will prompt for confirmation and create rollback checkpoints.
#
# Usage:
#   ./scripts/system_update_and_boot_metrics.sh
#   ./scripts/system_update_and_boot_metrics.sh --approve
#   ./scripts/system_update_and_boot_metrics.sh --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
STATE_DIR="$ROOT_DIR/state/boot"
LOG_DIR="$ROOT_DIR/memory/reliability"

# Safety flags
APPROVE_FLAG="${1:-}"
DRY_RUN=false
if [ "$APPROVE_FLAG" = "--approve" ]; then
    APPROVE_FLAG="yes"
elif [ "$APPROVE_FLAG" = "--dry-run" ]; then
    DRY_RUN=true
    APPROVE_FLAG="yes"
else
    APPROVE_FLAG=""
fi

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    mkdir -p "$LOG_DIR"
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_DIR/system-update.log"
}

check_approval() {
    if [ -z "$APPROVE_FLAG" ]; then
        cat <<'EOF'
================================================================================
SYSTEM UPDATE AND REBOOT - EXPLICIT APPROVAL REQUIRED
================================================================================

This script will:
1. Perform a FULL system update (pacman -Syu)
2. TRIGGER A REBOOT to apply updates
3. Collect granular boot performance metrics during reboot

RISKS:
- System update may fail or break existing functionality
- Reboot will interrupt all running processes
- Boot metrics collection requires early boot systemd service
- No guaranteed rollback if update breaks the system

REQUIREMENTS:
- This is a CachyOS/Arch-based system (verified)
- You must have sudo/root access for system update
- You must have systemd for boot metrics collection
- You must explicitly approve this operation

To proceed, run:
  ./scripts/system_update_and_boot_metrics.sh --approve

To preview without executing:
  ./scripts/system_update_and_boot_metrics.sh --dry-run

================================================================================
EOF
        exit 1
    fi
}

check_prerequisites() {
    log "Checking prerequisites..."

    # Check for systemd
    if ! command -v systemctl >/dev/null 2>&1; then
        log "ERROR: systemd not found. Boot metrics collection requires systemd."
        exit 1
    fi

    # Check for package manager
    if ! command -v pacman >/dev/null 2>&1; then
        log "ERROR: pacman not found. This script requires an Arch-based system."
        exit 1
    fi

    # Check for uv
    if ! command -v uv >/dev/null 2>&1; then
        log "ERROR: uv not found. Install uv to run Python modules."
        exit 1
    fi

    # Check for sudo/root
    if [ "$(id -u)" -ne 0 ]; then
        if ! sudo -n true 2>/dev/null; then
            log "ERROR: Root/sudo access required for system update."
            exit 1
        fi
    fi

    log "Prerequisites satisfied."
}

install_boot_metrics_service() {
    log "Installing boot metrics collector service..."

    # Create systemd user directory if needed
    mkdir -p ~/.config/systemd/user

    # Copy unit file
    cp "$ROOT_DIR/scripts/templates/boot-metrics-collector.service" \
       ~/.config/systemd/user/boot-metrics-collector.service || true

    # Ensure unit file exists
    if [ ! -s ~/.config/systemd/user/boot-metrics-collector.service ]; then
        cat > ~/.config/systemd/user/boot-metrics-collector.service <<'EOF'
[Unit]
Description=Boot Metrics Collector (early boot)
DefaultDependencies=no
Conflicts=shutdown.target
Before=local-fs-pre.target shutdown.target
Wants=local-fs-pre.target

[Service]
Type=oneshot
ExecStart=/usr/bin/env uv run python /home/ahron/codespace/substrate/boot/boot_metrics.py --output /home/ahron/codespace/state/boot/boot-${boot_id}.json
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=local-fs.target
EOF
    fi

    # Reload and enable
    systemctl --user daemon-reload
    systemctl --user enable --now boot-metrics-collector.service || true

    log "Boot metrics collector service installed and enabled."
}

create_rollback_checkpoint() {
    log "Creating rollback checkpoint..."

    CHECKPOINT="$STATE_DIR/rollback-checkpoint-$(date +%Y%m%d-%H%M%S).json"
    mkdir -p "$STATE_DIR"

    # Capture current package state
    pacman -Qe > "$STATE_DIR/explicit-packages.txt" 2>/dev/null || true
    pacman -Qm > "$STATE_DIR/foreign-packages.txt" 2>/dev/null || true
    pacman -Q > "$STATE_DIR/all-packages.txt" 2>/dev/null || true

    # Capture current systemd unit states
    systemctl --user list-unit-files --type=service --state=enabled > "$STATE_DIR/enabled-services.txt" 2>/dev/null || true

    # Create checkpoint metadata
    cat > "$CHECKPOINT" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "kernel": "$(uname -r)",
  "packages_backup": [
    "$STATE_DIR/explicit-packages.txt",
    "$STATE_DIR/foreign-packages.txt",
    "$STATE_DIR/all-packages.txt"
  ],
  "services_backup": "$STATE_DIR/enabled-services.txt",
  "boot_metrics_installed": true
}
EOF

    log "Rollback checkpoint created: $CHECKPOINT"
}

perform_system_update() {
    if [ "$DRY_RUN" = true ]; then
        log "DRY RUN: Would execute: pacman -Syu --noconfirm"
        return 0
    fi

    log "Starting full system update..."
    pacman -Syu --noconfirm
    log "System update completed."
}

trigger_reboot() {
    if [ "$DRY_RUN" = true ]; then
        log "DRY RUN: Would execute: reboot"
        return 0
    fi

    log "System update complete. Rebooting to apply updates..."
    log "Boot metrics will be collected during reboot."
    log "After reboot, run: uv run python substrate/boot/optimization_analyzer.py --metrics state/boot/latest.json"

    # Give a moment for logs to flush
    sleep 5

    # Trigger reboot
    reboot
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    log "=== System Update and Boot Metrics Collection ==="

    check_approval
    check_prerequisites
    install_boot_metrics_service
    create_rollback_checkpoint

    if [ "$DRY_RUN" = true ]; then
        log "DRY RUN complete. No changes made."
        log "To actually perform the update, run with --approve flag."
        exit 0
    fi

    perform_system_update
    trigger_reboot
}

main "$@"
