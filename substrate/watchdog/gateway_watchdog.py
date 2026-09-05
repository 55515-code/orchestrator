"""OpenClaw Gateway Watchdog.

Automated, persistent background watchdog for the OpenClaw gateway service.
Detects outages, diagnoses root causes, performs remediation, and logs
all actions for audit.

Usage:
    uv run python substrate/watchdog/gateway_watchdog.py
    uv run python substrate/watchdog/gateway_watchdog.py --once
    uv run python substrate/watchdog/gateway_watchdog.py --status
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT_DIR = Path("/home/ahron/codespace")
STATE_DIR = ROOT_DIR / "state" / "watchdog"
LOG_DIR = ROOT_DIR / "memory" / "reliability"
DEFAULT_INTERVAL = int(os.environ.get("GATEWAY_WATCHDOG_INTERVAL", "30"))
GRACE_AFTER_RESTART = int(os.environ.get("GATEWAY_WATCHDOG_GRACE", "20"))
MAX_RESTARTS = int(os.environ.get("GATEWAY_WATCHDOG_MAX_RESTARTS", "3"))
RESTART_WINDOW = int(os.environ.get("GATEWAY_WATCHDOG_RESTART_WINDOW", "600"))
HEALTH_URL = os.environ.get("GATEWAY_HEALTH_URL", "http://127.0.0.1:8090/healthz")
SERVICE_UNIT = os.environ.get("GATEWAY_SERVICE_UNIT", "openclaw-gateway.service")
PORT = int(os.environ.get("GATEWAY_PORT", "8090"))
HOST = os.environ.get("GATEWAY_HOST", "127.0.0.1")
OPENCLAW_CONFIG = Path(os.environ.get("OPENCLAW_CONFIG", str(Path.home() / ".openclaw" / "openclaw.json")))
LOG_FILE = LOG_DIR / "gateway-watchdog.log"
STATUS_FILE = STATE_DIR / "status.json"
AUDIT_FILE = STATE_DIR / "audit.jsonl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def utc_now_ts() -> float:
    return datetime.now(UTC).timestamp()


def run(cmd: list[str], *, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=check,
    )


def is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pid_on_port(port: int) -> int | None:
    """Return the PID listening on port, or None."""
    ss = shutil.which("ss") or "/usr/bin/ss"
    proc = run([ss, "-tlnp"])
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if f":{port} " in line and "LISTEN" in line:
            # Extract pid from users:(("...",pid=1234,fd=...))
            import re

            m = re.search(r"pid=(\d+)", line)
            if m:
                return int(m.group(1))
    return None


def write_audit(record: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    record["_ts"] = utc_now_iso()
    # `default=str` guarantees the audit trail is never lost to a stray
    # non-serializable value (e.g. a subprocess wrapper or exception object).
    # A watchdog must not crash while recording why it acted.
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_status(status: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False, default=str))


def log(msg: str) -> None:
    line = f"[{utc_now_iso()}] {msg}"
    print(line, flush=True)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_http_health() -> dict[str, Any]:
    result: dict[str, Any] = {
        "check": "http_health",
        "ok": False,
        "status_code": None,
        "detail": "",
    }
    try:
        import urllib.request

        with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
            result["status_code"] = resp.status
            result["ok"] = resp.status == 200
            result["detail"] = "ok"
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def check_systemd() -> dict[str, Any]:
    result: dict[str, Any] = {
        "check": "systemd",
        "ok": False,
        "active": False,
        "substate": "",
        "detail": "",
    }
    proc = run(["systemctl", "--user", "is-active", "--", SERVICE_UNIT])
    result["substate"] = proc.stdout.strip()
    result["active"] = proc.stdout.strip() == "active"
    result["ok"] = result["active"]
    if not result["ok"]:
        result["detail"] = proc.stderr.strip() or f"substate={result['substate']}"
    return result


def check_port() -> dict[str, Any]:
    result: dict[str, Any] = {
        "check": "port_listener",
        "ok": False,
        "port": PORT,
        "pid": None,
        "detail": "",
    }
    if is_port_open(HOST, PORT):
        result["ok"] = True
        result["pid"] = pid_on_port(PORT)
    else:
        result["detail"] = f"port {HOST}:{PORT} not listening"
    return result


def check_resource_usage() -> dict[str, Any]:
    """Check if the gateway process is consuming excessive resources."""
    result: dict[str, Any] = {
        "check": "resource_usage",
        "ok": True,
        "memory_mb": None,
        "cpu_percent": None,
        "detail": "",
    }

    pid = pid_on_port(PORT)
    if pid is None:
        result["ok"] = False
        result["detail"] = "gateway pid not found"
        return result

    # Try to get memory info from /proc
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    result["memory_mb"] = round(kb / 1024, 1)
                    break
    except OSError:
        pass

    # Flag if memory > 1GB
    if result["memory_mb"] is not None and result["memory_mb"] > 1024:
        result["ok"] = False
        result["detail"] = f"memory {result['memory_mb']}MB > 1024MB threshold"

    return result


def check_config() -> dict[str, Any]:
    """Check OpenClaw config validity and drift."""
    result: dict[str, Any] = {
        "check": "config",
        "ok": False,
        "exists": False,
        "valid_json": False,
        "bind": None,
        "detail": "",
    }

    if not OPENCLAW_CONFIG.exists():
        result["detail"] = f"config missing: {OPENCLAW_CONFIG}"
        return result
    result["exists"] = True

    try:
        data = json.loads(OPENCLAW_CONFIG.read_text())
        result["valid_json"] = True
        gateway = data.get("gateway") or {}
        bind = gateway.get("bind") or ""
        result["bind"] = bind
        if bind in ("loopback", "lan"):
            result["ok"] = True
        else:
            result["detail"] = f"unexpected bind value: {bind}"
    except json.JSONDecodeError as exc:
        result["detail"] = f"invalid JSON: {exc}"
    except OSError as exc:
        result["detail"] = str(exc)

    return result


def check_upstream_dns() -> dict[str, Any]:
    """Basic check that the host can resolve external DNS (for webhook delivery)."""
    result: dict[str, Any] = {
        "check": "upstream_dns",
        "ok": False,
        "detail": "",
    }
    try:
        proc = run(["host", "graph.facebook.com"], timeout=5)
        if proc.returncode == 0:
            result["ok"] = True
        else:
            result["detail"] = proc.stderr.strip() or "DNS resolution failed"
    except Exception as exc:  # noqa: BLE001
        result["detail"] = str(exc)
    return result


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


def diagnose(checks: dict[str, dict[str, Any]]) -> str:
    """Return a diagnosis label based on check results."""
    http_ok = checks.get("http_health", {}).get("ok", False)
    systemd_ok = checks.get("systemd", {}).get("ok", False)
    port_ok = checks.get("port_listener", {}).get("ok", False)
    config_ok = checks.get("config", {}).get("ok", False)
    resource_ok = checks.get("resource_usage", {}).get("ok", False)
    dns_ok = checks.get("upstream_dns", {}).get("ok", False)

    if not systemd_ok:
        return "SYSTEMD_FAILED"
    if not port_ok:
        return "PORT_DOWN"
    if not http_ok and port_ok:
        return "HTTP_UNHEALTHY"
    if not config_ok:
        return "CONFIG_DRIFT"
    if not resource_ok:
        return "RESOURCE_EXHAUSTION"
    if not dns_ok:
        return "UPSTREAM_DNS_FAILURE"
    return "HEALTHY"


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------


def remediate(diagnosis: str, checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Attempt to fix the diagnosed issue. Returns action record."""
    result: dict[str, Any] = {
        "diagnosis": diagnosis,
        "action": "none",
        "success": False,
        "detail": "",
    }

    if diagnosis == "HEALTHY":
        result["success"] = True
        return result

    if diagnosis == "SYSTEMD_FAILED":
        result["action"] = "restart_service"
        proc = run(["systemctl", "--user", "restart", SERVICE_UNIT])
        result["success"] = proc.returncode == 0
        result["detail"] = proc.stderr.strip() or proc.stdout.strip()
        return result

    if diagnosis == "PORT_DOWN":
        # Service may have crashed; try restart.
        result["action"] = "restart_service"
        proc = run(["systemctl", "--user", "restart", SERVICE_UNIT])
        result["success"] = proc.returncode == 0
        result["detail"] = proc.stderr.strip() or proc.stdout.strip()
        return result

    if diagnosis == "HTTP_UNHEALTHY":
        # Port is up but HTTP is not responding — likely hung process.
        result["action"] = "restart_service"
        proc = run(["systemctl", "--user", "restart", SERVICE_UNIT])
        result["success"] = proc.returncode == 0
        result["detail"] = proc.stderr.strip() or proc.stdout.strip()
        return result

    if diagnosis == "CONFIG_DRIFT":
        result["action"] = "log_config_drift"
        result["success"] = True
        result["detail"] = f"bind={checks.get('config', {}).get('bind')}"
        # Do NOT auto-repair config; that is a Tier 2 action requiring human review.
        return result

    if diagnosis == "RESOURCE_EXHAUSTION":
        result["action"] = "restart_service"
        proc = run(["systemctl", "--user", "restart", SERVICE_UNIT])
        result["success"] = proc.returncode == 0
        result["detail"] = proc.stderr.strip() or proc.stdout.strip()
        return result

    if diagnosis == "UPSTREAM_DNS_FAILURE":
        result["action"] = "escalate_dns"
        result["success"] = True
        result["detail"] = "DNS resolution failed; no automated remediation available"
        return result

    # Unknown diagnosis
    result["action"] = "unknown_diagnosis"
    result["detail"] = f"no remediation defined for {diagnosis}"
    return result


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict[str, Any]) -> None:
    write_status(state)


