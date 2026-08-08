"""Persistent state for the WhatsApp gateway plugin.

Credentials and webhook activity are stored under ``state/`` (gitignored) so
the control panel can configure the plugin without editing workspace.yaml and
so webhook events can be audited after the fact.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

CONFIG_KEYS = (
    "phone_number_id",
    "access_token",
    "app_secret",
    "verify_token",
    "webhook_url",
    "graph_api_version",
)

# Keys never returned to the browser.
SECRET_KEYS = {"access_token", "app_secret"}


def config_path(root: Path) -> Path:
    return root / "state" / "gateway-whatsapp.json"


def log_path(root: Path) -> Path:
    return root / "state" / "gateway-whatsapp.log"


def load_config(root: Path) -> dict[str, Any]:
    path = config_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in CONFIG_KEYS if key in payload}


def save_config(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Persist a validated plugin config. Returns the stored config."""
    path = config_path(root)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = dict(config)
        path.write_text(
            json.dumps(stored, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    append_log(root, "config", f"configuration saved (phone {config.get('phone_number_id', '?')})")
    return stored


def public_config(root: Path) -> dict[str, Any]:
    """Config with secrets masked, safe to return to the browser."""
    config = load_config(root)
    return {
        **config,
        "access_token": bool(config.get("access_token")),
        "app_secret": bool(config.get("app_secret")),
    }


def append_log(root: Path, event: str, detail: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{ts}  [{event}]  {detail}\n"
    with _LOCK:
        path = log_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass


def tail_log(root: Path, limit: int = 200) -> str:
    path = log_path(root)
    if not path.exists():
        return "(no gateway events recorded yet)"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(log unavailable)"
    return "\n".join(lines[-limit:]) or "(log empty)"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
