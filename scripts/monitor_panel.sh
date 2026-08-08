#!/usr/bin/env bash
# Panel health monitor — part of the swarm-control production deployment.
#
# Checks the substrate control panel health endpoint and service state.
# With --restart, restarts the systemd service after 3 consecutive failures.
# All output is written to journald so `journalctl --user -u substrate-panel-monitor` shows history.

set -uo pipefail

PANEL_URL="${PANEL_URL:-http://127.0.0.1:8090}"
SERVICE="${PANEL_SERVICE:-substrate-panel.service}"
STATE_DIR="${STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/substrate-panel-monitor}"
FAILURES=0

mkdir -p "$STATE_DIR"

log() { echo "panel-monitor: $*"; }

check_healthz() {
    curl -fsS --max-time 5 "$PANEL_URL/healthz" >/dev/null 2>&1
}

if check_healthz; then
    echo 0 > "$STATE_DIR/failures"
    log "healthz OK"
    exit 0
fi

# Restore failure count, bump it.
if [ -f "$STATE_DIR/failures" ]; then
    FAILURES=$(cat "$STATE_DIR/failures")
fi
FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$STATE_DIR/failures"

log "healthz UNREACHABLE (failure $FAILURES)"

if [ "$FAILURES" -ge 3 ]; then
    log "3 consecutive failures; restarting $SERVICE"
    if systemctl --user restart "$SERVICE" 2>/dev/null; then
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
