from __future__ import annotations

import os
import platform
import shutil
import socket
from pathlib import Path

from .models import EnvironmentProfile


def detect_environment(cwd: Path) -> EnvironmentProfile:
    os_name = platform.system().lower()
    tags: list[str] = []
    if os_name == "darwin":
        tags.append("macos")
    if os_name == "windows":
        tags.append("windows")
    if os_name == "linux":
        tags.append("linux")
    if not tags:
        tags.append(os_name)

    is_ci = bool(os.getenv("CI"))
    is_codespaces = bool(os.getenv("CODESPACES"))
    is_github_actions = bool(os.getenv("GITHUB_ACTIONS"))
    is_wsl = "microsoft" in platform.release().lower()

    if is_ci:
        tags.append("ci")
    if is_codespaces:
        tags.append("codespaces")
    if is_github_actions:
        tags.append("github-actions")
    if is_wsl:
        tags.append("wsl")

    return EnvironmentProfile(
        os_name=os_name,
        os_release=platform.release(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        user=os.getenv("USER") or os.getenv("USERNAME") or "unknown",
        hostname=socket.gethostname(),
        cwd=str(cwd),
        shell=os.getenv("SHELL") or os.getenv("COMSPEC") or "",
        is_ci=is_ci,
        is_codespaces=is_codespaces,
        is_github_actions=is_github_actions,
        is_wsl=is_wsl,
        git_available=shutil.which("git") is not None,
        tags=tags,
    )


def platform_key() -> str:
    os_name = platform.system().lower()
    if os_name.startswith("win"):
        return "windows"
    if os_name == "darwin":
        return "darwin"
    return "linux"
