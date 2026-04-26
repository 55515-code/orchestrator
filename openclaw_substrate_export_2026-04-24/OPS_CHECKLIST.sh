#!/usr/bin/env bash
set -euo pipefail

echo "== OpenClaw + Caddy Health =="
sudo systemctl is-active openclaw-gateway caddy
sudo systemctl status openclaw-gateway --no-pager -l | sed -n '1,60p'
sudo systemctl status caddy --no-pager -l | sed -n '1,60p'

echo "== Public URL probe =="
curl -skI https://ocrow.34-173-227-78.sslip.io/ | sed -n '1,25p'

echo "== Open ports =="
sudo ss -tulpn

echo "== Disk/Memory =="
df -h
free -h
uptime

echo "== OpenClaw status --all =="
PW="$(sudo sed -n 's/^OPENCLAW_GATEWAY_PASSWORD=//p' /etc/openclaw/openclaw-gateway.env | head -n1)"
sudo -iu ahronzombi env OPENCLAW_GATEWAY_PASSWORD="$PW" /home/ahronzombi/.npm-global/bin/openclaw status --all
