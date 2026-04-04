from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _scripts_root() -> Path:
    return _repo_root() / "scripts" / "windows"


def _run_powershell_script(script_name: str, args: list[str] | None = None, timeout_seconds: int = 180) -> dict:
    if os.name != "nt":
        return {"ok": False, "message": "Windows integration is only available on Windows hosts.", "code": None}

    script_path = _scripts_root() / script_name
    if not script_path.exists():
        return {"ok": False, "message": f"Script not found: {script_path}", "code": None}

    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-RepoRoot",
        str(_repo_root()),
    ]
    if args:
        command.extend(args)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "Windows integration command timed out.", "code": 124}

    output = "\n".join([(completed.stdout or "").strip(), (completed.stderr or "").strip()]).strip()
    if completed.returncode != 0:
        return {
            "ok": False,
            "message": output or f"Windows integration command failed with exit code {completed.returncode}.",
            "code": completed.returncode,
        }
    return {
        "ok": True,
        "message": output or "Success",
        "code": completed.returncode,
    }


def windows_app_mode_install() -> dict:
    return _run_powershell_script("Install-WindowsAppMode.ps1")


def windows_app_mode_uninstall() -> dict:
    return _run_powershell_script("Install-WindowsAppMode.ps1", ["-Uninstall"])


def windows_host_start() -> dict:
    return _run_powershell_script("Start-CodexSchedulerHost.ps1")


def windows_host_stop() -> dict:
    return _run_powershell_script("Stop-CodexSchedulerHost.ps1")
