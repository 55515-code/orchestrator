#!/usr/bin/env bash
set -euo pipefail

ON_CALENDAR="*-*-* 09:00:00"
CRON_EXPR="0 9 * * *"

usage() {
  cat <<'USAGE'
Usage: bash scripts/install_developer_polish_timer.sh [--on-calendar "<systemd-calendar>"] [--cron "<cron-expression>"]

Examples:
  bash scripts/install_developer_polish_timer.sh
  bash scripts/install_developer_polish_timer.sh --on-calendar "*-*-* 13:00:00"
  bash scripts/install_developer_polish_timer.sh --cron "30 18 * * 1-5"
USAGE
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --on-calendar)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --on-calendar" >&2
        exit 2
      fi
      ON_CALENDAR="$2"
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
SERVICE_NAME="substrate-developer-polish"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
TIMER_FILE="${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"

mkdir -p "$SYSTEMD_USER_DIR"

cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Substrate developer polish task
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT_DIR
ExecStart=/usr/bin/env bash $ROOT_DIR/scripts/developer_polish.sh

[Install]
WantedBy=default.target
EOF

cat >"$TIMER_FILE" <<EOF
[Unit]
Description=Run substrate developer polish task on a recurring schedule

[Timer]
OnCalendar=$ON_CALENDAR
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
echo "${CRON_EXPR} cd \"$ROOT_DIR\" && /usr/bin/env bash scripts/developer_polish.sh >> memory/task-runs/developer-polish-cron.log 2>&1"
