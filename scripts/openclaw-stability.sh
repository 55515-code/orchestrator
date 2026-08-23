#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_CONFIG="/home/ahron/.openclaw/openclaw.json"
OPENCLAW_UNIT="openclaw-gateway.service"
EXPECTED_BIND="loopback"
HEALTH_URL="http://127.0.0.1:8090/healthz"
MAX_RESTARTS=3
RESTART_WINDOW=300

restart_count=0
last_restart=0

while true; do
    now=$(date +%s)
    
    # Check if config has correct bind
    if [ -f "$OPENCLAW_CONFIG" ]; then
        current_bind=$(grep -o '"bind": *"[^"]*"' "$OPENCLAW_CONFIG" | head -1 | sed 's/"bind": *"//;s/"//')
        if [ "$current_bind" != "$EXPECTED_BIND" ]; then
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Config drift detected: bind=$current_bind, expected=$EXPECTED_BIND. Repairing..."
            sed -i "s/\"bind\": *\"[^\"]*\"/\"bind\": \"$EXPECTED_BIND\"/" "$OPENCLAW_CONFIG"
            systemctl --user daemon-reload
            systemctl --user restart "$OPENCLAW_UNIT"
            sleep 5
        fi
    fi
    
    # Check if gateway is healthy
    if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
        restart_count=0
        sleep 30
        continue
    fi
    
    # Gateway is unhealthy - check if we should restart
    if [ $((now - last_restart)) -gt $RESTART_WINDOW ]; then
        restart_count=0
    fi
    
    if [ $restart_count -ge $MAX_RESTARTS ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CRITICAL: Gateway failed $MAX_RESTARTS times in ${RESTART_WINDOW}s. Manual intervention required."
        sleep 60
        continue
    fi
    
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gateway unhealthy. Restarting ($((restart_count+1))/$MAX_RESTARTS)..."
    systemctl --user restart "$OPENCLAW_UNIT"
    last_restart=$now
    restart_count=$((restart_count + 1))
    sleep 10
done
