#!/usr/bin/env python3
"""
Substrate persistent lister / verifier.

Runs in an infinite loop, verifies that all substrate automations and
critical services are active, logs status, and attempts self-healing
when a dependency is down. Designed to run as a systemd --user service
with Restart=always so it survives crashes and reboots.

Canonical runtime root: /home/ahron/codespace (the services all run from
here; the worktrees are development-only).
"""

from __future__ import annotations

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
STATE_DIR = ROOT_DIR / "state"
MEMORY_DIR = ROOT_DIR / "memory"
LOG_DIR = MEMORY_DIR / "reliability"
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATUS_FILE = STATE_DIR / "lister-status.json"
LOG_FILE = LOG_DIR / "lister.log"

CHECK_INTERVAL_SECONDS = int(os.environ.get("SUBSTRATE_LISTER_INTERVAL", "60"))

TAILSCALE_BIN = shutil.which("tailscale") or "/usr/bin/tailscale"
OPENCLAW_BIN = shutil.which("openclaw") or "/home/ahron/.npm-global/bin/openclaw"
OPENCLAW_AGENT_CYCLE_JOB_ID = "69997515-7b90-4ddc-95f3-488a1b36d3d9"

# Services we care about (systemd --user units)
# openclaw-gateway is the primary UI on 8090; substrate-panel.service is
# intentionally retired to avoid port conflicts.
# kilo-proxy.service is retired (2026-08-13): the unit was removed after an
# unbounded-memory failure (17.5G peak, SIGKILL) and OpenClaw does not route
# models through it -- no 4097/kilo-proxy refs remain in openclaw.json.
SERVICES = [
    {
        "name": "kilo-remote",
        "unit": "kilo-remote.service",
        "type": "simple",
        "required": True,
        "description": "Persistent Kilo remote session (mobile control)",
    },
    {
        "name": "openclaw-gateway",
        "unit": "openclaw-gateway.service",
        "type": "simple",
        "required": True,
        "description": "OpenClaw Gateway + Control UI on 127.0.0.1:8090",
        "port": 8090,
        "host": "127.0.0.1",
    },
    {
        "name": "substrate-chatbot",
        "unit": "substrate-chatbot.service",
        "type": "simple",
        "required": True,
        "description": "Substrate chatbot HTTP server (headless)",
        "port": 8322,
        "host": "127.0.0.1",
    },
    {
        "name": "ttyd",
        "unit": "ttyd.service",
        "type": "simple",
        "required": True,
        "description": "ttyd web shell (iPhone terminal)",
        "port": 8765,
        "host": "127.0.0.1",
    },
]

