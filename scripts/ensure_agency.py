#!/usr/bin/env python3
"""
Substrate agency bootstrap — idempotent self-healing of the full automation
stack. Designed to run from the substrate-agent-timer.service every 5 minutes
(and manually on boot), so ANY down service is repaired automatically without
operator intervention.

Responsibilities:
  1. daemon-reload so unit file edits take effect
  2. enable + start every unit in the agency unit set
  3. restart any unit that is failed/activating (crash loop)
  4. verify the panel port (8090) is actually serving HTTP
  5. verify the Kilo remote process is alive
  6. ensure tailscale is up and `tailscale serve :10000 -> 127.0.0.1:8090`
     is configured (one-time sudo, then idempotent)
  7. write state/agency-status.json so the lister and operators can inspect it

Exit code is always 0 (best-effort, idempotent) so a partial failure never
marks the systemd timer as failed.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/ahron/codespace")
STATE_DIR = ROOT / "state"
STATUS_FILE = STATE_DIR / "agency-status.json"
PANEL_HOST = "127.0.0.1"
PANEL_PORT = 8090
TAILSCALE_HTTPS_PORT = 10000
TTYD_PORT = 8765

# (unit, required)
# openclaw-gateway is the primary UI on 8090; substrate-panel.service is
# intentionally excluded to avoid port conflicts.
# Note: substrate-agent-timer.timer is managed by OpenClaw cron jobs, not
# systemd, to avoid duplicate scheduling.
UNITS: list[tuple[str, bool]] = [
    ("kilo-remote.service", True),
    ("kilo-proxy.service", True),
    ("openclaw-gateway.service", True),
    ("substrate-lister.service", True),
    ("substrate-chatbot.service", True),
    ("ttyd.service", True),
]

TAILSCALE_BIN = shutil.which("tailscale") or "/usr/bin/tailscale"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def log(msg: str) -> None:
    line = f"[{utc_now()}] {msg}"
    print(line, flush=True)


def _is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(path: str = "/health", timeout: int = 4) -> tuple[bool, str]:
    url = f"http://{PANEL_HOST}:{PANEL_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return resp.status == 200, f"{resp.status} {url}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def ensure_systemd() -> dict[str, Any]:
    """Reload the user daemon and ensure every unit is enabled + running."""
    out: dict[str, Any] = {"daemon_reloaded": False, "units": {}}

    reloaded = run(["systemctl", "--user", "daemon-reload"])
    out["daemon_reloaded"] = reloaded.returncode == 0
    if not out["daemon_reloaded"]:
        out["daemon_reload_error"] = reloaded.stderr.strip()

    for unit, required in UNITS:
        entry: dict[str, Any] = {"required": required, "action": None, "ok": False}

        # Enable first (idempotent).
        run(["systemctl", "--user", "enable", unit])

        active = run(["systemctl", "--user", "is-active", unit])
        state = active.stdout.strip()
        entry["state"] = state

        if state == "active":
            entry["ok"] = True
        elif state in {"failed", "activating", "deactivating"}:
            # Crash loop / stuck — force restart.
            restart = run(["systemctl", "--user", "restart", unit])
            entry["action"] = "restart"
            if restart.returncode == 0:
                time.sleep(2)
                again = run(["systemctl", "--user", "is-active", unit])
                entry["state"] = again.stdout.strip()
                entry["ok"] = again.stdout.strip() == "active"
            else:
                entry["error"] = restart.stderr.strip()
        else:
            # inactive / dead / not-found — start it.
            start = run(["systemctl", "--user", "start", unit])
            entry["action"] = "start"
            if start.returncode == 0:
                time.sleep(2)
                again = run(["systemctl", "--user", "is-active", unit])
                entry["state"] = again.stdout.strip()
                entry["ok"] = again.stdout.strip() == "active"
            else:
                entry["error"] = start.stderr.strip()

        out["units"][unit] = entry

    return out


def ensure_tailscale_serve() -> dict[str, Any]:
    """Make sure tailscale is up and serves :10000 -> 127.0.0.1:8090."""
    out: dict[str, Any] = {"ok": False, "tailscale_up": False}

    if not Path(TAILSCALE_BIN).exists():
        out["error"] = f"tailscale binary missing: {TAILSCALE_BIN}"
        return out

    status = run([TAILSCALE_BIN, "status", "--json"], timeout=15)
    if status.returncode == 0:
        out["tailscale_up"] = True
        try:
            data = json.loads(status.stdout)
            self_node = data.get("SelfNode") or {}
            out["tailscale_ip"] = (self_node.get("Addresses") or [""])[0]
            out["hostname"] = self_node.get("HostName")
        except json.JSONDecodeError:
            pass
    else:
        # Try to bring tailscale up (may need auth; keep the browser auth flow).
        up = run(["tailscale", "up"], timeout=30)
        out["up_attempt"] = up.returncode
        out["up_error"] = up.stderr.strip() or up.stdout.strip()

    # Configure serve (idempotent; tailscale serve replaces existing config).
    serve_cmd = [
        TAILSCALE_BIN,
        "serve",
        "--bg",
        f"--https={TAILSCALE_HTTPS_PORT}",
        f"http://{PANEL_HOST}:{PANEL_PORT}",
    ]
    served = run(["sudo", "-n", *serve_cmd], timeout=30)
    if served.returncode != 0:
        # No passwordless sudo — try direct (works if tailscale is root-owned group access)
        served = run(serve_cmd, timeout=30)
    out["serve_configured"] = served.returncode == 0
    if not out["serve_configured"]:
        out["serve_error"] = served.stderr.strip() or served.stdout.strip()
        out["serve_command"] = "sudo " + " ".join(serve_cmd)

    # ttyd over HTTPS: the control-panel Terminal page embeds ttyd in an
    # iframe. When the panel is served via Tailscale HTTPS (:10000), a plain
    # http://127.0.0.1:8765 iframe is blocked as mixed content, so ttyd gets
    # its own Tailscale HTTPS mapping on :8765.
    ttyd_serve_cmd = [
        TAILSCALE_BIN,
        "serve",
        "--bg",
        f"--https={TTYD_PORT}",
        f"http://{PANEL_HOST}:{TTYD_PORT}",
    ]
    ttyd_served = run(["sudo", "-n", *ttyd_serve_cmd], timeout=30)
    if ttyd_served.returncode != 0:
        ttyd_served = run(ttyd_serve_cmd, timeout=30)
    out["ttyd_serve_configured"] = ttyd_served.returncode == 0
    if not out["ttyd_serve_configured"]:
        out["ttyd_serve_error"] = ttyd_served.stderr.strip() or ttyd_served.stdout.strip()

    # Verify: tailscale serve status should show the mapping.
    check = run([TAILSCALE_BIN, "serve", "status"], timeout=15)
    if check.returncode == 0:
        out["serve_status"] = check.stdout.strip()
        out["ok"] = f"http://127.0.0.1:{PANEL_PORT}" in check.stdout.replace(
            "http://", "http://"
        )
    else:
        out["serve_status_error"] = check.stderr.strip()

    return out


def ensure_kilo_remote() -> dict[str, Any]:
    """Confirm the Kilo remote process is alive via the unit + process scan."""
    out: dict[str, Any] = {"ok": False}
    active = run(["systemctl", "--user", "is-active", "kilo-remote.service"])
    out["unit_state"] = active.stdout.strip()
    if active.stdout.strip() != "active":
        return out
    # Any node process running the kilo CLI remote subcommand counts as alive.
    proc = run(["pgrep", "-af", "kilo.*remote"], timeout=10)
    out["processes"] = proc.stdout.strip().splitlines()
    out["ok"] = bool(out["processes"])
    return out


def main() -> int:
    report: dict[str, Any] = {
        "generated_at": utc_now(),
        "host": os.uname().nodename,
        "systemd": {},
        "tailscale": {},
        "kilo_remote": {},
        "panel_http": {},
        "panel_port_open": False,
    }

    log("Agency bootstrap: repairing systemd units")
    report["systemd"] = ensure_systemd()

    log("Agency bootstrap: checking panel HTTP")
    report["panel_port_open"] = _is_port_open(PANEL_HOST, PANEL_PORT)
    ok, detail = _http_ok()
    report["panel_http"] = {"ok": ok, "detail": detail}

    log("Agency bootstrap: checking kilo remote")
    report["kilo_remote"] = ensure_kilo_remote()

    log("Agency bootstrap: checking tailscale serve")
    report["tailscale"] = ensure_tailscale_serve()

    # Aggregate health.
    unit_ok = all(u["ok"] for u in report["systemd"].get("units", {}).values())
    report["healthy"] = (
        unit_ok
        and report["panel_http"].get("ok", False)
        and report["kilo_remote"].get("ok", False)
    )
    report["tailscale_ok"] = report["tailscale"].get("ok", False)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    log(f"Agency bootstrap: healthy={report['healthy']} tailscale_ok={report['tailscale_ok']}")

    # Always exit 0: the systemd timer must never be marked failed by this.
    return 0


if __name__ == "__main__":
    sys.exit(main())
