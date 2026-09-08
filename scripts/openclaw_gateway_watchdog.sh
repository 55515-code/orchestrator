#!/usr/bin/env bash
# openclaw_gateway_watchdog.sh — deep health watchdog for the OpenClaw Gateway.
#
# Unlike ensure_agency.py (which only checks `systemctl --user is-active` and
# a raw TCP connect), this watchdog performs a real HTTP health probe. A
# gateway that is "active" but no longer answering /health (hung event loop,
# stale socket, wedged channel adapter) is force-restarted.
#
# Crash-loop protection: if the gateway is restarted more than
# MAX_RESTARTS times within WINDOW_SECONDS, the watchdog stops restarting and
# logs CRITICAL instead of amplifying a broken config into a hot loop.
#
# Intended to run every 60s from openclaw-gateway-watchdog.timer. All output
# goes to stdout/stderr so systemd captures it in the journal:
#   journalctl --user -u openclaw-gateway-watchdog.service -f

set -uo pipefail

HOST="${OPENCLAW_GATEWAY_HOST:-127.0.0.1}"
PORT="${OPENCLAW_GATEWAY_PORT:-8090}"
SERVICE="${OPENCLAW_GATEWAY_SERVICE:-openclaw-gateway.service}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/openclaw-gateway-watchdog"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-5}"
MAX_RESTARTS="${MAX_RESTARTS:-5}"
WINDOW_SECONDS="${WINDOW_SECONDS:-600}"
POST_RESTART_WAIT="${POST_RESTART_WAIT:-8}"

mkdir -p "$STATE_DIR"
FAILURES_FILE="$STATE_DIR/failures"
RESTARTS_FILE="$STATE_DIR/restarts"

log()  { echo "openclaw-watchdog: $*"; }
warn() { echo "openclaw-watchdog WARNING: $*" >&2; }
crit() { echo "openclaw-watchdog CRITICAL: $*" >&2; }

now_epoch() { date +%s; }

# ---------------------------------------------------------------------------
# Health probe: /health first (native gateway returns {"ok":true}), then
# /healthz (container image healthcheck). HTTP 200 on either counts as healthy.
# ---------------------------------------------------------------------------
probe_health() {
    local url
    for path in /health /healthz; do
        url="http://${HOST}:${PORT}${path}"
        if curl -fsS --max-time "$HEALTH_TIMEOUT" "$url" >/dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Crash-loop breaker: prune restart timestamps older than the window, then
# refuse to restart if too many recent restarts remain.
# ---------------------------------------------------------------------------
restart_allowed() {
    local now cutoff count
    now="$(now_epoch)"
    cutoff=$((now - WINDOW_SECONDS))
    if [ -f "$RESTARTS_FILE" ]; then
        # Keep only timestamps inside the window.
        awk -v c="$cutoff" '$1 >= c' "$RESTARTS_FILE" > "$RESTARTS_FILE.tmp" 2>/dev/null
        mv -f "$RESTARTS_FILE.tmp" "$RESTARTS_FILE" 2>/dev/null
    fi
    count=0
    [ -f "$RESTARTS_FILE" ] && count="$(wc -l < "$RESTARTS_FILE" 2>/dev/null || echo 0)"
    if [ "$count" -ge "$MAX_RESTARTS" ]; then
        return 1
    fi
    return 0
}

record_restart() {
    now_epoch >> "$RESTARTS_FILE"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if probe_health; then
    echo 0 > "$FAILURES_FILE"
    log "health OK"
    exit 0
fi

# Restore and bump the consecutive-failure counter.
FAILURES=0
[ -f "$FAILURES_FILE" ] && FAILURES="$(cat "$FAILURES_FILE" 2>/dev/null || echo 0)"
FAILURES=$((FAILURES + 1))
echo "$FAILURES" > "$FAILURES_FILE"

log "health probe FAILED (consecutive failures: $FAILURES)"

# Only act after a single failed probe — a hung gateway should be restarted
# immediately, not after N failures, because every minute offline is downtime.
if ! restart_allowed; then
    crit "restart limit reached (${MAX_RESTARTS} restarts in ${WINDOW_SECONDS}s); NOT restarting ${SERVICE}. Investigate config/port/disk and run: openclaw doctor --fix"
    exit 1
fi

if systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
    log "unit active but HTTP down — force restarting ${SERVICE}"
else
    log "unit not active — starting ${SERVICE}"
fi

if systemctl --user restart "$SERVICE" 2>/dev/null; then
    record_restart
    sleep "$POST_RESTART_WAIT"
    if probe_health; then
        echo 0 > "$FAILURES_FILE"
        log "restarted ${SERVICE}; health OK"
        exit 0
    fi
    warn "restarted ${SERVICE} but still unhealthy after ${POST_RESTART_WAIT}s"
else
    warn "failed to restart ${SERVICE}"
fi

exit 1
