"""Persistent state for the WhatsApp gateway plugin.

Credentials and webhook activity are stored under ``state/`` (gitignored) so
the control panel can configure the plugin without editing workspace.yaml and
so webhook events can be audited after the fact.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..credentials import CredentialStore

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
SECRET_KEYS = {"access_token", "app_secret", "verify_token"}


def config_path(root: Path) -> Path:
    return root / "state" / "gateway-whatsapp.json"


def log_path(root: Path) -> Path:
    return root / "state" / "gateway-whatsapp.log"


def save_config(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Persist a validated plugin config. Returns the stored config.

    Security: secret keys (access_token, app_secret, verify_token) are
    NEVER written to the JSON state file.  They are routed to the OS
    keyring via CredentialStore (encrypted-file fallback) and the JSON
    holds only a ``secret_ref`` pointer like ``keyring:whatsapp:access_token``.
    """
    path = config_path(root)
    secret_keys = {"access_token", "app_secret", "verify_token"}
    to_keyring = {k: config[k] for k in secret_keys if k in config and config[k]}

    # Persist secrets to the keyring / encrypted file (never plaintext JSON).
    if to_keyring:
        store = CredentialStore(root)
        for key, value in to_keyring.items():
            store.set_token(f"whatsapp:{key}", value)

    # Non-secret fields plus opaque pointers for the secret fields.
    stored = {}
    for key in CONFIG_KEYS:
        if key in config:
            if key in secret_keys:
                if config[key]:
                    stored[key] = f"keyring:whatsapp:{key}"
            else:
                stored[key] = config[key]

    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(stored, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    append_log(root, "config", f"configuration saved (phone {config.get('phone_number_id', '?')})")
    return stored


def load_config(root: Path) -> dict[str, Any]:
    """Load config, resolving keyring pointers back to live secrets.

    Returns the fully-resolved config (secrets included) for server-side
    use.  Never call this for browser responses; use ``public_config``.
    """
    path = config_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}

    result = {key: payload[key] for key in CONFIG_KEYS if key in payload}

    # Resolve keyring pointers for secret fields.
    store = CredentialStore(root)
    for key in ("access_token", "app_secret", "verify_token"):
        value = result.get(key)
        if isinstance(value, str) and value.startswith("keyring:"):
            resolved = store.get_token(f"whatsapp:{key}")
            if resolved is not None:
                result[key] = resolved
            else:
                # Pointer exists but secret is gone: drop it so callers
                # fail closed rather than sending a stale pointer.
                result.pop(key, None)
    return result


def public_config(root: Path) -> dict[str, Any]:
    """Config with secrets masked, safe to return to the browser."""
    config = load_config(root)
    return {
        **{k: v for k, v in config.items() if k not in SECRET_KEYS},
        "access_token": bool(config.get("access_token")),
        "app_secret": bool(config.get("app_secret")),
        "verify_token": bool(config.get("verify_token")),
    }


def append_log(root: Path, event: str, detail: str) -> None:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
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
    return datetime.now(UTC).isoformat()