def rate_limit_exceeded(state: dict[str, Any]) -> bool:
    now = utc_now_ts()
    restarts = state.get("restart_timestamps", [])
    # Keep only restarts within the window
    recent = [t for t in restarts if now - t <= RESTART_WINDOW]
    state["restart_timestamps"] = recent
    return len(recent) >= MAX_RESTARTS


def record_restart(state: dict[str, Any]) -> None:
    state.setdefault("restart_timestamps", []).append(utc_now_ts())


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_checks() -> dict[str, Any]:
    return {
        "http_health": check_http_health(),
        "systemd": check_systemd(),
        "port_listener": check_port(),
        "resource_usage": check_resource_usage(),
        "config": check_config(),
        "upstream_dns": check_upstream_dns(),
    }


def watchdog_cycle(state: dict[str, Any]) -> dict[str, Any]:
    checks = run_checks()
    diagnosis = diagnose(checks)
    state["last_check"] = utc_now_iso()
    state["last_diagnosis"] = diagnosis
    state["last_checks"] = checks

    healthy = diagnosis == "HEALTHY"
    state["healthy"] = healthy

    if healthy:
        state["consecutive_failures"] = 0
        save_state(state)
        return state

    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1

    # Check rate limit before remediating
    if rate_limit_exceeded(state):
        action_record = {
            "event": "rate_limit_exceeded",
            "diagnosis": diagnosis,
            "detail": f"{MAX_RESTARTS} restarts in {RESTART_WINDOW}s; manual intervention required",
        }
        write_audit(action_record)
        log(f"RATE_LIMIT_EXCEEDED: {diagnosis} — manual intervention required")
        save_state(state)
        return state

    # Perform remediation
    action_record = remediate(diagnosis, checks)
    action_record["event"] = "remediation"
    action_record["consecutive_failures"] = state["consecutive_failures"]
    write_audit(action_record)

    if action_record["success"]:
        record_restart(state)
        log(f"REMEDIATION_OK: {diagnosis} -> {action_record['action']}")
        # Wait for grace period before next check
        time.sleep(GRACE_AFTER_RESTART)
    else:
        log(f"REMEDIATION_FAILED: {diagnosis} -> {action_record['action']}: {action_record['detail']}")

    save_state(state)
    return state


