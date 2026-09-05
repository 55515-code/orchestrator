#!/usr/bin/env bash
# Install the OpenClaw Gateway Watchdog systemd user service.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
WATCHDOG_PY="$ROOT_DIR/substrate/watchdog/gateway_watchdog.py"
WATCHDOG_UNIT="$HOME/.config/systemd/user/openclaw-gateway-watchdog.service"

echo "== Installing OpenClaw Gateway Watchdog =="

# 1. Verify Python module compiles
echo "-- verifying watchdog module --"
uv run python -m compileall "$WATCHDOG_PY"

# 2. Install systemd unit
echo "-- installing systemd unit --"
mkdir -p "$(dirname "$WATCHDOG_UNIT")"
cp "$SCRIPT_DIR/../templates/openclaw-gateway-watchdog.service" "$WATCHDOG_UNIT" 2>/dev/null || true

# If template doesn't exist, write inline
if [ ! -s "$WATCHDOG_UNIT" ]; then
    cat > "$WATCHDOG_UNIT" <<'EOF'
[Unit]
Description=OpenClaw Gateway Watchdog
After=network.target openclaw-gateway.service
Wants=openclaw-gateway.service

[Service]
Type=simple
ExecStart=/usr/bin/env uv run python /home/ahron/codespace/substrate/watchdog/gateway_watchdog.py
WorkingDirectory=/home/ahron/codespace
Restart=always
RestartSec=10
Environment=GATEWAY_WATCHDOG_INTERVAL=30
Environment=GATEWAY_WATCHDOG_GRACE=20
Environment=GATEWAY_WATCHDOG_MAX_RESTARTS=3
Environment=GATEWAY_WATCHDOG_RESTART_WINDOW=600

# Hardening
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=default.target
EOF
fi

chmod 644 "$WATCHDOG_UNIT"

# 3. Reload systemd and enable
echo "-- enabling service --"
systemctl --user daemon-reload
systemctl --user enable --now openclaw-gateway-watchdog.service

# 4. Verify
echo "-- verifying --"
sleep 2
if systemctl --user is-active --quiet openclaw-gateway-watchdog.service; then
    echo "Watchdog service is ACTIVE"
else
    echo "Watchdog service FAILED to start"
    systemctl --user status openclaw-gateway-watchdog.service || true
    exit 1
fi

echo "== Installation complete =="
echo "View logs: journalctl --user -u openclaw-gateway-watchdog.service -f"
echo "Status:   systemctl --user status openclaw-gateway-watchdog.service"
echo "Stop:     systemctl --user stop openclaw-gateway-watchdog.service"
echo "Disable:  systemctl --user disable openclaw-gateway-watchdog.service"
