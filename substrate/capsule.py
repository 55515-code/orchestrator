"""Read-only discovery and release planning for the portable Gateway Capsule."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAPSULE_SCHEMA_VERSION = 1
DEFAULT_PANEL_PORT = 18080
DEFAULT_GATEWAY_CANDIDATE_PORT = 18090
REQUIRED_TOOLS = ("podman", "systemctl", "openclaw", "kilo", "restic", "btrfs")


def _run(command: list[str], *, cwd: Path, timeout: int = 8) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "exit_code": None, "output": str(exc)}
    output = (completed.stdout or completed.stderr).strip()
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": output[:4000],
    }


def _version(command: list[str], *, root: Path) -> str | None:
    result = _run(command, cwd=root)
    if not result["ok"]:
        return None
    return str(result["output"]).splitlines()[0] or None


def _port_available(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _filesystem_type(path: Path) -> str | None:
    result = _run(["findmnt", "-n", "-o", "FSTYPE", "--target", str(path)], cwd=path)
    return str(result["output"]).splitlines()[0] if result["ok"] else None


def _git_facts(root: Path) -> dict[str, Any]:
    commit = _run(["git", "rev-parse", "HEAD"], cwd=root)
    dirty = _run(["git", "status", "--porcelain"], cwd=root)
    return {
        "commit": commit["output"] if commit["ok"] else None,
        "dirty": bool(dirty["output"]) if dirty["ok"] else None,
    }


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_capsule(root: Path) -> dict[str, Any]:
    """Return a bounded, secret-free capability inventory without mutation."""
    root = root.resolve()
    tools = {name: shutil.which(name) for name in REQUIRED_TOOLS}
    openclaw_state = Path(os.environ.get("OPENCLAW_CONFIG_DIR", str(Path.home() / ".openclaw"))).expanduser()
    state_paths = {
        "workspace": root,
        "openclaw": openclaw_state,
        "substrate_state": root / "state",
        "substrate_memory": root / "memory",
        "kilo": Path.home() / ".config" / "kilo",
        "artifacts": root / "artifacts",
    }
    current_gateway_port = 8090
    return {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "read-only",
        "root": str(root),
        "filesystem": {
            "type": _filesystem_type(root),
            "btrfs": _filesystem_type(root) == "btrfs",
        },
        "tools": {name: {"available": path is not None, "path": path} for name, path in tools.items()},
        "versions": {
            "podman": _version(["podman", "version", "--format", "{{.Client.Version}}"], root=root),
            "openclaw": _version(["openclaw", "--version"], root=root),
            "kilo": _version(["kilo", "--version"], root=root),
            "restic": _version(["restic", "version"], root=root),
        },
        "rootless_podman": _run(["podman", "info", "--format", "{{.Host.Security.Rootless}}"], cwd=root)["output"]
        == "true",
        "ports": {
            "current_gateway": {
                "port": current_gateway_port,
                "available": _port_available(current_gateway_port),
            },
            "candidate_gateway": {
                "port": DEFAULT_GATEWAY_CANDIDATE_PORT,
                "available": _port_available(DEFAULT_GATEWAY_CANDIDATE_PORT),
            },
            "candidate_panel": {
                "port": DEFAULT_PANEL_PORT,
                "available": _port_available(DEFAULT_PANEL_PORT),
            },
        },
        "state": {name: {"path": str(path), "exists": path.exists()} for name, path in state_paths.items()},
        "git": _git_facts(root),
    }


def plan_capsule(root: Path) -> dict[str, Any]:
    """Build an actionable local research/development plan from a live probe."""
    probe = probe_capsule(root)
    missing = [name for name, item in probe["tools"].items() if not item["available"]]
    blocked: list[dict[str, str]] = []
    if missing:
        blocked.append({"code": "missing_tools", "detail": ", ".join(missing)})
    if not probe["rootless_podman"]:
        blocked.append({"code": "podman_not_rootless", "detail": "Rootless Podman is required."})
    if not probe["ports"]["candidate_gateway"]["available"]:
        blocked.append({"code": "candidate_gateway_port_busy", "detail": str(DEFAULT_GATEWAY_CANDIDATE_PORT)})
    if not probe["ports"]["candidate_panel"]["available"]:
        blocked.append({"code": "candidate_panel_port_busy", "detail": str(DEFAULT_PANEL_PORT)})

    return {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "mode": "plan-only",
        "ready_for_disposable_capsule": not blocked,
        "blocked": blocked,
        "live_gateway_untouched": True,
        "target": {
            "runtime": "rootless-podman",
            "manager": "systemd-user-quadlet",
            "publish_host": "127.0.0.1",
            "candidate_gateway_port": DEFAULT_GATEWAY_CANDIDATE_PORT,
            "candidate_panel_port": DEFAULT_PANEL_PORT,
        },
        "steps": [
            {
                "order": 1,
                "stage": "local",
                "pass": "research",
                "action": "capture release manifest and verified backups",
            },
            {"order": 2, "stage": "local", "pass": "development", "action": "build digest-addressed Substrate image"},
            {
                "order": 3,
                "stage": "local",
                "pass": "development",
                "action": "render Quadlets into an isolated candidate slot",
            },
            {
                "order": 4,
                "stage": "local",
                "pass": "testing",
                "action": "restore sanitized state and run health/security/session gates",
            },
            {
                "order": 5,
                "stage": "hosted_dev",
                "pass": "research",
                "action": "stop; production cutover remains separately gated",
            },
        ],
        "rollback": {
            "native_gateway_remains_enabled": True,
            "candidate_uses_alternate_ports": True,
            "state_restore_required_only_for_incompatible_migrations": True,
        },
        "probe": probe,
    }


def release_manifest(root: Path) -> dict[str, Any]:
    """Create a deterministic-shape release manifest without reading secrets."""
    root = root.resolve()
    probe = probe_capsule(root)
    tracked_config = [
        root / "deploy" / "compose.yaml",
        root / "deploy" / "Dockerfile",
        root / "deploy" / "quadlet" / "openclaw-candidate.container",
        root / "deploy" / "quadlet" / "substrate-candidate.container",
        root / "workspace.yaml",
        root / "uv.lock",
    ]
    return {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "git": probe["git"],
        "components": probe["versions"],
        "images": {
            "openclaw": {"reference": "${OPENCLAW_IMAGE_DIGEST}", "digest_required": True},
            "substrate": {"reference": "${SUBSTRATE_IMAGE_DIGEST}", "digest_required": True},
        },
        "config_sha256": {str(path.relative_to(root)): _sha256(path) for path in tracked_config if path.exists()},
        "volume_schema": {
            "version": 1,
            "required": ["openclaw", "workspace", "substrate-state", "memory", "kilo", "artifacts"],
        },
        "secret_references": ["OPENCLAW_GATEWAY_TOKEN", "provider credentials in OpenClaw state"],
        "promotion": {"stage": "local", "status": "unpromoted", "previous_release": None},
        "backup_ids": {"openclaw": None, "sqlite": None, "btrfs": [], "restic": None},
        "test_evidence": [],
    }


def write_manifest(root: Path, output: Path) -> dict[str, Any]:
    """Write a manifest atomically and return it with its output path."""
    payload = release_manifest(root)
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return {**payload, "output": str(destination)}
