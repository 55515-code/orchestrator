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
from datetime import datetime, timezone
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

# Services we care about (systemd --user units)
SERVICES = [
    {
        "name": "kilo-remote",
        "unit": "kilo-remote.service",
        "type": "simple",
        "required": True,
        "description": "Persistent Kilo remote session (mobile control)",
    },
    {
        "name": "kilo-acp",
        "unit": "kilo-acp.service",
        "type": "simple",
        "required": True,
        "description": "Kilo ACP headless server (automation)",
    },
    {
        "name": "substrate-panel",
        "unit": "substrate-panel.service",
        "type": "simple",
        "required": True,
        "description": "Substrate web panel on 127.0.0.1:8090",
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
TIMERS = [
    {
        "name": "substrate-agent-timer",
        "unit": "substrate-agent-timer.timer",
        "required": True,
        "description": "Substrate agent cycle (5min)",
    }
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    # Look for recent agent-cycle logs
    try:
        proc = run(
            ["journalctl", "--user", "-u", "substrate-agent-timer.service", "-n", "20", "--no-pager"],
            capture=True,
        )
        output = proc.stdout
        if "agent-cycle" in output or "agent_cycle" in output or "Finished Substrate agent cycle" in output:
            result["recent"] = True
            result["ok"] = True
            result["last_run"] = utc_now_iso()
            return result
    except Exception:  # noqa: BLE001
        pass

    # Check if timer has fired recently via list-timers
    try:
        proc = run(["systemctl", "--user", "list-timers", "substrate-agent-timer.timer", "--no-pager"])
        output = proc.stdout
        if "substrate-agent-timer.timer" in output and "LEFT" in output:
            result["recent"] = True
            result["ok"] = True
            result["last_run"] = utc_now_iso()
            return result
    except Exception:  # noqa: BLE001
        pass

    if not result["ok"]:
        result["action"] = "agent_cycle_not_recently_observed"

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
    }

    for svc in SERVICES:
        status["services"].append(check_service(svc))

    for tmr in TIMERS:
        status["timers"].append(check_timer(tmr))

    status["agent_cycle"] = check_agent_cycle()
    status["tailscale_serve"] = check_tailscale_serve()

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
