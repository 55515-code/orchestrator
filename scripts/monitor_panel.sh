#!/usr/bin/env bash
# Panel health monitor — part of the swarm-control production deployment.
#
# Checks the OpenClaw control panel health endpoint and service state.
# With --restart, restarts the systemd service after 3 consecutive failures.
# All output is written to journald so `journalctl --user -u openclaw-gateway` shows history.

set -uo pipefail

PANEL_URL="${PANEL_URL:-http://127.0.0.1:8090}"
SERVICE="${PANEL_SERVICE:-openclaw-gateway.service}"
STATE_DIR="${STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/substrate-panel-monitor}"
FAILURES=0
MAX_RESTARTS="${MAX_RESTARTS:-5}"
RESTART_WINDOW_SECONDS="${RESTART_WINDOW_SECONDS:-600}"

mkdir -p "$STATE_DIR"

log() { echo "panel-monitor: $*"; }

# Native OpenClaw gateway answers /health ({"ok":true}); the container image
# answers /healthz. Probe both so endpoint drift doesn't cause false outages.
check_healthz() {
    curl -fsS --max-time 5 "$PANEL_URL/health"  >/dev/null 2>&1 ||
    curl -fsS --max-time 5 "$PANEL_URL/healthz" >/dev/null 2>&1
}

# Crash-loop breaker: refuse to restart if the gateway has been restarted too
# many times recently (broken config / port conflict would otherwise hot-loop).
restart_allowed() {
    local now cutoff count
    now=$(date +%s)
    cutoff=$((now - RESTART_WINDOW_SECONDS))
    if [ -f "$STATE_DIR/restarts" ]; then
        awk -v c="$cutoff" '$1 >= c' "$STATE_DIR/restarts" > "$STATE_DIR/restarts.tmp" 2>/dev/null
        mv -f "$STATE_DIR/restarts.tmp" "$STATE_DIR/restarts" 2>/dev/null
    fi
    count=0
    [ -f "$STATE_DIR/restarts" ] && count="$(wc -l < "$STATE_DIR/restarts" 2>/dev/null || echo 0)"
    [ "$count" -lt "$MAX_RESTARTS" ]
}

record_restart() { date +%s >> "$STATE_DIR/restarts"; }

if check_healthz; then
    echo 0 > "$STATE_DIR/failures"
    log "health OK"
    exit 0
fi

# Restore failure count, bump it.
if [ -f "$STATE_DIR/failures" ]; then
    FAILURES=$(cat "$STATE_DIR/failures")
fi
FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$STATE_DIR/failures"

log "health UNREACHABLE (failure $FAILURES)"

if [ "$FAILURES" -ge 3 ]; then
    if ! restart_allowed; then
        log "restart limit reached (${MAX_RESTARTS} in ${RESTART_WINDOW_SECONDS}s); NOT restarting $SERVICE"
        exit 1
    fi
    log "3 consecutive failures; restarting $SERVICE"
    if systemctl --user restart "$SERVICE" 2>/dev/null; then
        record_restart
        sleep 5
        if check_healthz; then
            echo 0 > "$STATE_DIR/failures"
            log "service restarted and healthy"
        else
            log "service restarted but STILL unhealthy"
        fi
    else
        log "failed to restart $SERVICE"
    fi
fi

exit 1
