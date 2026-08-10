"""Configuration for the substrate desktop chatbot."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8321
DEFAULT_WORKSPACE = str(Path.home() / "codespace")
CONFIG_ENV = "SUBSTRATE_CHATBOT_CONFIG"

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kilo" / "chatbot.json"


def _default_kilo_binary() -> str:
    for candidate in ("kilo", "kilo-cli"):
        from shutil import which

        resolved = which(candidate)
        if resolved:
            return candidate
    return "kilo"


@dataclass(slots=True)
class ChatbotConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    workspace: str = DEFAULT_WORKSPACE
    kilo_binary: str = field(default_factory=_default_kilo_binary)
    agent: str | None = None
    model: str | None = None
    kilo_config: str | None = None
    task_timeout_seconds: int = 900
    max_session_messages: int = 200
    keep_sessions: int = 50
    prefill_proxy_enabled: bool = True
    prefill_proxy_port: int = 8477

    @classmethod
    def load(cls, path: Path | None = None) -> ChatbotConfig:
        config_path = path or _config_path()
        raw: dict[str, Any] = {}
        if config_path.exists():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8") or "{}")
                if isinstance(payload, dict):
                    raw = payload
            except json.JSONDecodeError:
                raw = {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChatbotConfig:
        known = {
            "host",
            "port",
            "workspace",
            "kilo_binary",
            "agent",
            "model",
            "kilo_config",
            "task_timeout_seconds",
            "max_session_messages",
            "keep_sessions",
            "prefill_proxy_enabled",
            "prefill_proxy_port",
        }
        filtered = {key: value for key, value in raw.items() if key in known}
        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "workspace": self.workspace,
            "kilo_binary": self.kilo_binary,
            "agent": self.agent,
            "model": self.model,
            "kilo_config": self.kilo_config,
            "task_timeout_seconds": self.task_timeout_seconds,
            "max_session_messages": self.max_session_messages,
            "keep_sessions": self.keep_sessions,
            "prefill_proxy_enabled": self.prefill_proxy_enabled,
            "prefill_proxy_port": self.prefill_proxy_port,
        }


def _config_path() -> Path:
    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_CONFIG_PATH


def workspace_root() -> Path:
    """Resolve the chatbot workspace to an absolute path (defaults to ~/codespace)."""
    cfg = ChatbotConfig.load()
    return Path(cfg.workspace).expanduser().resolve()


def state_dir() -> Path:
    return workspace_root() / "state" / "chatbot"
