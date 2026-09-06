#!/usr/bin/env python3
"""Auto-approval watcher for OpenClaw device pairing requests.

Polls the device_pairing_pending table in the OpenClaw SQLite database
and auto-approves any new pairing requests using the gateway token.
Runs for up to 15 minutes (covers the ~10min setup code expiry window).
"""
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/.openclaw/state/openclaw.sqlite")
OPENCLAW = "/home/ahron/.openclaw/tmp/agent-cli/openclaw"
GATEWAY_URL = "ws://127.0.0.1:8090"
POLL_INTERVAL = 5  # seconds
MAX_RUNTIME = 900  # 15 minutes

# Read gateway token from config (never expose on command line)
with open(os.path.expanduser("~/.openclaw/openclaw.json")) as f:
    cfg = json.load(f)
gateway_token = cfg["gateway"]["auth"]["token"]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def get_pending():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT request_id, device_id, display_name, platform, "
            "client_id, client_mode, scopes_json, remote_ip, ts, refreshed_at_ms "
            "FROM device_pairing_pending ORDER BY ts DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def approve_request(request_id):
    env = os.environ.copy()
    env["OPENCLAW_GATEWAY_TOKEN"] = gateway_token
    result = subprocess.run(
        [OPENCLAW, "devices", "approve", request_id, "--json"],
        capture_output=True, text=True, timeout=30,
        env=env, cwd="/home/ahron/codespace"
    )
    return result.returncode == 0, result.stdout + result.stderr

def main():
    log("Starting auto-approval watcher (15 min timeout)")
    log(f"Database: {DB_PATH}")
    log(f"Gateway: {GATEWAY_URL}")
    log(f"Polling every {POLL_INTERVAL}s for pending pairing requests")

    start = time.time()
    approved = set()

    while time.time() - start < MAX_RUNTIME:
        pending = get_pending()
        for req in pending:
            rid = req["request_id"]
            if rid in approved:
                continue
            log(f"Pending request detected: {rid}")
            log(f"  Display name: {req['display_name'] or 'unknown'}")
            log(f"  Client ID: {req['client_id'] or 'unknown'}")
            log(f"  Platform: {req['platform'] or 'unknown'}")

            ok, detail = approve_request(rid)
            if ok:
                log(f"  APPROVED: {rid}")
                # Record in audit trail
                entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": "auto_device_approval",
                    "tier": 1,
                    "details": {
                        "request_id": rid,
                        "display_name": req.get("display_name"),
                        "client_id": req.get("client_id"),
                        "platform": req.get("platform"),
                        "scopes": json.loads(req.get("scopes_json", "[]") or "[]"),
                        "remote_ip": req.get("remote_ip"),
                        "result": "approved",
                    }
                }
                with open(os.path.expanduser(
                    "~/.openclaw/state/crypto/auto-approval-audit.jsonl"
                ), "a") as f:
                    f.write(json.dumps(entry) + "\n")
                approved.add(rid)
            else:
                log(f"  FAILED to approve {rid}: {detail[:200]}")

        time.sleep(POLL_INTERVAL)

    log("Auto-approval watcher timed out (15 min). Stopping.")
    if not approved:
        log("No pairing requests were approved during the watch period.")
    else:
        log(f"Approved {len(approved)} request(s): {approved}")

if __name__ == "__main__":
    main()