# Timers we care about
# Note: substrate-agent-timer was migrated to OpenClaw cron (job id
# OPENCLAW_AGENT_CYCLE_JOB_ID). It is checked separately in check_agent_cycle().
TIMERS = [
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def run(cmd: list[str], *, check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=capture,
        check=check,
    )


def write_status(status: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": utc_now_iso(),
        "ok": all(item.get("ok", False) for item in status.get("services", [])),
        "services": status.get("services", []),
        "timers": status.get("timers", []),
        "agent_cycle": status.get("agent_cycle", {}),
        "tailscale_serve": status.get("tailscale_serve", {}),
        "openclaw_config": status.get("openclaw_config", {}),
    }
    STATUS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def log(msg: str) -> None:
    line = f"[{utc_now_iso()}] {msg}"
    print(line, flush=True)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_service(service: dict[str, Any]) -> dict[str, Any]:
    unit = service["unit"]
    result = {
        "name": service["name"],
        "unit": unit,
        "required": service.get("required", True),
        "description": service.get("description", ""),
        "ok": False,
        "active": False,
        "substate": "",
        "port_open": None,
        "action": None,
    }

    # Try systemctl --user is-active first
    try:
        proc = run(["systemctl", "--user", "is-active", "--", unit])
        active = proc.stdout.strip() == "active"
        result["active"] = active
        result["substate"] = proc.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        result["substate"] = f"error:{exc}"
        active = False

    if active:
        result["ok"] = True
        # Optional port check
        port = service.get("port")
        if port:
            host = service.get("host", "127.0.0.1")
            if _is_port_open(host, port):
                result["port_open"] = True
                result["ok"] = True
            else:
                result["port_open"] = False
                result["ok"] = False
        return result

    # Service is not active — attempt restart if required
    if service.get("required", True):
        restart = run(["systemctl", "--user", "restart", "--", unit])
        if restart.returncode == 0:
            result["action"] = f"restarted {unit}"
            time.sleep(3)
            # Re-check
            try:
                proc2 = run(["systemctl", "--user", "is-active", "--", unit])
                result["active"] = proc2.stdout.strip() == "active"
                result["substate"] = proc2.stdout.strip()
                result["ok"] = result["active"]
            except Exception:  # noqa: BLE001
                pass
        else:
            result["action"] = f"restart_failed:{restart.stderr.strip()}"
    else:
        result["action"] = "skipped (not required)"

    return result


def check_timer(timer: dict[str, Any]) -> dict[str, Any]:
    unit = timer["unit"]
    result = {
        "name": timer["name"],
        "unit": unit,
        "required": timer.get("required", True),
        "description": timer.get("description", ""),
        "ok": False,
        "active": False,
        "action": None,
    }

    try:
        proc = run(["systemctl", "--user", "is-active", "--", unit])
        result["active"] = proc.stdout.strip() == "active"
        result["substate"] = proc.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        result["substate"] = f"error:{exc}"
        result["active"] = False

    result["ok"] = result["active"]

    if not result["active"] and timer.get("required", True):
        start = run(["systemctl", "--user", "start", "--", unit])
        if start.returncode == 0:
            result["action"] = f"started {unit}"
            result["ok"] = True
            result["active"] = True
            result["substate"] = "active"
        else:
            result["action"] = f"start_failed:{start.stderr.strip()}"

    return result


def check_agent_cycle() -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "last_run": None,
        "recent": False,
        "action": None,
    }

    # Check OpenClaw cron job status (agent cycle migrated from systemd timer)
    try:
        proc = run(
            [OPENCLAW_BIN, "cron", "show", OPENCLAW_AGENT_CYCLE_JOB_ID, "--json"],
            capture=True,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            result["ok"] = data.get("enabled", False)
            result["active"] = data.get("enabled", False)
            last_run_ms = data.get("state", {}).get("lastRunAtMs")
            if last_run_ms:
                last_run_dt = datetime.fromtimestamp(last_run_ms / 1000, tz=UTC)
                result["last_run"] = last_run_dt.isoformat()
                # Consider recent if within the last 15 minutes (job runs every 5 min)
                now = datetime.now(tz=UTC)
                if (now - last_run_dt).total_seconds() < 900:
                    result["recent"] = True
            result["action"] = f"openclaw_cron:{data.get('state', {}).get('lastRunStatus', 'unknown')}"
            return result
    except Exception as exc:  # noqa: BLE001
        result["action"] = f"openclaw_cron_check_failed:{exc}"

    if not result["ok"]:
        result["action"] = result.get("action") or "agent_cycle_not_recently_observed"

    return result


def check_tailscale_serve() -> dict[str, Any]:
    """Confirm tailscale is up and :10000 -> 127.0.0.1:8090 is configured."""
    result: dict[str, Any] = {
        "ok": False,
        "tailscale_up": False,
        "serve_configured": False,
        "detail": "",
    }

    if not Path(TAILSCALE_BIN).exists():
        result["detail"] = f"tailscale binary missing: {TAILSCALE_BIN}"
        return result

    status = run([TAILSCALE_BIN, "status", "--json"], capture=True)
    if status.returncode == 0:
        result["tailscale_up"] = True
        try:
            data = json.loads(status.stdout)
            self_node = data.get("SelfNode") or {}
            result["tailscale_ip"] = (self_node.get("Addresses") or [""])[0]
        except json.JSONDecodeError:
            pass
    else:
        result["detail"] = "tailscale not up"

    serve_status = run([TAILSCALE_BIN, "serve", "status"], capture=True)
    if serve_status.returncode == 0:
        text = serve_status.stdout
        result["serve_configured"] = "8090" in text and ("10000" in text or "https" in text.lower())
        result["detail"] = serve_status.stdout.strip()[:300]
    else:
        result["detail"] = serve_status.stderr.strip() or "tailscale serve status failed"

    result["ok"] = result["tailscale_up"] and result["serve_configured"]
    return result


def check_openclaw_config() -> dict[str, Any]:
    """Verify OpenClaw gateway bind is loopback to prevent tailnet drift."""
    result: dict[str, Any] = {
        "ok": False,
        "bind": None,
        "action": None,
    }

    config_path = Path("/home/ahron/.openclaw/openclaw.json")
    if not config_path.exists():
        result["action"] = "config_missing"
        return result

    try:
        data = json.loads(config_path.read_text())
        bind = (((data.get("gateway") or {}).get("bind")) or "")
        result["bind"] = bind
        if bind == "loopback":
            result["ok"] = True
        else:
            result["action"] = f"bind_drift:{bind}"
    except Exception as exc:  # noqa: BLE001
        result["action"] = f"config_read_error:{exc}"

    return result


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def lister_cycle() -> dict[str, Any]:
    status: dict[str, Any] = {
        "checked_at": utc_now_iso(),
        "services": [],
        "timers": [],
        "agent_cycle": {},
        "tailscale_serve": {},
        "openclaw_config": {},
    }

    for svc in SERVICES:
        status["services"].append(check_service(svc))

    for tmr in TIMERS:
        status["timers"].append(check_timer(tmr))

    status["agent_cycle"] = check_agent_cycle()
    status["tailscale_serve"] = check_tailscale_serve()
    status["openclaw_config"] = check_openclaw_config()

    write_status(status)

    # Determine overall health
    unhealthy = [
        s for s in status["services"] if not s.get("ok")
    ] + [
        t for t in status["timers"] if not t.get("ok")
    ]

    if unhealthy:
        names = ", ".join(u["unit"] for u in unhealthy)
        log(f"UNHEALTHY: {names}")
        for u in unhealthy:
            if u.get("action"):
                log(f"  action: {u['action']}")
    else:
        log("ALL_HEALTHY")

    if not status["tailscale_serve"].get("ok"):
        log(f"TAILSCALE_SERVE_DOWN: {status['tailscale_serve'].get('detail', '')[:120]}")

    config = status.get("openclaw_config", {})
    if not config.get("ok"):
        log(f"OPENCLAW_CONFIG_DRIFT: {config.get('action', 'unknown')}")

    return status


def main() -> int:
    log(f"Substrate lister starting (interval={CHECK_INTERVAL_SECONDS}s)")
    while True:
        try:
            lister_cycle()
        except Exception as exc:  # noqa: BLE001
            log(f"LISTER_ERROR: {exc}")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
