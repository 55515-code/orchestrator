#!/usr/bin/env python3
"""Rootless-first local workload fabric for the codespace."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import socket
import subprocess
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "fabric.json"


def load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        config = json.load(stream)
    if config.get("version") != 1:
        raise SystemExit(f"unsupported fabric config version: {config.get('version')}")
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise SystemExit("fabric config requires profiles")
    for section in ("profiles", "mcps"):
        for name, entry in config.get(section, {}).items():
            backend = entry.get("backend")
            if backend not in {"local", "container", "vm"}:
                raise SystemExit(f"{section}.{name} has unsupported backend: {backend}")
            if backend == "container":
                image = str(entry.get("image", ""))
                if not image:
                    raise SystemExit(f"{section}.{name} requires an image")
                if image.startswith(("docker.io/", "quay.io/", "ghcr.io/")) and "@sha256:" not in image:
                    raise SystemExit(
                        f"{section}.{name} remote image must be digest pinned: {image}"
                    )
            for env_name in entry.get("pass_env", []):
                if not isinstance(env_name, str) or not env_name.replace("_", "").isalnum():
                    raise SystemExit(f"{section}.{name} has invalid pass_env name")


def bytes_available(path: Path) -> int:
    return shutil.disk_usage(path).free


def memory_available() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable not found")


def running(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=False, text=True, capture_output=True)


def discover_projects(
    root: Path, max_depth: int = 4, overrides: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    overrides = overrides or {}
    skip = {".git", ".repo", "node_modules", ".venv", "out", "dist"}
    for current, dirs, _files in os.walk(root):
        relative = Path(current).relative_to(root)
        if len(relative.parts) > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [name for name in dirs if name not in skip]
        current_path = Path(current)
        is_git = (current_path / ".git").is_dir()
        is_repo_checkout = (current_path / ".repo").is_dir()
        if not is_git and not is_repo_checkout:
            continue
        dirs[:] = [name for name in dirs if name != ".git"]
        markers = {
            "container": any(
                (current_path / name).exists()
                for name in ("Containerfile", "Dockerfile", "compose.yaml")
            ),
            "python": (current_path / "pyproject.toml").exists(),
            "node": (current_path / "package.json").exists(),
            "rust": (current_path / "Cargo.toml").exists(),
            "buildroot": (current_path / "buildroot").is_dir(),
        }
        recommendation = "container-arch-build" if markers["buildroot"] else (
            "container-ubuntu" if any(markers.values()) else "local-light"
        )
        relative_name = "." if current_path == root else str(current_path.relative_to(root))
        recommendation = overrides.get(relative_name, recommendation)
        projects.append(
            {
                "name": current_path.name,
                "path": str(current_path),
                "markers": [name for name, present in markers.items() if present],
                "recommended_profile": recommendation,
            }
        )
        # A Git checkout or Android repo checkout is one schedulable workload.
        # Only the codespace root is a container for other independent projects.
        if current_path != root:
            dirs[:] = []
    return sorted(projects, key=lambda project: project["path"])


def check_capacity(config: dict[str, Any], profile: dict[str, Any], workspace: Path) -> None:
    policy = config["policy"]
    cpu_total = os.cpu_count() or 1
    cpu_limit = int(profile["cpus"])
    if cpu_limit > cpu_total - int(policy["reserved_host_cpus"]):
        raise SystemExit(
            f"profile requests {cpu_limit} CPUs but policy permits at most "
            f"{cpu_total - int(policy['reserved_host_cpus'])}"
        )
    minimum_free = int(policy["minimum_free_disk_gib"]) * 1024**3
    if bytes_available(workspace) < minimum_free:
        raise SystemExit("free disk is below the fabric safety threshold")
    requested_memory = str(profile["memory"]).lower()
    multiplier = 1024**3 if requested_memory.endswith("g") else 1024**2
    requested_bytes = int(requested_memory[:-1]) * multiplier
    reserve_bytes = int(policy["reserved_host_memory_gib"]) * 1024**3
    if requested_bytes + reserve_bytes > memory_available():
        raise SystemExit("profile memory plus host reserve exceeds available memory")


def container_command(
    profile: dict[str, Any], workspace: Path | None, command: list[str], interactive: bool = False
) -> list[str]:
    args = [
        str(HERE / "container-run.sh"),
        "--cpu", str(profile["cpus"]),
        "--memory", str(profile["memory"]),
        "--pids", str(profile["pids"]),
        "--network", str(profile.get("network", "pasta")),
    ]
    if profile.get("kvm"):
        args.append("--kvm")
    if workspace:
        args.extend(["--workspace", str(workspace)])
    args.extend(["--", str(profile["image"])])
    if interactive:
        # container-run currently uses podman run without -i; MCPs need stdio.
        args = [
            "podman", "run", "--rm", "-i",
            "--cpus", str(profile["cpus"]),
            "--memory", str(profile["memory"]),
            "--pids-limit", str(profile["pids"]),
            "--network", str(profile.get("network", "pasta")),
            "--security-opt", "no-new-privileges",
        ]
        for env_name in profile.get("pass_env", []):
            args.extend(["--env", env_name])
        args.append(str(profile["image"]))
    return args + command


def run_profile(
    config: dict[str, Any], name: str, workspace: Path, command: list[str], dry_run: bool
) -> int:
    try:
        profile = config["profiles"][name]
    except KeyError:
        raise SystemExit(f"unknown profile: {name}") from None
    workspace = workspace.resolve(strict=True)
    check_capacity(config, profile, workspace)
    backend = profile["backend"]
    if backend == "container":
        invocation = container_command(profile, workspace, command)
    elif backend == "local":
        invocation = [
            "systemd-run", "--user", "--scope", "--quiet", "--collect",
            "-p", f"CPUQuota={int(profile['cpus']) * 100}%",
            "-p", f"MemoryMax={profile['memory']}",
            "-p", f"TasksMax={profile['pids']}",
            "--working-directory", str(workspace),
            "--",
        ] + command
    elif backend == "vm":
        uri = str(profile["uri"])
        domain = str(profile["name"])
        state = running(["virsh", "--connect", uri, "domstate", domain])
        if state.returncode:
            raise SystemExit(
                f"VM {domain} is not provisioned; run {HERE / 'vm-provision.sh'} --apply"
            )
        if state.stdout.strip() != "running":
            start = subprocess.run(
                ["virsh", "--connect", uri, "start", domain], check=False
            )
            if start.returncode:
                return start.returncode
        host = str(profile["ssh_host"])
        port = int(profile["ssh_port"])
        if dry_run:
            print(
                json.dumps(
                    [
                        "ssh", "-p", str(port), "-i", str(profile["identity"]),
                        f"{profile['ssh_user']}@{host}", shlex.join(command),
                    ]
                )
            )
            return 0
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=2):
                    break
            except OSError:
                time.sleep(2)
        else:
            raise SystemExit(f"VM {domain} did not expose SSH within 240 seconds")
        known_hosts = Path(str(profile["identity"])).parent / "known_hosts"
        ssh_base = [
            "ssh",
            "-p", str(port),
            "-i", str(profile["identity"]),
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=3",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={known_hosts}",
            f"{profile['ssh_user']}@{host}",
        ]
        while time.monotonic() < deadline:
            ready = running(ssh_base + ["true"])
            if ready.returncode == 0:
                break
            time.sleep(2)
        else:
            raise SystemExit(f"VM {domain} SSH did not become ready within 240 seconds")
        configured_root = Path(config["workspace_root"]).resolve()
        try:
            relative = workspace.relative_to(configured_root)
            slug = "codespace" if not relative.parts else "--".join(relative.parts)
        except ValueError:
            slug = workspace.name
        remote_workspace = f"{profile['remote_root']}/{slug}"
        remote_command = (
            f"mkdir -p {shlex.quote(remote_workspace)} && "
            f"cd {shlex.quote(remote_workspace)} && "
            f"exec {shlex.join(command)}"
        )
        invocation = ssh_base + [remote_command]
    else:
        raise SystemExit(f"unsupported backend: {backend}")
    if dry_run:
        print(json.dumps(invocation))
        return 0
    return subprocess.run(invocation, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("status")
    commands.add_parser("projects")
    commands.add_parser("profiles")
    commands.add_parser("mcps")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--profile")
    run_parser.add_argument("--project")
    run_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    mcp_parser = commands.add_parser("mcp-run")
    mcp_parser.add_argument("name")
    vm_parser = commands.add_parser("vm")
    vm_parser.add_argument("operation", choices=("status", "start", "stop"))
    vm_parser.add_argument("--profile", default="vm-rootless")
    args = parser.parse_args()
    config = load_config(args.config)
    root = Path(config["workspace_root"])

    if args.action == "status":
        podman_ps = running(["podman", "ps", "--quiet"])
        vm_state = running(
            ["virsh", "--connect", "qemu:///session", "domstate", "fabric-ubuntu"]
        )
        output = {
            "workspace": str(root),
            "cpu_total": os.cpu_count(),
            "memory_available_gib": round(memory_available() / 1024**3, 1),
            "disk_available_gib": round(bytes_available(root) / 1024**3, 1),
            "podman": running(["podman", "info", "--format", "{{.Version.Version}}"]).stdout.strip(),
            "containers_running": len(
                [line for line in podman_ps.stdout.splitlines() if line]
            ),
            "libvirt_uri": running(["virsh", "uri"]).stdout.strip(),
            "fabric_vm_state": (
                vm_state.stdout.strip() if vm_state.returncode == 0 else "not-provisioned"
            ),
            "projects": len(discover_projects(root, overrides=config.get("project_overrides"))),
            "profiles": len(config["profiles"]),
            "mcps": len(config["mcps"]),
        }
        print(json.dumps(output, indent=2))
        return 0
    if args.action == "projects":
        print(
            json.dumps(
                discover_projects(root, overrides=config.get("project_overrides")),
                indent=2,
            )
        )
        return 0
    if args.action == "profiles":
        print(json.dumps(config["profiles"], indent=2))
        return 0
    if args.action == "mcps":
        print(json.dumps(config["mcps"], indent=2))
        return 0
    if args.action == "run":
        if not args.command:
            parser.error("run requires a command after --")
        command = args.command[1:] if args.command[0] == "--" else args.command
        workspace = args.workspace
        recommended = None
        if args.project:
            projects = discover_projects(root, overrides=config.get("project_overrides"))
            matches = [
                project
                for project in projects
                if project["name"] == args.project or project["path"] == args.project
            ]
            if len(matches) != 1:
                raise SystemExit(
                    f"project selector must match exactly once: {args.project} "
                    f"(matches={len(matches)})"
                )
            workspace = Path(matches[0]["path"])
            recommended = matches[0]["recommended_profile"]
        profile = args.profile or recommended or config["policy"]["default_profile"]
        return run_profile(config, profile, workspace, command, args.dry_run)
    if args.action == "mcp-run":
        try:
            mcp = config["mcps"][args.name]
        except KeyError:
            raise SystemExit(f"unknown MCP: {args.name}") from None
        check_capacity(config, mcp, root)
        invocation = container_command(mcp, None, list(mcp["command"]), interactive=True)
        os.execvp(invocation[0], invocation)
    if args.action == "vm":
        try:
            profile = config["profiles"][args.profile]
        except KeyError:
            raise SystemExit(f"unknown profile: {args.profile}") from None
        if profile["backend"] != "vm":
            raise SystemExit(f"profile is not a VM: {args.profile}")
        base = ["virsh", "--connect", str(profile["uri"])]
        domain = str(profile["name"])
        if args.operation == "status":
            return subprocess.run(base + ["dominfo", domain], check=False).returncode
        if args.operation == "start":
            state = running(base + ["domstate", domain])
            if state.returncode == 0 and state.stdout.strip() == "running":
                print(f"{domain} is already running")
                return 0
            return subprocess.run(base + ["start", domain], check=False).returncode
        return subprocess.run(base + ["shutdown", domain], check=False).returncode
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
