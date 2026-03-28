from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .registry import SubstrateRuntime

VALID_ACCESS_MODES = {"read", "write"}
TOKEN_REF_RE = re.compile(r"^[A-Za-z0-9_./:-]{1,160}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"connections": {}}
    payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    if not isinstance(payload, dict):
        return {"connections": {}}
    connections = payload.get("connections")
    if not isinstance(connections, dict):
        return {"connections": {}}
    return {"connections": connections}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_service(raw: dict[str, Any]) -> dict[str, Any]:
    service_id = str(raw.get("id") or "").strip()
    if not service_id:
        raise ValueError("integration service id is required.")
    auth = raw.get("auth") if isinstance(raw.get("auth"), dict) else {}
    read_profile = (
        raw.get("read_profile") if isinstance(raw.get("read_profile"), dict) else {}
    )
    write_profile = (
        raw.get("write_profile") if isinstance(raw.get("write_profile"), dict) else {}
    )
    return {
        "id": service_id,
        "name": str(raw.get("name") or service_id),
        "category": str(raw.get("category") or "external"),
        "availability": str(raw.get("availability") or "general"),
        "api_status": str(raw.get("api_status") or "public"),
        "notes": str(raw.get("notes") or ""),
        "auth": {
            "methods": [
                str(item)
                for item in _ensure_list(
                    auth.get("methods"), f"services[{service_id}].auth.methods"
                )
            ],
            "login_url": str(auth.get("login_url") or ""),
            "docs_url": str(auth.get("docs_url") or ""),
        },
        "cli_tools": [
            str(item)
            for item in _ensure_list(
                raw.get("cli_tools"), f"services[{service_id}].cli_tools"
            )
        ],
        "supported_surfaces": [
            str(item)
            for item in _ensure_list(
                raw.get("supported_surfaces"),
                f"services[{service_id}].supported_surfaces",
            )
        ],
        "alternatives": [
            str(item)
            for item in _ensure_list(
                raw.get("alternatives"), f"services[{service_id}].alternatives"
            )
        ],
        "community_projects": [
            str(item)
            for item in _ensure_list(
                raw.get("community_projects"),
                f"services[{service_id}].community_projects",
            )
        ],
        "read_profile": {
            "default_scopes": [
                str(item)
                for item in _ensure_list(
                    read_profile.get("default_scopes"),
                    f"services[{service_id}].read_profile.default_scopes",
                )
            ],
            "guidance": str(read_profile.get("guidance") or ""),
        },
        "write_profile": {
            "scopes": [
                str(item)
                for item in _ensure_list(
                    write_profile.get("scopes"),
                    f"services[{service_id}].write_profile.scopes",
                )
            ],
            "guidance": str(write_profile.get("guidance") or ""),
        },
    }


def _catalog(runtime: SubstrateRuntime) -> dict[str, Any]:
    source = _load_yaml(runtime.paths["integrations"])
    defaults = (
        source.get("defaults") if isinstance(source.get("defaults"), dict) else {}
    )
    services = [
        _normalize_service(raw)
        for raw in _ensure_list(source.get("services"), "services")
        if isinstance(raw, dict)
    ]
    default_mode = str(defaults.get("access_mode") or "read")
    if default_mode not in VALID_ACCESS_MODES:
        default_mode = "read"
    return {
        "version": int(source.get("version") or 1),
        "defaults": {
            "access_mode": default_mode,
            "write_requires_directive": bool(
                defaults.get("write_requires_directive", True)
            ),
            "write_policy": str(
                defaults.get("write_policy")
                or "External writes require explicit directives."
            ),
        },
        "services": services,
    }


def _service_lookup(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {service["id"]: service for service in catalog["services"]}


def _validated_mode(mode: str, *, default_mode: str) -> str:
    normalized = mode.strip().lower() if mode else default_mode
    if normalized not in VALID_ACCESS_MODES:
        raise ValueError(
            f"mode must be one of: {', '.join(sorted(VALID_ACCESS_MODES))}"
        )
    return normalized


def _validated_token_ref(token_ref: str | None) -> str | None:
    if token_ref is None:
        return None
    normalized = token_ref.strip()
    if not normalized:
        return None
    if not TOKEN_REF_RE.fullmatch(normalized):
        raise ValueError("token_ref contains unsupported characters.")
    return normalized


def _parse_scopes(granted_scopes: str | list[str] | None) -> list[str]:
    if granted_scopes is None:
        return []
    if isinstance(granted_scopes, list):
        return [str(item).strip() for item in granted_scopes if str(item).strip()]
    return [segment.strip() for segment in granted_scopes.split(",") if segment.strip()]


def integrations_payload(runtime: SubstrateRuntime) -> dict[str, Any]:
    catalog = _catalog(runtime)
    state = _load_state(runtime.paths["integrations_state"])
    by_id = _service_lookup(catalog)

    services: list[dict[str, Any]] = []
    connected_total = 0
    write_total = 0
    for service_id, service in by_id.items():
        connection = state["connections"].get(service_id, {})
        connected = bool(connection.get("connected", False))
        mode = str(connection.get("mode") or catalog["defaults"]["access_mode"])
        if mode not in VALID_ACCESS_MODES:
            mode = catalog["defaults"]["access_mode"]
        if connected:
            connected_total += 1
        if connected and mode == "write":
            write_total += 1
        services.append(
            {
                **service,
                "connected": connected,
                "mode": mode,
                "granted_scopes": connection.get("granted_scopes", []),
                "auth_method": connection.get("auth_method"),
                "token_ref": connection.get("token_ref"),
                "write_directive": connection.get("write_directive"),
                "updated_at": connection.get("updated_at"),
            }
        )

    return {
        "version": catalog["version"],
        "defaults": catalog["defaults"],
        "summary": {
            "services_total": len(services),
            "connected_total": connected_total,
            "write_enabled_total": write_total,
        },
        "services": services,
    }


def connect_integration(
    runtime: SubstrateRuntime,
    *,
    service_id: str,
    auth_method: str | None = None,
    token_ref: str | None = None,
    granted_scopes: str | list[str] | None = None,
    mode: str | None = None,
    write_directive: str | None = None,
) -> dict[str, Any]:
    catalog = _catalog(runtime)
    by_id = _service_lookup(catalog)
    if service_id not in by_id:
        raise KeyError(f"Unknown integration service: {service_id}")

    selected_mode = _validated_mode(
        mode or "", default_mode=catalog["defaults"]["access_mode"]
    )
    directive = (write_directive or "").strip()
    if (
        selected_mode == "write"
        and catalog["defaults"]["write_requires_directive"]
        and not directive
    ):
        raise ValueError("write_directive is required when mode=write.")

    state = _load_state(runtime.paths["integrations_state"])
    service = by_id[service_id]
    selected_auth_method = (auth_method or "").strip() or None
    if selected_auth_method and selected_auth_method not in service["auth"]["methods"]:
        raise ValueError(
            f"auth_method must be one of: {', '.join(service['auth']['methods'])}"
        )

    connection = {
        "connected": True,
        "mode": selected_mode,
        "auth_method": selected_auth_method,
        "token_ref": _validated_token_ref(token_ref),
        "granted_scopes": _parse_scopes(granted_scopes),
        "write_directive": directive or None,
        "updated_at": _utc_now(),
    }
    state["connections"][service_id] = connection
    _save_state(runtime.paths["integrations_state"], state)
    return {
        "service_id": service_id,
        "connection": connection,
    }


def set_integration_mode(
    runtime: SubstrateRuntime,
    *,
    service_id: str,
    mode: str,
    write_directive: str | None = None,
) -> dict[str, Any]:
    catalog = _catalog(runtime)
    by_id = _service_lookup(catalog)
    if service_id not in by_id:
        raise KeyError(f"Unknown integration service: {service_id}")

    state = _load_state(runtime.paths["integrations_state"])
    connection = state["connections"].get(service_id)
    if not isinstance(connection, dict) or not connection.get("connected"):
        raise ValueError(f"Service '{service_id}' is not connected.")

    selected_mode = _validated_mode(
        mode, default_mode=catalog["defaults"]["access_mode"]
    )
    directive = (write_directive or "").strip()
    if (
        selected_mode == "write"
        and catalog["defaults"]["write_requires_directive"]
        and not directive
    ):
        raise ValueError("write_directive is required when mode=write.")

    connection["mode"] = selected_mode
    connection["write_directive"] = directive or None
    connection["updated_at"] = _utc_now()
    state["connections"][service_id] = connection
    _save_state(runtime.paths["integrations_state"], state)
    return {"service_id": service_id, "connection": connection}


def disconnect_integration(
    runtime: SubstrateRuntime, *, service_id: str
) -> dict[str, Any]:
    catalog = _catalog(runtime)
    by_id = _service_lookup(catalog)
    if service_id not in by_id:
        raise KeyError(f"Unknown integration service: {service_id}")

    state = _load_state(runtime.paths["integrations_state"])
    connection = state["connections"].get(service_id)
    if not isinstance(connection, dict):
        return {"service_id": service_id, "disconnected": False}

    state["connections"].pop(service_id, None)
    _save_state(runtime.paths["integrations_state"], state)
    return {"service_id": service_id, "disconnected": True}
