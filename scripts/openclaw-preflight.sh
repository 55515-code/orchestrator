#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_CONFIG="${OPENCLAW_CONFIG:-/home/ahron/.openclaw/openclaw.json}"

if [ ! -f "$OPENCLAW_CONFIG" ]; then
    echo "[openclaw-preflight] FATAL: Config missing: $OPENCLAW_CONFIG"
    exit 1
fi

# Extract bind mode
BIND=$(grep -o '"bind": *"[^"]*"' "$OPENCLAW_CONFIG" | head -1 | sed 's/"bind": *"//;s/"//' || echo "")
# Extract allowedOrigins
ORIGINS=$(grep -A5 '"allowedOrigins"' "$OPENCLAW_CONFIG" | grep -o '"[^"]*"' | tr -d '"' | grep -v 'allowedOrigins' || true)
# Extract tailscale mode
TAILSCALE_MODE=$(python3 -c "
import json, sys
with open('$OPENCLAW_CONFIG') as f:
    data = json.load(f)
print(((data.get('gateway') or {}).get('tailscale') or {}).get('mode', ''))
" 2>/dev/null || echo "")

echo "[openclaw-preflight] bind=$BIND tailscale_mode=$TAILSCALE_MODE"

# Check 1: bind=loopback with LAN origins = misconfiguration that breaks mobile devices
LAN_ORIGINS=$(echo "$ORIGINS" | grep -E '^http://192\.168\.|^http://10\.|^http://172\.' || true)
if [ "$BIND" = "loopback" ] && [ -n "$LAN_ORIGINS" ]; then
    echo "[openclaw-preflight] ERROR: gateway.bind=loopback but allowedOrigins contains LAN IPs:"
    echo "$LAN_ORIGINS" | while read -r origin; do
        echo "[openclaw-preflight]   - $origin"
    done
    echo "[openclaw-preflight] iPhone/Android devices on LAN cannot reach gateway on 127.0.0.1."
    echo "[openclaw-preflight] Fix: set gateway.bind=lan or remove LAN origins from allowedOrigins."
    echo "[openclaw-preflight] Also check: gateway.tailscale.mode=funnel requires gateway.auth.mode=password."
fi

# Check 2: tailscale funnel requires password auth
if [ "$TAILSCALE_MODE" = "funnel" ]; then
    AUTH_MODE=$(python3 -c "
import json, sys
with open('$OPENCLAW_CONFIG') as f:
    data = json.load(f)
print(((data.get('gateway') or {}).get('auth') or {}).get('mode', ''))
" 2>/dev/null || echo "")
    if [ "$AUTH_MODE" != "password" ]; then
        echo "[openclaw-preflight] ERROR: gateway.tailscale.mode=funnel requires gateway.auth.mode=password, but found mode=$AUTH_MODE"
        echo "[openclaw-preflight] Fix: set gateway.auth.mode=password or remove tailscale.funnel config."
    fi
fi

# Check 3: bind=lan requires LAN-accessible listen address
if [ "$BIND" = "lan" ]; then
    echo "[openclaw-preflight] INFO: bind=lan exposes gateway on LAN interfaces."
    echo "[openclaw-preflight] INFO: Ensure gateway.auth.mode is set (token/password) to protect LAN access."
fi

exit 0
