from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from .registry import SubstrateRuntime

TargetEnv = Literal["linux", "mac", "windows"]
CONFIG_SYNC_TARGET_ENVS: tuple[TargetEnv, ...] = ("linux", "mac", "windows")
DOTFILE_TARGET_ENVS: tuple[TargetEnv, ...] = CONFIG_SYNC_TARGET_ENVS
LINE_ENDING_MODES = {"auto", "preserve", "lf", "crlf"}
CONVERSION_MODES = {"auto", "preserve", "portable", "canonicalize"}
DEFAULT_CONFIG_SYNC_PROFILES_FILE = "config_sync_profiles.yaml"

POSIX_SHELL_NAMES = {
    ".bashrc",
    ".bash_profile",
    ".bash_login",
    ".profile",
    ".zshrc",
    ".zprofile",
    ".zshenv",
    ".kshrc",
    ".mkshrc",
    ".tcshrc",
}
POWERSHELL_NAMES = {
    "Microsoft.PowerShell_profile.ps1",
    "profile.ps1",
    "Microsoft.PowerShell_profile.psm1",
}
POSIX_SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".profile", ".env"}
POWERSHELL_SUFFIXES = {".ps1", ".psm1", ".psd1"}
TEXT_SUFFIXES = {
    ".conf",
    ".config",
    ".ini",
    ".json",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".rc",
    ".fish",
    ".lua",
    ".vim",
    ".xml",
}
EXPORT_RE = re.compile(r"^export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
POWERSHELL_ENV_RE = re.compile(
    r"^\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", re.IGNORECASE
)
TEMPLATE_TOKEN_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_index() -> dict[str, Any]:
    return {
        "version": 2,
        "kind": "config_sync",
        "updated_at": None,
        "last_scan_at": None,
        "last_backup_at": None,
        "entries": {},
        "history": [],
    }


def _default_catalog() -> dict[str, Any]:
    return {
        "version": 1,
        "sources": [],
        "profiles": [],
    }


def _normalize_target_env(value: str | None) -> TargetEnv:
    if (
        value is None
        or not str(value).strip()
        or str(value).strip().lower() == "current"
    ):
        system = platform.system().lower()
        if system.startswith("win"):
            return "windows"
        if system == "darwin":
            return "mac"
        return "linux"
    normalized = value.strip().lower()
    aliases = {
        "darwin": "mac",
        "macos": "mac",
        "osx": "mac",
        "win": "windows",
        "windows": "windows",
        "linux": "linux",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in CONFIG_SYNC_TARGET_ENVS:
        raise ValueError(
            f"target must be one of: {', '.join(CONFIG_SYNC_TARGET_ENVS)}."
        )
    return normalized  # type: ignore[return-value]


def _normalize_line_ending_mode(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    if normalized not in LINE_ENDING_MODES:
        raise ValueError(
            f"line_endings must be one of: {', '.join(sorted(LINE_ENDING_MODES))}."
        )
    return normalized


def _normalize_conversion_mode(value: str | None) -> str:
    normalized = (value or "auto").strip().lower()
    if normalized not in CONVERSION_MODES:
        raise ValueError(
            f"conversion_mode must be one of: {', '.join(sorted(CONVERSION_MODES))}."
        )
    return normalized


def _home_path() -> Path:
    return Path.home().expanduser()


def _template_values() -> dict[str, str]:
    home = _home_path()
    return {
        "HOME": str(home),
        "USERPROFILE": os.environ.get("USERPROFILE", str(home)),
        "XDG_CONFIG_HOME": os.environ.get("XDG_CONFIG_HOME", str(home / ".config")),
        "XDG_DATA_HOME": os.environ.get(
            "XDG_DATA_HOME", str(home / ".local" / "share")
        ),
        "XDG_STATE_HOME": os.environ.get(
            "XDG_STATE_HOME", str(home / ".local" / "state")
        ),
        "APPDATA": os.environ.get("APPDATA", str(home / "AppData" / "Roaming")),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")),
        "MAC_APP_SUPPORT": str(home / "Library" / "Application Support"),
        "DOCUMENTS": str(home / "Documents"),
    }


def _runtime_path(
    runtime: SubstrateRuntime,
    *,
    key: str,
    legacy_key: str | None = None,
    fallback: str,
) -> Path:
    path = runtime.paths.get(key)
    if isinstance(path, Path):
        return path
    if legacy_key:
        legacy = runtime.paths.get(legacy_key)
        if isinstance(legacy, Path):
            return legacy
    return runtime.root / fallback


def _index_path(runtime: SubstrateRuntime) -> Path:
    return _runtime_path(
        runtime,
        key="config_sync_index",
        legacy_key="dotfiles_index",
        fallback="state/config-sync-index.json",
    )


def _legacy_index_path(runtime: SubstrateRuntime) -> Path | None:
    path = runtime.paths.get("dotfiles_index")
    if isinstance(path, Path):
        return path
    return None


def _backup_base_path(runtime: SubstrateRuntime) -> Path:
    return _runtime_path(
        runtime,
        key="config_sync_backups",
        legacy_key="dotfiles_backups",
        fallback="memory/config-sync/backups",
    )


def _deploy_base_path(runtime: SubstrateRuntime) -> Path:
    return _runtime_path(
        runtime,
        key="config_sync_deployments",
        legacy_key="dotfiles_deployments",
        fallback="memory/config-sync/deployments",
    )


def _profiles_path(runtime: SubstrateRuntime) -> Path:
    return _runtime_path(
        runtime,
        key="config_sync_profiles",
        fallback=DEFAULT_CONFIG_SYNC_PROFILES_FILE,
    )


def _load_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_index()
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(payload, dict):
        return _default_index()
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        payload["entries"] = {}
    history = payload.get("history")
    if not isinstance(history, list):
        payload["history"] = []
    payload.setdefault("version", 2)
    payload.setdefault("kind", "config_sync")
    payload.setdefault("updated_at", None)
    payload.setdefault("last_scan_at", None)
    payload.setdefault("last_backup_at", None)
    return payload


def _load_runtime_index(runtime: SubstrateRuntime) -> dict[str, Any]:
    primary = _index_path(runtime)
    if primary.exists():
        return _load_index(primary)
    legacy = _legacy_index_path(runtime)
    if legacy and legacy != primary and legacy.exists():
        migrated = _load_index(legacy)
        migrated.setdefault("migrated_from", str(legacy))
        return migrated
    return _default_index()


def _save_index(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _utc_now()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in paths:
        key = str(path.expanduser())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path.expanduser())
    return deduped


def _normalize_path_templates(raw_paths: Any, *, field: str) -> list[str]:
    templates: list[str] = []
    if raw_paths is None:
        return templates
    if isinstance(raw_paths, list):
        for item in raw_paths:
            if not isinstance(item, str):
                raise ValueError(f"{field} items must be strings.")
            value = item.strip()
            if value:
                templates.append(value)
        return templates
    if isinstance(raw_paths, dict):
        for key, value in raw_paths.items():
            if isinstance(value, str):
                text = value.strip()
                if text:
                    templates.append(text)
                continue
            if isinstance(value, list):
                for item in value:
                    if not isinstance(item, str):
                        raise ValueError(f"{field}.{key} items must be strings.")
                    text = item.strip()
                    if text:
                        templates.append(text)
                continue
            raise ValueError(f"{field}.{key} must be a string or list of strings.")
        return templates
    raise ValueError(f"{field} must be a list or mapping.")


def _normalize_catalog(runtime: SubstrateRuntime) -> dict[str, Any]:
    path = _profiles_path(runtime)
    source = _load_yaml(path)
    if not source:
        return _default_catalog()

    sources_payload: list[dict[str, str]] = []
    for raw_source in _ensure_list(source.get("sources"), "sources"):
        if not isinstance(raw_source, dict):
            raise ValueError("sources items must be mappings.")
        source_id = str(raw_source.get("id") or "").strip()
        if not source_id:
            continue
        sources_payload.append(
            {
                "id": source_id,
                "name": str(raw_source.get("name") or source_id),
                "docs_url": str(raw_source.get("docs_url") or ""),
                "repo_url": str(raw_source.get("repo_url") or ""),
                "rationale": str(raw_source.get("rationale") or ""),
            }
        )

    profiles_payload: list[dict[str, Any]] = []
    for raw_profile in _ensure_list(source.get("profiles"), "profiles"):
        if not isinstance(raw_profile, dict):
            raise ValueError("profiles items must be mappings.")
        profile_id = str(raw_profile.get("id") or "").strip()
        if not profile_id:
            raise ValueError("profiles[].id is required.")
        entries_payload: list[dict[str, Any]] = []
        for raw_entry in _ensure_list(
            raw_profile.get("entries"), f"profiles[{profile_id}].entries"
        ):
            if not isinstance(raw_entry, dict):
                raise ValueError(
                    f"profiles[{profile_id}].entries items must be mappings."
                )
            entry_id = str(raw_entry.get("id") or "").strip()
            if not entry_id:
                raise ValueError(f"profiles[{profile_id}] entry is missing id.")
            templates = _normalize_path_templates(
                raw_entry.get("paths"),
                field=f"profiles[{profile_id}].entries[{entry_id}].paths",
            )
            entries_payload.append(
                {
                    "id": entry_id,
                    "label": str(raw_entry.get("label") or entry_id),
                    "application": str(
                        raw_entry.get("application") or raw_entry.get("app") or entry_id
                    ),
                    "category": str(raw_entry.get("category") or "application"),
                    "classification": str(
                        raw_entry.get("classification") or "app-config"
                    ),
                    "kind_hint": str(raw_entry.get("kind") or "file"),
                    "path_templates": templates,
                    "target_envs": [
                        str(item)
                        for item in _ensure_list(
                            raw_entry.get("target_envs"), "target_envs"
                        )
                    ]
                    or list(CONFIG_SYNC_TARGET_ENVS),
                }
            )
        profiles_payload.append(
            {
                "id": profile_id,
                "name": str(raw_profile.get("name") or profile_id),
                "description": str(raw_profile.get("description") or ""),
                "enabled_by_default": bool(raw_profile.get("enabled_by_default", True)),
                "entries": entries_payload,
                "sources": [
                    str(item)
                    for item in _ensure_list(raw_profile.get("sources"), "sources")
                ],
                "tags": [
                    str(item) for item in _ensure_list(raw_profile.get("tags"), "tags")
                ],
            }
        )
    return {
        "version": int(source.get("version") or 1),
        "sources": sources_payload,
        "profiles": profiles_payload,
    }


def _expand_template(path_template: str, values: dict[str, str]) -> Path:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "")

    expanded = TEMPLATE_TOKEN_RE.sub(_replace, path_template)
    expanded = os.path.expandvars(expanded)
    return Path(expanded).expanduser()


def _legacy_candidate_paths() -> list[Path]:
    home = _home_path()
    xdg_config_home = Path(
        os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
    ).expanduser()
    appdata = Path(
        os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
    ).expanduser()

    candidates: list[Path] = [
        home / ".bashrc",
        home / ".bash_profile",
        home / ".bash_login",
        home / ".profile",
        home / ".zshrc",
        home / ".zprofile",
        home / ".zshenv",
        home / ".gitconfig",
        home / ".npmrc",
        home / ".tmux.conf",
        home / ".ssh" / "config",
        home / ".config" / "git" / "config",
        home / ".config" / "nvim",
        home / ".config" / "fish",
        home / ".config" / "kitty",
        home / ".config" / "alacritty",
        home / ".config" / "wezterm",
        home / ".config" / "code" / "User",
        xdg_config_home / "git" / "config",
        xdg_config_home / "nvim",
        xdg_config_home / "fish",
        xdg_config_home / "kitty",
        xdg_config_home / "alacritty",
        xdg_config_home / "wezterm",
        xdg_config_home / "code" / "User",
        home / "Library" / "Application Support" / "Code" / "User",
        home / "Library" / "Application Support" / "nvim",
        home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
        home / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
        appdata / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
        appdata / "Code" / "User",
    ]
    return _dedupe_paths(candidates)


def _candidate_map(runtime: SubstrateRuntime) -> dict[str, dict[str, Any]]:
    values = _template_values()
    catalog = _normalize_catalog(runtime)
    candidates: dict[str, dict[str, Any]] = {}

    for profile in catalog["profiles"]:
        if not profile.get("enabled_by_default", True):
            continue
        for entry in profile.get("entries", []):
            if not isinstance(entry, dict):
                continue
            for template in entry.get("path_templates", []):
                path = _expand_template(str(template), values).expanduser()
                key = str(path)
                if key in candidates:
                    continue
                candidates[key] = {
                    "profile_id": profile.get("id"),
                    "profile_name": profile.get("name"),
                    "entry_id": entry.get("id"),
                    "entry_label": entry.get("label"),
                    "application": entry.get("application"),
                    "category": entry.get("category"),
                    "classification": entry.get("classification"),
                    "kind_hint": entry.get("kind_hint"),
                    "managed_by": [
                        item
                        for item in profile.get("sources", [])
                        if isinstance(item, str)
                    ],
                }

    for legacy in _legacy_candidate_paths():
        key = str(legacy.expanduser())
        candidates.setdefault(
            key,
            {
                "profile_id": "legacy_dotfiles",
                "profile_name": "Legacy Dotfiles",
                "entry_id": legacy.name,
                "entry_label": legacy.name,
                "application": "generic",
                "category": "legacy-dotfile",
                "classification": "dotfile",
                "kind_hint": "file",
                "managed_by": [],
            },
        )
    return candidates


def discover_dotfiles() -> list[Path]:
    discovered: list[Path] = []
    for candidate in _legacy_candidate_paths():
        try:
            if candidate.exists():
                discovered.append(candidate)
        except OSError:
            continue
    return _dedupe_paths(discovered)


def discover_config_sync_paths(
    runtime: SubstrateRuntime,
) -> list[tuple[Path, dict[str, Any]]]:
    discovered: list[tuple[Path, dict[str, Any]]] = []
    for source_path, hint in _candidate_map(runtime).items():
        candidate = Path(source_path).expanduser()
        try:
            if candidate.exists():
                discovered.append((candidate, hint))
        except OSError:
            continue
    discovered.sort(key=lambda item: str(item[0]))
    return discovered


def _relative_source_path(source: Path) -> Path:
    home = _home_path()
    resolved = source.expanduser()
    try:
        return resolved.resolve().relative_to(home.resolve())
    except Exception:
        parts = [part for part in resolved.parts if part not in {resolved.anchor, ""}]
        return (
            Path("external") / Path(*parts[-4:])
            if parts
            else Path("external") / source.name
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_path(path: Path) -> str:
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path.rglob("*")):
            if child.is_dir():
                continue
            rel = child.relative_to(path).as_posix().encode("utf-8")
            digest.update(rel)
            if child.is_symlink():
                digest.update(f"symlink:{os.readlink(child)}".encode("utf-8"))
                continue
            digest.update(_sha256_file(child).encode("utf-8"))
        return digest.hexdigest()
    if path.is_file():
        return _sha256_file(path)
    return ""


def _detect_family(path: Path) -> str:
    name = path.name
    suffix = path.suffix.lower()
    lower_name = name.lower()
    if name in POWERSHELL_NAMES or suffix in POWERSHELL_SUFFIXES:
        return "powershell"
    if name in POSIX_SHELL_NAMES or suffix in POSIX_SHELL_SUFFIXES:
        return "posix-shell"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if lower_name.startswith(".") and not suffix:
        return "text"
    return "config"


def _entry_metadata(
    path: Path,
    *,
    existing: dict[str, Any] | None = None,
    hint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stat_result = path.stat()
    family = _detect_family(path)
    relative_path = _relative_source_path(path).as_posix()
    hint_payload = hint or {}
    metadata = {
        "source_path": str(path.expanduser()),
        "relative_path": relative_path,
        "name": path.name,
        "kind": "directory" if path.is_dir() else "file",
        "family": family,
        "exists": True,
        "is_symlink": path.is_symlink(),
        "size_bytes": stat_result.st_size,
        "modified_at": datetime.fromtimestamp(
            stat_result.st_mtime, tz=timezone.utc
        ).isoformat(),
        "checksum": _checksum_path(path),
        "backup_count": int(existing.get("backup_count", 0)) if existing else 0,
        "last_backup_at": existing.get("last_backup_at") if existing else None,
        "last_backup_path": existing.get("last_backup_path") if existing else None,
        "last_backup_checksum": existing.get("last_backup_checksum")
        if existing
        else None,
        "last_seen_at": _utc_now(),
        "deployment_family": family,
        "profile_id": str(
            hint_payload.get("profile_id")
            or existing.get("profile_id")
            or "unclassified"
        )
        if existing
        else str(hint_payload.get("profile_id") or "unclassified"),
        "profile_name": str(
            hint_payload.get("profile_name")
            or existing.get("profile_name")
            or "Unclassified"
        )
        if existing
        else str(hint_payload.get("profile_name") or "Unclassified"),
        "entry_id": str(
            hint_payload.get("entry_id") or existing.get("entry_id") or path.name
        )
        if existing
        else str(hint_payload.get("entry_id") or path.name),
        "application": str(
            hint_payload.get("application") or existing.get("application") or "generic"
        )
        if existing
        else str(hint_payload.get("application") or "generic"),
        "category": str(
            hint_payload.get("category") or existing.get("category") or "application"
        )
        if existing
        else str(hint_payload.get("category") or "application"),
        "classification": str(
            hint_payload.get("classification")
            or existing.get("classification")
            or ("dotfile" if path.name.startswith(".") else "app-config")
        )
        if existing
        else str(
            hint_payload.get("classification")
            or ("dotfile" if path.name.startswith(".") else "app-config")
        ),
        "managed_by": list(
            hint_payload.get("managed_by")
            if isinstance(hint_payload.get("managed_by"), list)
            else existing.get("managed_by", [])
            if existing
            else []
        ),
    }
    if path.is_dir():
        metadata["file_count"] = sum(1 for child in path.rglob("*") if child.is_file())
    else:
        metadata["file_count"] = 1
    return metadata


def _merge_entries(
    index: dict[str, Any],
    discovered: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    entries: dict[str, Any] = dict(index.get("entries", {}))
    discovered_map = {str(path.expanduser()): (path, hint) for path, hint in discovered}

    for source_path, (path, hint) in discovered_map.items():
        existing = entries.get(source_path)
        entries[source_path] = _entry_metadata(
            path,
            existing=existing if isinstance(existing, dict) else None,
            hint=hint if isinstance(hint, dict) else None,
        )

    for source_path, existing in list(entries.items()):
        if source_path in discovered_map:
            continue
        if isinstance(existing, dict):
            existing["exists"] = False
            existing["last_seen_at"] = existing.get("last_seen_at") or index.get(
                "last_scan_at"
            )
            entries[source_path] = existing

    index["entries"] = entries
    index["last_scan_at"] = _utc_now()
    return index


def _entry_list(index: dict[str, Any]) -> list[dict[str, Any]]:
    entries = index.get("entries", {})
    if not isinstance(entries, dict):
        return []
    items = [value for value in entries.values() if isinstance(value, dict)]
    return sorted(items, key=lambda item: item.get("source_path") or "")


def _filter_entries(
    entries: list[dict[str, Any]],
    *,
    selection: list[str] | None,
    profile_ids: list[str] | None,
) -> list[dict[str, Any]]:
    filtered = entries
    normalized_profiles = [item.strip() for item in (profile_ids or []) if item.strip()]
    if normalized_profiles:
        profile_set = set(normalized_profiles)
        filtered = [
            entry
            for entry in filtered
            if str(entry.get("profile_id") or "") in profile_set
        ]

    normalized = [item.strip() for item in (selection or []) if item.strip()]
    if not normalized:
        return filtered
    selected: list[dict[str, Any]] = []
    for entry in filtered:
        source_path = str(entry.get("source_path") or "")
        relative_path = str(entry.get("relative_path") or "")
        name = str(entry.get("name") or "")
        if any(
            source_path == filter_item
            or source_path.endswith(filter_item)
            or relative_path == filter_item
            or relative_path.endswith(filter_item)
            or name == filter_item
            for filter_item in normalized
        ):
            selected.append(entry)
    return selected


def _select_entries_for_runtime(
    runtime: SubstrateRuntime,
    *,
    selection: list[str] | None = None,
    profile_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    index = _load_runtime_index(runtime)
    entries = _entry_list(index)
    discovered = discover_config_sync_paths(runtime)
    if entries:
        merged: dict[str, dict[str, Any]] = {}
        for entry in entries:
            source_path = str(entry.get("source_path") or "")
            if source_path:
                merged[source_path] = dict(entry)
        for path, hint in discovered:
            source_path = str(path.expanduser())
            merged[source_path] = _entry_metadata(
                path,
                existing=merged.get(source_path)
                if isinstance(merged.get(source_path), dict)
                else None,
                hint=hint,
            )
        entries = sorted(
            merged.values(), key=lambda item: item.get("source_path") or ""
        )
    else:
        entries = [_entry_metadata(path, hint=hint) for path, hint in discovered]
    return _filter_entries(entries, selection=selection, profile_ids=profile_ids)


def _line_ending_target(target_env: TargetEnv) -> str:
    return "crlf" if target_env == "windows" else "lf"


def _resolved_line_ending_target(target_env: TargetEnv, mode: str) -> str:
    if mode == "auto":
        return _line_ending_target(target_env)
    if mode == "preserve":
        return "preserve"
    return mode


def normalize_line_endings(text: str, target: str = "lf") -> str:
    if target.lower() == "preserve":
        return text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if target.lower() == "crlf":
        return normalized.replace("\n", "\r\n")
    return normalized


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _quote_posix(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _quote_powershell(value: str) -> str:
    escaped = value.replace("`", "``").replace('"', '`"')
    return f'"{escaped}"'


def posix_exports_to_powershell(text: str) -> str:
    output: list[str] = []
    for line in normalize_line_endings(text, "lf").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output.append(line)
            continue
        match = EXPORT_RE.match(stripped)
        if not match:
            output.append(line)
            continue
        key = match.group(1)
        value = _strip_quotes(match.group(2).strip())
        output.append(f"$Env:{key} = {_quote_powershell(value)}")
    return "\n".join(output)


def powershell_exports_to_posix(text: str) -> str:
    output: list[str] = []
    for line in normalize_line_endings(text, "lf").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output.append(line)
            continue
        match = POWERSHELL_ENV_RE.match(stripped)
        if not match:
            output.append(line)
            continue
        key = match.group(1)
        value = _strip_quotes(match.group(2).strip())
        output.append(f"export {key}={_quote_posix(value)}")
    return "\n".join(output)


def convert_content_for_target(
    text: str,
    source_family: str,
    target_env: TargetEnv,
    *,
    line_endings_mode: str = "auto",
    conversion_mode: str = "auto",
) -> str:
    normalized_line_endings = _resolved_line_ending_target(
        target_env, line_endings_mode
    )
    normalized = normalize_line_endings(text, normalized_line_endings)
    normalized_conversion_mode = _normalize_conversion_mode(conversion_mode)
    should_convert_exports = normalized_conversion_mode != "preserve"
    if (
        should_convert_exports
        and source_family == "posix-shell"
        and target_env == "windows"
    ):
        normalized = posix_exports_to_powershell(normalized)
    elif (
        should_convert_exports
        and source_family == "powershell"
        and target_env in {"linux", "mac"}
    ):
        normalized = powershell_exports_to_posix(normalized)
    return normalize_line_endings(normalized, normalized_line_endings)


def _target_root_hint(target_env: TargetEnv) -> str:
    return {"linux": "~", "mac": "~", "windows": "%USERPROFILE%"}[target_env]


def _suggested_target_path(entry: dict[str, Any], target_env: TargetEnv) -> str:
    relative_path = Path(
        entry.get("relative_path")
        or entry.get("source_path")
        or entry.get("name")
        or ""
    )
    target_root = _target_root_hint(target_env)
    return f"{target_root}/{relative_path.as_posix()}"


def _plan_entry(
    entry: dict[str, Any],
    target_env: TargetEnv,
    *,
    line_endings_mode: str,
    conversion_mode: str,
) -> dict[str, Any]:
    family = str(entry.get("family") or "config")
    transforms: list[str] = []
    resolved_line_endings = _resolved_line_ending_target(target_env, line_endings_mode)
    if resolved_line_endings == "crlf":
        transforms.append("line_endings:*->crlf")
    elif resolved_line_endings == "lf":
        transforms.append("line_endings:*->lf")
    if (
        conversion_mode != "preserve"
        and family == "posix-shell"
        and target_env == "windows"
    ):
        transforms.append("env_exports:posix->powershell")
    elif (
        conversion_mode != "preserve"
        and family == "powershell"
        and target_env in {"linux", "mac"}
    ):
        transforms.append("env_exports:powershell->posix")
    return {
        "source_path": str(entry.get("source_path") or ""),
        "relative_path": entry.get("relative_path"),
        "target_env": target_env,
        "target_path_hint": _suggested_target_path(entry, target_env),
        "family": family,
        "profile_id": entry.get("profile_id"),
        "application": entry.get("application"),
        "exists": bool(entry.get("exists", False)),
        "action": "copy" if entry.get("exists", False) else "skip",
        "transforms": transforms,
        "line_endings_mode": line_endings_mode,
        "conversion_mode": conversion_mode,
        "backup_ready": bool(entry.get("checksum")),
        "checksum": entry.get("checksum"),
        "last_backup_at": entry.get("last_backup_at"),
        "last_backup_path": entry.get("last_backup_path"),
        "warnings": [] if entry.get("exists", False) else ["source file is missing"],
    }


def _backup_destination_for(source: Path, backup_root: Path) -> Path:
    return backup_root / _relative_source_path(source)


def _content_transform(
    path: Path,
    target_env: TargetEnv,
    *,
    line_endings_mode: str,
    conversion_mode: str,
) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    family = _detect_family(path)
    return convert_content_for_target(
        text,
        family,
        target_env,
        line_endings_mode=line_endings_mode,
        conversion_mode=conversion_mode,
    )


def _deploy_single_file(
    source: Path,
    target_path: Path,
    target_env: TargetEnv,
    *,
    line_endings_mode: str,
    conversion_mode: str,
) -> None:
    family = _detect_family(source)
    if family in {"posix-shell", "powershell", "text", "config"}:
        transformed = _content_transform(
            source,
            target_env,
            line_endings_mode=line_endings_mode,
            conversion_mode=conversion_mode,
        )
        target_path.write_text(transformed, encoding="utf-8")
        shutil.copystat(source, target_path, follow_symlinks=True)
        return
    shutil.copy2(source, target_path)


def _deploy_tree(
    source: Path,
    target_path: Path,
    target_env: TargetEnv,
    *,
    line_endings_mode: str,
    conversion_mode: str,
) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    for child in source.rglob("*"):
        relative = child.relative_to(source)
        destination = target_path / relative
        if child.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        _deploy_single_file(
            child,
            destination,
            target_env,
            line_endings_mode=line_endings_mode,
            conversion_mode=conversion_mode,
        )


def scan_config_sync(runtime: SubstrateRuntime) -> dict[str, Any]:
    discovered = discover_config_sync_paths(runtime)
    index = _load_runtime_index(runtime)
    index = _merge_entries(index, discovered)
    _save_index(_index_path(runtime), index)
    return config_sync_payload(runtime, index=index)


def backup_config_sync(
    runtime: SubstrateRuntime,
    selection: list[str] | None = None,
    profile_ids: list[str] | None = None,
) -> dict[str, Any]:
    index = _load_runtime_index(runtime)
    selected = _select_entries_for_runtime(
        runtime,
        selection=selection,
        profile_ids=profile_ids,
    )

    backup_root = _backup_base_path(runtime) / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%SZ"
    )
    backup_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for entry in selected:
        source = Path(str(entry.get("source_path") or "")).expanduser()
        if not source.exists():
            results.append(
                {"source_path": str(source), "status": "missing", "backup_path": None}
            )
            continue
        destination = _backup_destination_for(source, backup_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(
                source, destination, dirs_exist_ok=True, copy_function=shutil.copy2
            )
        else:
            shutil.copy2(source, destination)
        checksum = _checksum_path(source)
        updated_entry = dict(entry)
        updated_entry["exists"] = True
        updated_entry["checksum"] = checksum
        updated_entry["backup_count"] = int(updated_entry.get("backup_count", 0)) + 1
        updated_entry["last_backup_at"] = _utc_now()
        updated_entry["last_backup_path"] = str(destination)
        updated_entry["last_backup_checksum"] = checksum
        index.setdefault("entries", {})[str(source)] = updated_entry
        results.append(
            {
                "source_path": str(source),
                "status": "backed_up",
                "backup_path": str(destination),
                "checksum": checksum,
                "profile_id": entry.get("profile_id"),
            }
        )

    if results:
        index["last_backup_at"] = _utc_now()
        index.setdefault("history", []).append(
            {
                "ts": index["last_backup_at"],
                "backup_root": str(backup_root),
                "entries": len(results),
                "selection": selection or [],
                "profiles": profile_ids or [],
            }
        )
        _save_index(_index_path(runtime), index)

    manifest = {
        "generated_at": _utc_now(),
        "backup_root": str(backup_root),
        "entries": results,
        "profiles": profile_ids or [],
    }
    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "backup_root": str(backup_root),
        "entries": results,
        "count": len(results),
        "profiles": profile_ids or [],
    }


def config_sync_payload(
    runtime: SubstrateRuntime, index: dict[str, Any] | None = None
) -> dict[str, Any]:
    loaded_index = index or _load_runtime_index(runtime)
    entries = _entry_list(loaded_index)
    discovered = discover_config_sync_paths(runtime)
    if entries:
        merged: dict[str, dict[str, Any]] = {}
        for entry in entries:
            source_path = str(entry.get("source_path") or "")
            if source_path:
                merged[source_path] = dict(entry)
        for path, hint in discovered:
            source_path = str(path.expanduser())
            merged[source_path] = _entry_metadata(
                path,
                existing=merged.get(source_path)
                if isinstance(merged.get(source_path), dict)
                else None,
                hint=hint,
            )
        entries = sorted(
            merged.values(), key=lambda item: item.get("source_path") or ""
        )
    elif discovered:
        entries = [_entry_metadata(path, hint=hint) for path, hint in discovered]

    catalog = _normalize_catalog(runtime)
    target_env = _normalize_target_env(None)
    existing_total = sum(1 for entry in entries if entry.get("exists"))
    missing_total = sum(1 for entry in entries if not entry.get("exists"))
    backup_total = sum(1 for entry in entries if entry.get("last_backup_at"))
    changed_total = sum(
        1
        for entry in entries
        if entry.get("checksum")
        and entry.get("last_backup_checksum")
        and entry.get("checksum") != entry.get("last_backup_checksum")
    )
    profile_counts: dict[str, int] = {}
    for entry in entries:
        key = str(entry.get("profile_id") or "unclassified")
        profile_counts[key] = profile_counts.get(key, 0) + 1

    return {
        "version": loaded_index.get("version", 2),
        "feature": {
            "id": "config_sync",
            "name": "Backup & Sync",
            "legacy_alias": "dotfiles",
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "target_env": target_env,
            "home": str(_home_path()),
        },
        "summary": {
            "entries_total": len(entries),
            "existing_total": existing_total,
            "missing_total": missing_total,
            "changed_total": changed_total,
            "backed_up_total": backup_total,
            "last_scan_at": loaded_index.get("last_scan_at"),
            "last_backup_at": loaded_index.get("last_backup_at"),
        },
        "entries": entries,
        "inventory": entries,
        "profile_counts": profile_counts,
        "catalog": catalog,
        "history": loaded_index.get("history", []),
        "index_path": str(_index_path(runtime)),
        "backup_root": str(_backup_base_path(runtime)),
        "deploy_root": str(_deploy_base_path(runtime)),
    }


def plan_config_sync(
    runtime: SubstrateRuntime,
    *,
    target_env: str | None = None,
    selection: list[str] | None = None,
    profile_ids: list[str] | None = None,
    line_endings_mode: str = "auto",
    conversion_mode: str = "auto",
) -> dict[str, Any]:
    normalized_target = _normalize_target_env(target_env)
    normalized_line_endings = _normalize_line_ending_mode(line_endings_mode)
    normalized_conversion = _normalize_conversion_mode(conversion_mode)
    entries = _select_entries_for_runtime(
        runtime,
        selection=selection,
        profile_ids=profile_ids,
    )
    planned = [
        _plan_entry(
            entry,
            normalized_target,
            line_endings_mode=normalized_line_endings,
            conversion_mode=normalized_conversion,
        )
        for entry in entries
    ]
    return {
        "ok": True,
        "target_env": normalized_target,
        "line_endings_mode": normalized_line_endings,
        "conversion_mode": normalized_conversion,
        "profiles": profile_ids or [],
        "plan": planned,
        "summary": {
            "selected_total": len(planned),
            "copy_total": sum(1 for item in planned if item["action"] == "copy"),
            "missing_total": sum(1 for item in planned if item["action"] == "skip"),
            "line_endings_mode": normalized_line_endings,
            "conversion_mode": normalized_conversion,
        },
    }


def deploy_config_sync(
    runtime: SubstrateRuntime,
    *,
    target_env: str | None = None,
    apply: bool = False,
    directive: str | None = None,
    destination: str | None = None,
    selection: list[str] | None = None,
    profile_ids: list[str] | None = None,
    line_endings_mode: str = "auto",
    conversion_mode: str = "auto",
) -> dict[str, Any]:
    normalized_target = _normalize_target_env(target_env)
    normalized_line_endings = _normalize_line_ending_mode(line_endings_mode)
    normalized_conversion = _normalize_conversion_mode(conversion_mode)
    directive_text = (directive or "").strip()
    if not apply:
        raise PermissionError("deploy writes require --apply.")
    if not directive_text:
        raise PermissionError("deploy writes require a directive.")

    plan = plan_config_sync(
        runtime,
        target_env=normalized_target,
        selection=selection,
        profile_ids=profile_ids,
        line_endings_mode=normalized_line_endings,
        conversion_mode=normalized_conversion,
    )
    deploy_root = _deploy_base_path(runtime) / datetime.now(timezone.utc).strftime(
        "%Y%m%d-%H%M%SZ"
    )
    deploy_root.mkdir(parents=True, exist_ok=True)

    if destination:
        destination_root = Path(destination).expanduser()
        destination_root.mkdir(parents=True, exist_ok=True)
    else:
        destination_root = deploy_root

    applied: list[dict[str, Any]] = []
    for item in plan["plan"]:
        if item["action"] != "copy":
            applied.append(
                {
                    "source_path": item["source_path"],
                    "status": "skipped",
                    "target_path": item["target_path_hint"],
                }
            )
            continue
        source = Path(str(item["source_path"])).expanduser()
        if not source.exists():
            applied.append(
                {
                    "source_path": str(source),
                    "status": "missing",
                    "target_path": item["target_path_hint"],
                }
            )
            continue
        relative = _relative_source_path(source)
        target_path = destination_root / relative
        if source.is_dir():
            _deploy_tree(
                source,
                target_path,
                normalized_target,
                line_endings_mode=normalized_line_endings,
                conversion_mode=normalized_conversion,
            )
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _deploy_single_file(
                source,
                target_path,
                normalized_target,
                line_endings_mode=normalized_line_endings,
                conversion_mode=normalized_conversion,
            )
        applied.append(
            {
                "source_path": str(source),
                "status": "applied",
                "target_path": str(target_path),
                "transforms": item["transforms"],
                "profile_id": item.get("profile_id"),
            }
        )

    manifest = {
        "generated_at": _utc_now(),
        "target_env": normalized_target,
        "directive": directive_text,
        "line_endings_mode": normalized_line_endings,
        "conversion_mode": normalized_conversion,
        "destination_root": str(destination_root),
        "profiles": profile_ids or [],
        "items": applied,
        "source_plan": plan["plan"],
    }
    (deploy_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "target_env": normalized_target,
        "apply": True,
        "directive": directive_text,
        "line_endings_mode": normalized_line_endings,
        "conversion_mode": normalized_conversion,
        "profiles": profile_ids or [],
        "destination_root": str(destination_root),
        "deploy_root": str(deploy_root),
        "items": applied,
        "summary": {
            "applied_total": sum(1 for item in applied if item["status"] == "applied"),
            "skipped_total": sum(1 for item in applied if item["status"] == "skipped"),
            "missing_total": sum(1 for item in applied if item["status"] == "missing"),
        },
    }


# Compatibility aliases for previous "dotfiles" naming.
scan_dotfiles = scan_config_sync
backup_dotfiles = backup_config_sync
dotfiles_payload = config_sync_payload
plan_dotfiles = plan_config_sync
deploy_dotfiles = deploy_config_sync
