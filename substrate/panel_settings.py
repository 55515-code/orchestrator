"""Panel preferences persisted under ``state/panel-settings.json``.

These are user-interface preferences (default provider, default mode, auto
discovery mirror) that the control panel pre-fills into its forms. They are
separate from ``workspace.yaml`` policy: the panel never mutates workspace
configuration directly; it only stores UI defaults the user chooses in the
Configuration page.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "default_mode": "observe",
    "default_provider": "mock",
    "auto_discovery": True,
    "default_stage": "local",
    "sidebar_collapsed": False,
}

_LOCK = threading.Lock()


def settings_path(root: Path) -> Path:
    return root / "state" / "panel-settings.json"


def load_panel_settings(root: Path) -> dict[str, Any]:
    """Load panel preferences, falling back to defaults for missing keys."""
    path = settings_path(root)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8") or "{}")
            if isinstance(payload, dict):
                raw = payload
        except (json.JSONDecodeError, OSError):
            raw = {}
    merged = dict(DEFAULT_SETTINGS)
    for key, value in raw.items():
        if key in DEFAULT_SETTINGS:
            merged[key] = value
    return merged


def save_panel_settings(root: Path, settings: dict[str, Any]) -> dict[str, Any]:
    """Persist panel preferences. Unknown keys are ignored."""
    current = load_panel_settings(root)
    for key in ("default_mode", "default_provider", "auto_discovery", "default_stage"):
        if key in settings:
            current[key] = settings[key]
    current["sidebar_collapsed"] = bool(settings.get("sidebar_collapsed", current.get("sidebar_collapsed", False)))
    path = settings_path(root)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return current
