#!/usr/bin/env bash
set -euo pipefail

INTERVAL_MINUTES="5"
CRON_EXPR="*/5 * * * *"

usage() {
  cat <<'USAGE'
Usage: bash scripts/install_agent_timer.sh [--interval-minutes <n>] [--cron "<cron-expression>"]

Installs the substrate agent-cycle systemd user timer (fires every 5 minutes
by default; agent-cycle evaluates which agents are actually due internally).

Examples:
  bash scripts/install_agent_timer.sh
  bash scripts/install_agent_timer.sh --interval-minutes 10
  bash scripts/install_agent_timer.sh --cron "*/10 * * * *"
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
    --cron)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --cron" >&2
        exit 2
      fi
      CRON_EXPR="$2"
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
UV_BIN="$(command -v uv || echo /home/ahron/.local/bin/uv)"
SERVICE_NAME="substrate-agent-timer"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
TIMER_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"

mkdir -p "$SYSTEMD_USER_DIR"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Substrate agent cycle (research, dev, update, moderation agents)
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${ROOT_DIR}
ExecStart=${UV_BIN} run python ${ROOT_DIR}/scripts/substrate_cli.py agent-cycle
Environment=SUBSTRATE_ROOT=${ROOT_DIR}
TimeoutStartSec=45min

[Install]
WantedBy=default.target
EOF

cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Run substrate agent cycle every ${INTERVAL_MINUTES} minute(s)

[Timer]
OnCalendar=*:0/${INTERVAL_MINUTES}
Persistent=true
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

echo "Wrote:"
echo "- $SERVICE_FILE"
echo "- $TIMER_FILE"

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  set +e
  daemon_output="$(systemctl --user daemon-reload 2>&1)"
  daemon_code="$?"
  enable_output="$(systemctl --user enable --now "${SERVICE_NAME}.timer" 2>&1)"
  enable_code="$?"
  set -e

  if [[ "$daemon_code" -eq 0 && "$enable_code" -eq 0 ]]; then
    echo
    echo "Enabled ${SERVICE_NAME}.timer"
    systemctl --user list-timers --all "${SERVICE_NAME}.timer" --no-pager
    echo
    echo "Logs: journalctl --user -u ${SERVICE_NAME} -f"
    echo "Rollback: systemctl --user stop ${SERVICE_NAME}.timer"
    exit 0
  fi

  echo
  echo "systemd --user was detected, but timer activation failed."
  if [[ -n "$daemon_output" ]]; then
    echo "$daemon_output"
  fi
  if [[ -n "$enable_output" ]]; then
    echo "$enable_output"
  fi
fi

echo
echo "Using cron fallback:"
echo "${CRON_EXPR} cd \"${ROOT_DIR}\" && ${UV_BIN} run python scripts/substrate_cli.py agent-cycle >> memory/task-runs/agent-cycle-cron.log 2>&1"
