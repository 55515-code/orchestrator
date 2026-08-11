#!/usr/bin/env bash
set -euo pipefail

echo "== OpenClaw deployment verification =="

echo "-- systemd unit --"
systemctl --user is-active openclaw-gateway.service || true

echo "-- port 8090 listener --"
ss -tulpn | grep ':8090' || true

echo "-- health endpoint --"
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8090/health || echo "FAIL"

echo ""
echo "-- config check --"
python3 -c "import json; json.load(open('$HOME/.openclaw/openclaw.json'))" && echo "openclaw.json: valid JSON" || echo "openclaw.json: INVALID"

echo "-- skill check --"
test -f "$HOME/.openclaw/skills/kilo-runner/SKILL.md" && echo "kilo-runner skill: present" || echo "kilo-runner skill: MISSING"
