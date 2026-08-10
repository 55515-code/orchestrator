#!/usr/bin/env bash
# install_change_snapshot_timer.sh — install the automated change-snapshot timer.
#
# Installs a systemd user timer that runs the non-blocking change-snapshot
# cycle (see docs/change-snapshots.md) every INTERVAL_MINUTES minutes and
# after boot, then enables and starts it.

set -euo pipefail

INTERVAL_MINUTES="10"
ONBOOT_MINUTES="5"

usage() {
  cat <<'USAGE'
Usage: bash scripts/install_change_snapshot_timer.sh [--interval-minutes <n>]

Installs the substrate change-snapshot systemd user timer. Snapshots are
captured locally onto an `autosnap` branch per repository, non-blocking and
without diff output.

Examples:
  bash scripts/install_change_snapshot_timer.sh
  bash scripts/install_change_snapshot_timer.sh --interval-minutes 5
USAGE
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --interval-minutes)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --interval-minutes" >&2
        exit 2
      fi
      INTERVAL_MINUTES="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="change-snapshot"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
TIMER_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"

mkdir -p "$SYSTEMD_USER_DIR"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Capture non-blocking working-tree change snapshots
After=local-fs.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT_DIR
ExecStart=$ROOT_DIR/scripts/change_snapshot.sh
TimeoutStartSec=300

[Install]
WantedBy=default.target
EOF

cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Run change snapshots every ${INTERVAL_MINUTES} minute(s)

[Timer]
OnBootSec=${ONBOOT_MINUTES}min
OnUnitActiveSec=${INTERVAL_MINUTES}min
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME.timer"

echo "Installed and started: $SERVICE_NAME.timer"
echo "  service: $SERVICE_FILE"
echo "  timer:   $TIMER_FILE"
echo "  interval: every ${INTERVAL_MINUTES} minute(s), first run ${ONBOOT_MINUTES}min after boot"
echo
systemctl --user list-timers "$SERVICE_NAME.timer" --no-pager
