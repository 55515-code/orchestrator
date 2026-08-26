#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_CONFIG="/home/ahron/.openclaw/openclaw.json"
OPENCLAW_OVERRIDE="/home/ahron/.config/systemd/user/openclaw-gateway.service.d/override.conf"
OPENCLAW_UNIT="openclaw-gateway.service"
EXPECTED_BIND="loopback"
HEALTH_URL="http://127.0.0.1:8090/healthz"
MAX_RESTARTS=2
RESTART_WINDOW=600
STARTUP_GRACE_SECONDS=30

restart_count=0
last_restart=0
last_healthy=0

while true; do
    now=$(date +%s)
    
    # Check if config has correct bind
    if [ -f "$OPENCLAW_CONFIG" ]; then
        current_bind=$(grep -o '"bind": *"[^"]*"' "$OPENCLAW_CONFIG" | head -1 | sed 's/"bind": *"//;s/"//')
        if [ "$current_bind" != "$EXPECTED_BIND" ]; then
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Config drift detected: bind=$current_bind, expected=$EXPECTED_BIND. Repairing..."
            sed -i "s/\"bind\": *\"[^\"]*\"/\"bind\": \"$EXPECTED_BIND\"/" "$OPENCLAW_CONFIG"
            chmod 0444 "$OPENCLAW_CONFIG"
            systemctl --user daemon-reload
            systemctl --user restart "$OPENCLAW_UNIT"
            sleep 5
        fi
        
        # Enforce read-only permissions to prevent OpenClaw from rewriting
        current_perms=$(stat -c "%a" "$OPENCLAW_CONFIG" 2>/dev/null || stat -f "%Lp" "$OPENCLAW_CONFIG" 2>/dev/null || echo "000")
        if [ "$current_perms" != "444" ]; then
            chmod 0444 "$OPENCLAW_CONFIG" 2>/dev/null || true
        fi
    fi
    
    # Check if systemd override has correct bind
    if [ -f "$OPENCLAW_OVERRIDE" ]; then
        override_bind=$(grep -oE -- "--bind [^ ]*" "$OPENCLAW_OVERRIDE" | head -1 | awk '{print $2}' || true)
        if [ "$override_bind" != "$EXPECTED_BIND" ]; then
            echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Override drift detected: bind=$override_bind, expected=$EXPECTED_BIND. Repairing..."
            sed -i "s|--bind [^ ]*|--bind $EXPECTED_BIND|g" "$OPENCLAW_OVERRIDE"
            chmod 0444 "$OPENCLAW_OVERRIDE"
            systemctl --user daemon-reload
            systemctl --user restart "$OPENCLAW_UNIT"
            sleep 5
        fi
        
        # Enforce read-only permissions on override
        current_perms=$(stat -c "%a" "$OPENCLAW_OVERRIDE" 2>/dev/null || stat -f "%Lp" "$OPENCLAW_OVERRIDE" 2>/dev/null || echo "000")
        if [ "$current_perms" != "444" ]; then
            chmod 0444 "$OPENCLAW_OVERRIDE" 2>/dev/null || true
        fi
    fi
    
    # Skip health check during startup grace period after restart
    if [ $((now - last_restart)) -lt $STARTUP_GRACE_SECONDS ]; then
        sleep 10
        continue
    fi
    
    # Check if gateway is healthy (with retry)
    healthy=false
    for attempt in 1 2 3; do
        if curl -sf "$HEALTH_URL" >/dev/null 2>&1; then
            healthy=true
            break
        fi
        sleep 2
    done
    
    if [ "$healthy" = true ]; then
        restart_count=0
        last_healthy=$now
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
    sleep 15
done
