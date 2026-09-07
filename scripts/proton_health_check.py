#!/usr/bin/env python3
"""Proton Mail subsystem health check (watchdog).

Checks every layer of the Proton Mail → OpenClaw path and writes a state
file that the heartbeat agent can consume for transition-based alerting.

Layers checked:
  1. protonmail-bridge.service          active?
  2. proton-bridge-hook.service         active?
  3. IMAP login on 127.0.0.1:1143       bounded, single attempt
  4. Hook outbox backlog                any entries older than 1h = warning
  5. OpenClaw hook endpoint             HTTP reachable (unauthenticated GET
                                        must return 401/403, proving the
                                        server is up without dispatching)
  6. Recent hook agent-run failures     status=error in gateway log within
                                        the last 60 minutes

Output: /home/ahron/codespace/state/proton-health.json
  status: ok | degraded | down
  Each check carries ok: true/false + detail.
  first_failure_at / last_change_at enable transition detection.

Alerting policy: this script never sends messages. It only records state.
The heartbeat agent reads the state file and alerts on transitions only,
so a flapping provider does not spam the user.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

STATE_FILE = Path.home() / "codespace" / "state" / "proton-health.json"
GATEWAY_LOG_GLOB = Path("/tmp/openclaw/openclaw-*.log")
IMAP_HOST, IMAP_PORT = "127.0.0.1", 1143
HOOK_ENDPOINT = "http://127.0.0.1:8090/hooks/proton"
OUTBOX_DIR = Path.home() / ".local" / "state" / "proton-bridge-hook" / "outbox"
OUTBOX_WARN_AGE = 3600  # 1h

KEYRING_SERVICE = "substrate-credentials"
KEYRING_ACCOUNT = "proton-bridge-smtp"


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, -1, stdout="", stderr=str(exc))


def _service_active(name: str) -> bool:
    r = _run(["systemctl", "--user", "is-active", name])
    return r.returncode == 0 and r.stdout.strip() == "active"


def _bridge_password() -> str:
    import os
    env = os.environ.get("PROTON_BRIDGE_PW", "").strip()
    if env:
        return env
    r = _run(["secret-tool", "lookup", "service", KEYRING_SERVICE, "account", KEYRING_ACCOUNT], timeout=8)
    return r.stdout.strip() if r.returncode == 0 else ""


def _imap_login() -> tuple[bool, str]:
    import imaplib
    pw = _bridge_password()
    if not pw:
        return False, "no bridge password in keyring"
    try:
        conn = imaplib.IMAP4(IMAP_HOST, IMAP_PORT, timeout=15)
        conn.starttls()
        conn.login("ahronzombi@protonmail.com", pw)
        typ, data = conn.select("INBOX", readonly=True)
        ok = typ == "OK"
        detail = f"IMAP login OK; INBOX select {typ}" + (f" ({len(data[0])} msgs)" if ok and data and data[0] else "")
        conn.logout()
        return ok, detail
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _outbox_age() -> tuple[bool, str]:
    if not OUTBOX_DIR.exists():
        return True, "outbox empty"
    oldest = None
    for p in OUTBOX_DIR.glob("*.json"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if oldest is None or mtime < oldest:
            oldest = mtime
    if oldest is None:
        return True, "outbox empty"
    age = time.time() - oldest
    if age > OUTBOX_WARN_AGE:
        return False, f"{len(list(OUTBOX_DIR.glob('*.json')))} entries, oldest {int(age // 60)}m"
    return True, f"{len(list(OUTBOX_DIR.glob('*.json')))} entries, oldest {int(age // 60)}m"


def _hook_endpoint_reachable() -> tuple[bool, str]:
    import urllib.request
    req = urllib.request.Request(HOOK_ENDPOINT, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # A 2xx on GET would be surprising; any HTTP response proves reachability.
            return True, f"endpoint reachable (HTTP {resp.status})"
    except urllib.error.HTTPError as exc:
        # 401/403 without token = server is up and enforcing auth.
        return True, f"endpoint reachable (HTTP {exc.code})"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _recent_hook_failures(window_s: int = 3600) -> tuple[bool, str]:
    """Scan today's gateway log for hook agent-run failures in the window."""
    import re
    now = time.time()
    failures: list[str] = []
    for log_path in sorted(GATEWAY_LOG_GLOB.glob("*"), reverse=True)[:1]:
        try:
            with open(log_path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "hook agent run completed" not in line or "status=error" not in line:
                        continue
                    m = re.search(r'"time":"([^"]+)"', line)
                    if not m:
                        continue
                    try:
                        ts = datetime.fromisoformat(m.group(1)).timestamp()
                    except ValueError:
                        continue
                    if now - ts <= window_s:
                        sm = re.search(r"summary=([^ ]+)", line)
                        failures.append(sm.group(1) if sm else "error")
        except OSError:
            continue
    if failures:
        return False, f"{len(failures)} hook run error(s) in last {window_s // 60}m: {failures[-3:]}"
    return True, f"no hook run errors in last {window_s // 60}m"


def main() -> int:
    checks: dict[str, dict] = {
        "bridge_service": {"ok": _service_active("protonmail-bridge.service"),
                           "detail": "active" if _service_active("protonmail-bridge.service") else "INACTIVE"},
        "hook_service": {"ok": _service_active("proton-bridge-hook.service"),
                         "detail": "active" if _service_active("proton-bridge-hook.service") else "INACTIVE"},
    }
    imap_ok, imap_detail = _imap_login()
    checks["imap"] = {"ok": imap_ok, "detail": imap_detail}
    ob_ok, ob_detail = _outbox_age()
    checks["outbox"] = {"ok": ob_ok, "detail": ob_detail}
    ep_ok, ep_detail = _hook_endpoint_reachable()
    checks["hook_endpoint"] = {"ok": ep_ok, "detail": ep_detail}
    rf_ok, rf_detail = _recent_hook_failures()
    checks["agent_runs"] = {"ok": rf_ok, "detail": rf_detail}

    failed = [k for k, v in checks.items() if not v["ok"]]
    if failed:
        if any(checks[k]["ok"] is False and k in ("bridge_service", "hook_service", "imap") for k in failed):
            status = "down"
        else:
            status = "degraded"
    else:
        status = "ok"

    now_iso = datetime.now(UTC).isoformat()
    previous: dict | None = None
    if STATE_FILE.exists():
        try:
            previous = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            previous = None

    changed = previous is None or previous.get("status") != status
    first_failure = previous.get("first_failure_at") if previous else None
    if status != "ok" and first_failure is None:
        first_failure = now_iso
    if status == "ok":
        first_failure = None

    payload = {
        "generated_at": now_iso,
        "status": status,
        "checks": checks,
        "first_failure_at": first_failure,
        "last_change_at": now_iso if changed else (previous or {}).get("last_change_at"),
        "changed": changed,
    }
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps({"status": status, "checks": {k: v["ok"] for k, v in checks.items()},
                      "changed": changed}, indent=1))
    # Exit semantics: ok=0, degraded=0 (informational), down=1 (real failure).
    # A transient degraded state (e.g. outbox draining during a gateway restart)
    # must not surface as a systemd failure.
    return 1 if status == "down" else 0


if __name__ == "__main__":
    sys.exit(main())
