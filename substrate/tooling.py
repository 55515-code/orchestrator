from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from .registry import SubstrateRuntime

DEFAULT_TOOL_PROFILES_FILE = "tool_profiles.yaml"
MANAGER_BINARIES = {
    "uv_tool": "uv",
    "pipx": "pipx",
    "brew": "brew",
    "apt": "apt-get",
    "dnf": "dnf",
    "pacman": "pacman",
    "winget": "winget",
    "choco": "choco",
    "scoop": "scoop",
    "manual": None,
}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must be a YAML mapping.")
    return payload


def _ensure_list(payload: Any, field: str) -> list[Any]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError(f"{field} must be a list.")
    return payload


def _manager_availability() -> dict[str, bool]:
    availability: dict[str, bool] = {}
    for manager, binary in MANAGER_BINARIES.items():
        if binary is None:
            availability[manager] = True
            continue
        availability[manager] = shutil.which(binary) is not None
    return availability


def _normalize_install_map(raw_install: Any, *, tool_id: str) -> dict[str, list[str]]:
    if raw_install is None:
        return {}
    if not isinstance(raw_install, dict):
        raise ValueError(f"tools[{tool_id}].install must be a mapping.")
    normalized: dict[str, list[str]] = {}
    for key, value in raw_install.items():
        manager = str(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(
                f"tools[{tool_id}].install[{manager}] must be a list of strings."
            )
        normalized[manager] = list(value)
    return normalized


def _preferred_manager(
    install_map: dict[str, list[str]],
    *,
    manager_priority: list[str],
    manager_availability: dict[str, bool],
) -> tuple[str | None, list[str]]:
    for manager in manager_priority:
        if manager not in install_map:
            continue
        if manager != "manual" and not manager_availability.get(manager, False):
            continue
        return manager, list(install_map.get(manager, []))
    if "manual" in install_map:
        return "manual", list(install_map["manual"])
    return None, []


def _normalize_profiles(root: Path) -> dict[str, Any]:
    source = _load_yaml(root / DEFAULT_TOOL_PROFILES_FILE)
    manager_priority_raw = _ensure_list(
        source.get("manager_priority"), "manager_priority"
    )
    manager_priority = [str(item) for item in manager_priority_raw] or list(
        MANAGER_BINARIES.keys()
    )

    profiles: list[dict[str, Any]] = []
    for raw_profile in _ensure_list(source.get("profiles"), "profiles"):
        if not isinstance(raw_profile, dict):
            raise ValueError("profiles items must be mappings.")
        profile_id = str(raw_profile.get("id") or "").strip()
        if not profile_id:
            raise ValueError("profile id is required.")
        tools: list[dict[str, Any]] = []
        for raw_tool in _ensure_list(
            raw_profile.get("tools"), f"profiles[{profile_id}].tools"
        ):
            if not isinstance(raw_tool, dict):
                raise ValueError(
                    f"profiles[{profile_id}].tools items must be mappings."
                )
            tool_id = str(raw_tool.get("id") or "").strip()
            if not tool_id:
                raise ValueError(f"profiles[{profile_id}] has a tool without id.")
            tools.append(
                {
                    "id": tool_id,
                    "name": str(raw_tool.get("name") or tool_id),
                    "binary": str(raw_tool.get("binary") or tool_id),
                    "source_url": str(raw_tool.get("source_url") or ""),
                    "install": _normalize_install_map(
                        raw_tool.get("install"), tool_id=tool_id
                    ),
                }
            )
        profiles.append(
            {
                "id": profile_id,
                "name": str(raw_profile.get("name") or profile_id),
                "description": str(raw_profile.get("description") or ""),
                "tools": tools,
            }
        )
    return {
        "version": int(source.get("version") or 1),
        "manager_priority": manager_priority,
        "profiles": profiles,
    }


def tooling_snapshot(
    runtime: SubstrateRuntime, profile_id: str | None = None
) -> dict[str, Any]:
    catalog = _normalize_profiles(runtime.root)
    manager_availability = _manager_availability()
    available_managers = [
        manager
        for manager in catalog["manager_priority"]
        if manager_availability.get(manager, False)
    ]

    profiles: list[dict[str, Any]] = []
    for raw_profile in catalog["profiles"]:
        if profile_id and raw_profile["id"] != profile_id:
            continue
        tools: list[dict[str, Any]] = []
        missing_count = 0
        for raw_tool in raw_profile["tools"]:
            binary_path = shutil.which(raw_tool["binary"])
            installed = binary_path is not None
            if not installed:
                missing_count += 1
            manager, install_commands = _preferred_manager(
                raw_tool["install"],
                manager_priority=catalog["manager_priority"],
                manager_availability=manager_availability,
            )
            tools.append(
                {
                    "id": raw_tool["id"],
                    "name": raw_tool["name"],
                    "binary": raw_tool["binary"],
                    "installed": installed,
                    "path": binary_path,
                    "source_url": raw_tool["source_url"],
                    "install_manager": manager,
                    "install_commands": install_commands,
                }
            )
        profiles.append(
            {
                "id": raw_profile["id"],
                "name": raw_profile["name"],
                "description": raw_profile["description"],
                "tools_total": len(tools),
                "missing_tools": missing_count,
                "tools": tools,
                "ensure_hint": (
                    f"uv run python scripts/substrate_cli.py deps-ensure --profile {raw_profile['id']} --apply"
                ),
            }
        )

    return {
        "version": catalog["version"],
        "available_managers": available_managers,
        "profiles": profiles,
    }


def ensure_tool_profile(
    runtime: SubstrateRuntime,
    *,
    profile_id: str,
    apply: bool = False,
) -> dict[str, Any]:
    snapshot = tooling_snapshot(runtime, profile_id=profile_id)
    if not snapshot["profiles"]:
        raise KeyError(f"Unknown tool profile: {profile_id}")
    profile = snapshot["profiles"][0]
    actions: list[dict[str, Any]] = []
    for tool in profile["tools"]:
        if tool["installed"]:
            actions.append(
                {
                    "tool_id": tool["id"],
                    "status": "already_installed",
                    "binary": tool["binary"],
                    "path": tool["path"],
                    "commands": [],
                }
            )
            continue

        commands = list(tool["install_commands"])
        if not commands:
            actions.append(
                {
                    "tool_id": tool["id"],
                    "status": "no_install_plan",
                    "binary": tool["binary"],
                    "commands": [],
                }
            )
            continue

        if not apply:
            actions.append(
                {
                    "tool_id": tool["id"],
                    "status": "planned",
                    "binary": tool["binary"],
                    "install_manager": tool["install_manager"],
                    "commands": commands,
                }
            )
            continue

        command_results: list[dict[str, Any]] = []
        command_failed = False
        for command in commands:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
            )
            command_results.append(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-1200:],
                    "stderr": completed.stderr[-1200:],
                }
            )
            if completed.returncode != 0:
                command_failed = True
                break

        refreshed_path = shutil.which(tool["binary"])
        actions.append(
            {
                "tool_id": tool["id"],
                "status": (
                    "installed"
                    if (not command_failed and refreshed_path is not None)
                    else "failed"
                ),
                "binary": tool["binary"],
                "path": refreshed_path,
                "install_manager": tool["install_manager"],
                "commands": commands,
                "results": command_results,
            }
        )

    installed_now = sum(
        1
        for action in actions
        if action["status"] in {"installed", "already_installed"}
    )
    return {
        "profile_id": profile["id"],
        "profile_name": profile["name"],
        "apply": apply,
        "available_managers": snapshot["available_managers"],
        "actions": actions,
        "installed_count": installed_now,
        "tool_count": len(profile["tools"]),
    }
