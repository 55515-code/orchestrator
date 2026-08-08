"""iPhone webapp extensions for the Substrate Control Panel.

Adds three additive surfaces to the existing substrate/web.py:

1. ``GET  /api/automations``        — list available actions from actions.json
2. ``POST /api/automations/{name}``  — run an action by name, return JSON
3. ``GET  /api/iphone/system/stream`` — SSE stream of live system metrics (CPU,
   memory, disk, Tailscale status, Kilo service status). Server-rendered HTML
   fragments so they can be dropped straight into HTMX targets.

The endpoints are pure additions. They do not modify any existing route in
substrate/web.py. The page additions for the control panel are in
substrate/templates/iphone-panel-pages.html, mounted by the existing
control-panel.html.

Run as a user service on 127.0.0.1:8090; Tailscale Serve exposes the
:10000 HTTPS endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - only when psutil missing
    psutil = None  # type: ignore[assignment]

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

ACTIONS_FILE = Path(os.environ.get("SUBSTRATE_AUTOMATION_FILE", "/home/ahron/codespace/automation/actions.json"))
WRAPPER = Path(os.environ.get("SUBSTRATE_AUTOMATION_WRAPPER", "/home/ahron/codespace/automation/run.sh"))
TAILSCALE_BIN = shutil.which("tailscale") or "/usr/bin/tailscale"
KILO_BIN = shutil.which("kilo") or "/home/ahron/.npm-global/bin/kilo"

router = APIRouter(prefix="/api/iphone", tags=["iphone-panel"])


def _read_actions() -> dict[str, Any]:
    if not ACTIONS_FILE.exists():
        return {"actions": {}}
    try:
        return json.loads(ACTIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"actions": {}}


@router.get("/automations")
async def list_automations() -> dict[str, Any]:
    """Return the action library as JSON."""
    data = _read_actions()
    actions = data.get("actions", {})
    out: list[dict[str, Any]] = []
    for name, body in actions.items():
        out.append(
            {
                "name": name,
                "description": body.get("description", ""),
                "cwd": body.get("cwd", ""),
                "command": body.get("command", ""),
                "takes_input": "%PROMPT%" in body.get("command", ""),
            }
        )
    out.sort(key=lambda r: r["name"])
    return {"count": len(out), "actions": out}


@router.post("/automations/{name}")
async def run_automation(name: str, request: Request) -> dict[str, Any]:
    """Run an action by name. For agent_session, pass a JSON body {"prompt": "..."}."""
    data = _read_actions()
    actions = data.get("actions", {})
    if name not in actions:
        raise HTTPException(status_code=404, detail=f"unknown action: {name}")

    body = actions[name]
    cmd = body.get("command", "")
    cwd = body.get("cwd", "")

    prompt = ""
    if "%PROMPT%" in cmd:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="agent_session requires {\"prompt\": \"...\"}")

    if not WRAPPER.exists():
        raise HTTPException(status_code=500, detail=f"wrapper missing: {WRAPPER}")

    # Delegate to run.sh for every action: it substitutes %PROMPT% as a positional
    # argument to bash -c, so the prompt can never be interpreted as shell code.
    shell_cmd = f"{WRAPPER} {name}"
    if prompt:
        shell_cmd += f" {prompt!r}"

    if cwd and cwd != ".":
        shell_cmd = f"cd {cwd!r} && {shell_cmd}"

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        completed = subprocess.run(
            ["bash", "-lc", shell_cmd],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        rc = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        error = None
    except subprocess.TimeoutExpired:
        rc, stdout, stderr, error = -1, "", "", "timeout after 300s"
    except Exception as exc:  # noqa: BLE001
        rc, stdout, stderr, error = -1, "", "", str(exc)

    return {
        "ok": rc == 0 and error is None,
        "action": name,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "returncode": rc,
        "stdout": stdout[-8000:],
        "stderr": stderr[-4000:],
        "error": error,
        "prompt": prompt or None,
    }


# ---------- Live system SSE stream ----------


def _gather_system_snapshot() -> dict[str, Any]:
    snap: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if psutil is not None:
        snap["cpu_percent"] = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        snap["mem_percent"] = mem.percent
        snap["mem_used_gb"] = round(mem.used / 1024**3, 1)
        snap["mem_total_gb"] = round(mem.total / 1024**3, 1)
        disk = psutil.disk_usage("/home")
        snap["disk_percent"] = disk.percent
        snap["disk_used_gb"] = round(disk.used / 1024**3, 1)
        snap["disk_total_gb"] = round(disk.total / 1024**3, 1)
    else:
        snap["cpu_percent"] = None
        snap["mem_percent"] = None
        snap["disk_percent"] = None

    # Tailscale self-info
    try:
        out = subprocess.run(
            [TAILSCALE_BIN, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        if out.returncode == 0:
            d = json.loads(out.stdout)
            self_node = d.get("SelfNode", {}) or {}
            snap["tailscale"] = {
                "ip": (self_node.get("Addresses") or [""])[0],
                "hostname": self_node.get("HostName", "?"),
                "online": self_node.get("Online", False),
            }
        else:
            snap["tailscale"] = {"error": "tailscale status failed"}
    except Exception as exc:  # noqa: BLE001
        snap["tailscale"] = {"error": str(exc)}

    # Kilo service status
    snap["services"] = {}
    for name in ("kilo-remote.service", "kilo-acp.service", "substrate-panel.service", "ttyd.service"):
        try:
            out = subprocess.run(
                ["systemctl", "--user", "is-active", name],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            snap["services"][name] = out.stdout.strip() or "unknown"
        except Exception:  # noqa: BLE001
            snap["services"][name] = "error"

    return snap


def _snapshot_to_html(snap: dict[str, Any]) -> str:
    """Render the snapshot as an HTML fragment suitable for hx-swap."""
    def fmt_bar(percent: float | None) -> str:
        if percent is None:
            return '<span class="metric-empty">n/a</span>'
        pct = max(0, min(100, float(percent)))
        cls = "metric-bar__fill"
        if pct >= 85:
            cls += " metric-bar__fill--warn"
        if pct >= 95:
            cls += " metric-bar__fill--crit"
        return (
            f'<div class="metric-bar"><div class="{cls}" style="width:{pct:.0f}%"></div>'
            f'<span class="metric-bar__label">{pct:.0f}%</span></div>'
        )

    ts_html = '<span class="muted">' + (snap.get("ts") or "")[:19] + '</span>'
    cpu = fmt_bar(snap.get("cpu_percent"))
    mem = fmt_bar(snap.get("mem_percent"))
    if snap.get("mem_used_gb") is not None:
        mem = (
            f'<div class="metric-line">{fmt_bar(snap.get("mem_percent"))}'
            f'<span class="metric-detail">{snap["mem_used_gb"]:.1f} / {snap["mem_total_gb"]:.1f} GB</span></div>'
        )
    disk = (
        f'<div class="metric-line">{fmt_bar(snap.get("disk_percent"))}'
        f'<span class="metric-detail">{snap.get("disk_used_gb", "?")} / {snap.get("disk_total_gb", "?")} GB</span></div>'
    )

    ts_data = snap.get("tailscale") or {}
    if "error" in ts_data:
        ts_block = f'<span class="muted">tailscale: {ts_data["error"]}</span>'
    else:
        ts_block = (
            f'<strong>{ts_data.get("hostname", "?")}</strong> '
            f'<span class="muted">@</span> {ts_data.get("ip", "?")} '
            f'<span class="pill {("pill--ok" if ts_data.get("online") else "pill--off")}">'
            f'{"online" if ts_data.get("online") else "offline"}</span>'
        )

    services = snap.get("services") or {}
    svc_rows = []
    for name, state in services.items():
        cls = "pill"
        if state == "active":
            cls += " pill--ok"
        elif state == "inactive" or state == "dead":
            cls += " pill--off"
        else:
            cls += " pill--warn"
        svc_rows.append(
            f'<div class="svc-row"><span class="svc-name">{name}</span>'
            f'<span class="{cls}">{state}</span></div>'
        )

    return (
        f'<div class="snapshot" data-snapshot-ts="{snap.get("ts", "")}">'
        f'  <div class="snapshot-ts">{ts_html}</div>'
        f'  <div class="metric"><h4>CPU</h4>{cpu}</div>'
        f'  <div class="metric"><h4>Memory</h4>{mem}</div>'
        f'  <div class="metric"><h4>Disk (home)</h4>{disk}</div>'
        f'  <div class="metric metric--wide"><h4>Tailscale</h4>{ts_block}</div>'
        f'  <div class="metric metric--wide"><h4>Services</h4>'
        f'    <div class="svc-list">{"".join(svc_rows)}</div>'
        f'  </div>'
        f'</div>'
    )


@router.get("/system/snapshot")
async def system_snapshot() -> dict[str, Any]:
    """Return the current system snapshot as JSON (for charts and probes)."""
    return _gather_system_snapshot()


@router.get("/system/stream")
async def system_stream(request: Request):
    """SSE stream of system metrics, one event every 2s."""

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                snap = await asyncio.to_thread(_gather_system_snapshot)
                html = _snapshot_to_html(snap)
                yield f"event: system_snapshot\ndata: {html}\n\n"
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