def run_once() -> dict[str, Any]:
    state = load_state()
    state = watchdog_cycle(state)
    print(json.dumps(state, indent=2, ensure_ascii=False, default=str))
    return state


def run_daemon() -> None:
    log(f"Gateway watchdog starting (interval={DEFAULT_INTERVAL}s, max_restarts={MAX_RESTARTS}/{RESTART_WINDOW}s)")
    state = load_state()
    while True:
        try:
            state = watchdog_cycle(state)
            if state.get("healthy"):
                log("OK")
            else:
                log(f"UNHEALTHY: {state.get('last_diagnosis')}")
        except Exception as exc:  # noqa: BLE001
            log(f"WATCHDOG_ERROR: {exc}")
            write_audit({"event": "watchdog_error", "error": str(exc)})
        time.sleep(DEFAULT_INTERVAL)


# ---------------------------------------------------------------------------
# Status / reporting
# ---------------------------------------------------------------------------


def print_status() -> int:
    if not STATUS_FILE.exists():
        print("No status file found. Watchdog may not be running.")
        return 1
    state = json.loads(STATUS_FILE.read_text())
    healthy = state.get("healthy")
    diagnosis = state.get("last_diagnosis", "unknown")
    last_check = state.get("last_check", "never")
    consecutive = state.get("consecutive_failures", 0)
    restarts = len(state.get("restart_timestamps", []))

    status = "HEALTHY" if healthy else "UNHEALTHY"
    print(f"Status:   {status}")
    print(f"Diagnosis: {diagnosis}")
    print(f"Last check: {last_check}")
    print(f"Consecutive failures: {consecutive}")
    print(f"Restarts in window: {restarts}/{MAX_RESTARTS}")
    return 0 if healthy else 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    global DEFAULT_INTERVAL, GRACE_AFTER_RESTART, MAX_RESTARTS, RESTART_WINDOW

    parser = argparse.ArgumentParser(description="OpenClaw Gateway Watchdog")
    parser.add_argument("--once", action="store_true", help="Run one check cycle and exit")
    parser.add_argument("--status", action="store_true", help="Print current status from state file")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Polling interval in seconds")
    parser.add_argument("--grace", type=int, default=GRACE_AFTER_RESTART, help="Grace period after restart")
    parser.add_argument("--max-restarts", type=int, default=MAX_RESTARTS, help="Max restarts in window")
    parser.add_argument("--window", type=int, default=RESTART_WINDOW, help="Restart window in seconds")
    args = parser.parse_args()

    DEFAULT_INTERVAL = args.interval
    GRACE_AFTER_RESTART = args.grace
    MAX_RESTARTS = args.max_restarts
    RESTART_WINDOW = args.window

    if args.status:
        return print_status()
    if args.once:
        state = run_once()
        return 0 if state.get("healthy") else 2
    run_daemon()
    return 0


if __name__ == "__main__":
    sys.exit(main())
