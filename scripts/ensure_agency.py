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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path("/home/ahron/codespace")
STATE_DIR = ROOT / "state"
STATUS_FILE = STATE_DIR / "agency-status.json"
PANEL_HOST = "127.0.0.1"
PANEL_PORT = 8090
TAILSCALE_HTTPS_PORT = 10000
TTYD_PORT = 8765
GATEWAY_UNIT = "openclaw-gateway.service"
# Native gateway answers /health ({"ok":true}); the container image answers
# /healthz. Probe both so a hung-but-alive gateway is detected either way.
GATEWAY_HEALTH_PATHS = ("/health", "/healthz")
GATEWAY_RESTART_STATE = STATE_DIR / "gateway-restarts.json"
GATEWAY_MAX_RESTARTS = 5
GATEWAY_RESTART_WINDOW_SECONDS = 600

# (unit, required)
# openclaw-gateway is the primary UI on 8090; substrate-panel.service is
# intentionally excluded to avoid port conflicts.
# Note: substrate-agent-timer.timer is managed by OpenClaw cron jobs, not
# systemd, to avoid duplicate scheduling.
UNITS: list[tuple[str, bool]] = [
    ("kilo-remote.service", True),
    ("openclaw-gateway.service", True),
    ("substrate-lister.service", True),
    ("substrate-chatbot.service", True),
    ("ttyd.service", True),
]

TAILSCALE_BIN = shutil.which("tailscale") or "/usr/bin/tailscale"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


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
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200, f"{resp.status} {url}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _gateway_http_ok(timeout: int = 5) -> tuple[bool, str]:
    """Deep probe of the OpenClaw Gateway HTTP surface.

    A gateway whose unit is `active` but whose HTTP endpoint no longer answers
    is hung (wedged event loop / stale socket) and must be restarted. This is
    the failure mode a plain `is-active` + TCP-connect check misses.
    """
    for path in GATEWAY_HEALTH_PATHS:
        ok, detail = _http_ok(path, timeout=timeout)
        if ok:
            return True, detail
    return False, f"no gateway health path answered: {GATEWAY_HEALTH_PATHS}"


def _gateway_restart_allowed() -> bool:
    """Crash-loop breaker for gateway restarts triggered by this script."""
    now = time.time()
    try:
        data = json.loads(GATEWAY_RESTART_STATE.read_text())
    except (OSError, json.JSONDecodeError):
        data = []
    cutoff = now - GATEWAY_RESTART_WINDOW_SECONDS
    recent = [ts for ts in data if isinstance(ts, (int, float)) and ts >= cutoff]
    return len(recent) < GATEWAY_MAX_RESTARTS


def _gateway_record_restart() -> None:
    now = time.time()
    try:
        data = json.loads(GATEWAY_RESTART_STATE.read_text())
    except (OSError, json.JSONDecodeError):
        data = []
    cutoff = now - GATEWAY_RESTART_WINDOW_SECONDS
    recent = [ts for ts in data if isinstance(ts, (int, float)) and ts >= cutoff]
    recent.append(now)
    GATEWAY_RESTART_STATE.parent.mkdir(parents=True, exist_ok=True)
    GATEWAY_RESTART_STATE.write_text(json.dumps(recent))


def ensure_gateway_health() -> dict[str, Any]:
    """Restart the gateway when the unit is active but HTTP is not serving."""
    out: dict[str, Any] = {"ok": False, "action": None}

    ok, detail = _gateway_http_ok()
    out["http"] = {"ok": ok, "detail": detail}
    if ok:
        out["ok"] = True
        return out

    active = run(["systemctl", "--user", "is-active", GATEWAY_UNIT])
    out["unit_state"] = active.stdout.strip()

    if not _gateway_restart_allowed():
        out["error"] = (
            f"gateway restart limit reached ({GATEWAY_MAX_RESTARTS} in "
            f"{GATEWAY_RESTART_WINDOW_SECONDS}s); skipping restart"
        )
        return out

    log(f"Gateway unit is '{active.stdout.strip()}' but HTTP is down; restarting")
    restart = run(["systemctl", "--user", "restart", GATEWAY_UNIT])
    out["action"] = "restart"
    if restart.returncode != 0:
        out["error"] = restart.stderr.strip()
        return out

    _gateway_record_restart()
    time.sleep(4)
    ok, detail = _gateway_http_ok()
    out["http"] = {"ok": ok, "detail": detail}
    out["ok"] = ok
    return out


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
        "gateway_health": {},
        "tailscale": {},
        "kilo_remote": {},
        "panel_http": {},
        "panel_port_open": False,
    }

    log("Agency bootstrap: repairing systemd units")
    report["systemd"] = ensure_systemd()

    log("Agency bootstrap: deep-checking gateway HTTP health")
    report["gateway_health"] = ensure_gateway_health()

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
        and report["gateway_health"].get("ok", False)
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
