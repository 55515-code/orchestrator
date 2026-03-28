#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


_COMMAND_TIMEOUT_SECONDS = 8


def run_text(command: list[str], *, timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(1, int(timeout_seconds)),
        )
    except subprocess.TimeoutExpired:
        return f"timeout({max(1, int(timeout_seconds))}s)"
    except OSError as exc:
        return f"unavailable: {exc}"
    output = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 and output:
        return f"error({completed.returncode}): {output}"
    return output or "ok"


def _format_bytes(value: int) -> str:
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    for suffix in suffixes:
        if amount < 1024 or suffix == suffixes[-1]:
            return f"{amount:.1f}{suffix}"
        amount /= 1024
    return f"{value}B"


def write_probe(out_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    disk = shutil.disk_usage(Path.cwd())
    host = socket.gethostname()
    user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    os_release = platform.platform()
    python_version = platform.python_version()
    machine = platform.machine()
    processor = platform.processor()
    cpu_count = os.cpu_count() or 0

    network_info = (
        run_text(["ip", "-brief", "addr"])
        if os.name != "nt"
        else run_text(["ipconfig"])
    )
    tooling = []
    for tool in ["git", "rg", "uv", "mise", "direnv", "just", "node", "pnpm", "python"]:
        path = shutil.which(tool)
        if path is None:
            tooling.append(f"{tool:12}missing")
        else:
            version = run_text([tool, "--version"]).splitlines()[0]
            tooling.append(f"{tool:12}{version}")

    content = "\n".join(
        [
            "# System Probe",
            "",
            f"- Generated (UTC): {timestamp}",
            f"- Host: {host}",
            f"- User: {user}",
            f"- Working directory: {Path.cwd()}",
            "",
            "## OS and Runtime",
            "```text",
            f"OS: {os_release}",
            f"Machine: {machine}",
            f"Processor: {processor}",
            f"Python: {python_version}",
            "```",
            "",
            "## CPU and Disk",
            "```text",
            f"CPU count: {cpu_count}",
            f"Disk total: {_format_bytes(disk.total)}",
            f"Disk used: {_format_bytes(disk.used)}",
            f"Disk free: {_format_bytes(disk.free)}",
            "```",
            "",
            "## Network",
            "```text",
            network_info[:4000],
            "```",
            "",
            "## Core Tooling Snapshot",
            "```text",
            *tooling,
            "```",
            "",
        ]
    )
    out_file.write_text(content, encoding="utf-8")


def main() -> int:
    out_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/system-probe.md")
    write_probe(out_file)
    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
