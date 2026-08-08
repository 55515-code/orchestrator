#!/usr/bin/env bash
# Launch the Local Agent Substrate ops panel and open it in the default browser.
# If the server is already running on the configured port, it skips startup
# and just opens the browser.
#
# Usage: launch_substrate.sh [host] [port]
set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8090}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_LOG="$ROOT/state/serve.log"

mkdir -p "$ROOT/state"

# Check if server is already running
if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
    echo "Substrate server already running on http://${HOST}:${PORT}"
else
    echo "Starting Substrate ops panel on http://${HOST}:${PORT} ..."
    cd "$ROOT"
    nohup uv run python scripts/substrate_cli.py serve --host "$HOST" --port "$PORT" \
        > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!

    # Wait for the server to be ready (up to 30 seconds)
    for i in $(seq 1 60); do
        if curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
            echo "Server is up (PID ${SERVER_PID})."
            break
        fi
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "ERROR: Server process exited unexpectedly." >&2
            echo "Check $SERVER_LOG for details." >&2
            exit 1
        fi
        sleep 0.5
    done

    # Final readiness confirmation
    if ! curl -fsS "http://${HOST}:${PORT}/healthz" >/dev/null 2>&1; then
        echo "ERROR: Server did not become ready within 30 seconds." >&2
        echo "Check $SERVER_LOG for details." >&2
        exit 1
    fi
fi

# Open browser
URL="http://${HOST}:${PORT}/"
echo "Opening $URL in your browser..."
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" 2>/dev/null &
elif command -v open >/dev/null 2>&1; then
    open "$URL" &
else
    echo "No browser opener found. Open $URL manually."
fi

disown 2>/dev/null || true
