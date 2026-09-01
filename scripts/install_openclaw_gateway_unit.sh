#!/usr/bin/env bash
# install_openclaw_gateway_unit.sh — install the hardened OpenClaw Gateway
# systemd user unit + deep-health watchdog timer.
#
# Idempotent: safe to re-run. Installs the unit and watchdog into
# ~/.config/systemd/user/, then enables and starts everything.
# Run from /home/ahron/codespace.
#
#   bash scripts/install_openclaw_gateway_unit.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$SYSTEMD_USER_DIR"

# Sanity check: the unit's ExecStart binary must exist before we install it.
if [ ! -x /home/ahron/.npm-global/bin/openclaw ]; then
    echo "WARNING: /home/ahron/.npm-global/bin/openclaw not found." >&2
    echo "         Edit ExecStart in deploy/openclaw-gateway.service if your" >&2
    echo "         openclaw binary lives elsewhere." >&2
fi

cp "$ROOT_DIR/deploy/openclaw-gateway.service"            "$SYSTEMD_USER_DIR/"
cp "$ROOT_DIR/deploy/openclaw-gateway-watchdog.service"   "$SYSTEMD_USER_DIR/"
cp "$ROOT_DIR/deploy/openclaw-gateway-watchdog.timer"     "$SYSTEMD_USER_DIR/"

chmod +x "$ROOT_DIR/scripts/openclaw_gateway_watchdog.sh"

systemctl --user daemon-reload

systemctl --user enable --now openclaw-gateway.service
systemctl --user enable --now openclaw-gateway-watchdog.timer

echo
echo "Installed and started:"
echo "  openclaw-gateway.service          (Restart=always, crash-loop breaker)"
echo "  openclaw-gateway-watchdog.timer   (deep HTTP health check every 60s)"
echo
echo "Verify:"
echo "  systemctl --user status openclaw-gateway.service"
echo "  journalctl --user -u openclaw-gateway.service -f"
echo "  journalctl --user -u openclaw-gateway-watchdog.service -f"
echo "  curl -s http://127.0.0.1:8090/health"
