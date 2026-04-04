from __future__ import annotations

import json
import os
import socket
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


APP_NAME = "CodexSchedulerStudio"
DEFAULT_VERSION = "0.1.0-rc1"
VALID_CHANNELS = {"dev", "test", "stable"}


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local_appdata_root() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata)
    return Path.home() / "AppData" / "Local"


def default_desktop_data_dir(channel: str) -> Path:
    return _local_appdata_root() / APP_NAME / channel


def choose_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def detect_runtime_root(project_root: Path) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return project_root


def detect_bundled_codex_executable(runtime_root: Path) -> str | None:
    candidates = [
        runtime_root / "runtime" / "codex.cmd",
        runtime_root / "runtime" / "codex.exe",
        runtime_root / "runtime" / "codex",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass(slots=True)
class RuntimeOptions:
    mode: str = "server"
    channel: str = "stable"
    host: str = "127.0.0.1"
    port: int = 8787
    data_dir: Path | None = None
    session_token: str | None = None
    bundled_codex_executable: str | None = None
    update_base_url: str | None = None
    version: str = DEFAULT_VERSION

    @property
    def desktop_mode(self) -> bool:
        return self.mode == "desktop"

    def resolved_data_dir(self, project_root: Path) -> Path:
        if self.data_dir:
            return self.data_dir
        if self.desktop_mode:
            return default_desktop_data_dir(self.channel)
        return project_root

    def runtime_dir(self, project_root: Path) -> Path:
        return self.resolved_data_dir(project_root) / "runtime" if self.desktop_mode else project_root / "runtime"

    def run_root(self, project_root: Path) -> Path:
        return self.resolved_data_dir(project_root) / "runs" if self.desktop_mode else project_root / "runs"

    def codex_home_dir(self, project_root: Path) -> Path:
        return self.resolved_data_dir(project_root) / "codex-home" if self.desktop_mode else project_root / ".codex"

    def logs_dir(self, project_root: Path) -> Path:
        return self.resolved_data_dir(project_root) / "logs" if self.desktop_mode else project_root / "logs"

    def default_db_url(self, project_root: Path) -> str:
        if self.desktop_mode:
            return f"sqlite:///{self.resolved_data_dir(project_root) / 'codex_scheduler.db'}"
        return f"sqlite:///{project_root / 'codex_scheduler.db'}"

    def desktop_state_path(self, project_root: Path) -> Path:
        return self.runtime_dir(project_root) / "desktop-state.json"

    def update_status_path(self, project_root: Path) -> Path:
        return self.runtime_dir(project_root) / "update-status.json"

    def restart_request_path(self, project_root: Path) -> Path:
        return self.runtime_dir(project_root) / "restart-request.json"

    def ensure_directories(self, project_root: Path) -> None:
        for path in [
            self.resolved_data_dir(project_root),
            self.runtime_dir(project_root),
            self.run_root(project_root),
            self.codex_home_dir(project_root),
            self.logs_dir(project_root),
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def write_desktop_state(self, project_root: Path, *, healthy: bool) -> None:
        if not self.desktop_mode:
            return
        payload = {
            "port": self.port,
            "pid": os.getpid(),
            "channel": self.channel,
            "version": self.version,
            "started_at": utcnow_naive().isoformat(),
            "healthy": healthy,
        }
        write_json(self.desktop_state_path(project_root), payload)

    def queue_restart(self, project_root: Path) -> None:
        payload = {
            "requested_at": utcnow_naive().isoformat(),
            "pid": os.getpid(),
            "channel": self.channel,
        }
        write_json(self.restart_request_path(project_root), payload)


def normalize_channel(channel: str | None) -> str:
    normalized = (channel or "stable").strip().lower()
    if normalized not in VALID_CHANNELS:
        return "stable"
    return normalized
