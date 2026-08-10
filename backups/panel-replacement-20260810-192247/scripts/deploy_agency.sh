#!/usr/bin/env bash
# deploy_agency.sh — one-shot operator deployment of the full agency stack.
# Idempotent: safe to re-run any time. Run from /home/ahron/codespace.
set -euo pipefail

cd /home/ahron/codespace

echo "=== 1/4 daemon-reload ==="
systemctl --user daemon-reload

echo "=== 2/4 agency bootstrap (units + kilo remote + panel) ==="
uv run python scripts/ensure_agency.py || true

echo "=== 3/4 tailscale serve :10000 -> 127.0.0.1:8090 ==="
if tailscale serve status 2>/dev/null | grep -q "8090"; then
  echo "already configured"
else
  echo "configuring (one-time sudo; enter your password if prompted)"
  sudo tailscale serve --bg --https=10000 http://127.0.0.1:8090 || echo "WARN: tailscale serve failed"
fi

echo "=== 4/4 final status ==="
sleep 2
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/codespace/state/agency-status.json")
try:
    d = json.load(open(p))
except FileNotFoundError:
    print("agency-status.json not found — bootstrap did not complete")
    raise SystemExit(1)
print("healthy:", d.get("healthy"))
print("tailscale_ok:", d.get("tailscale_ok"))
print("tailscale:", json.dumps(d.get("tailscale", {}), indent=2))
print("panel_http:", json.dumps(d.get("panel_http", {}), indent=2))
print("kilo_remote:", json.dumps(d.get("kilo_remote", {}), indent=2))
units = d.get("systemd", {}).get("units", {})
for name, st in units.items():
    print(f"  unit {name}: {st.get('state')} ok={st.get('ok')} action={st.get('action')}")
PY

echo
echo "Done. Panel:  http://127.0.0.1:8090   (tailnet: https://<tailscale-ip>:10000)"
echo "Logs:  journalctl --user -u substrate-lister -f"
