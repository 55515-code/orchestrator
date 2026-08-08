"""Btrfs storage optimization for the Local Agent Substrate.

Provides production-tested, substrate-aligned guidance and tooling for:

* Filesystem creation parameters (``mkfs.btrfs``) tuned for the substrate's
  mixed workload: many small state files, SQLite databases, git worktrees,
  ``uv`` environments, and compressible JSON/JSONL logs.
* Mount option tuning (``compress=zstd``, ``space_cache=v2``, ``noatime``,
  ``autodefrag``, ``nodatacow`` for volatile state) with explicit tradeoffs.
* Deduplication workflow via ``duperemove`` and ``btrfs filesystem defrag``,
  gated on tool availability and explicit ``apply`` flags.
* Snapshot layout that reuses ``workspace.yaml`` ``ignored_paths`` so Btrfs
  snapshots never capture volatile/generated directories.
* Compatibility validation against the substrate tooling stack (SQLite WAL,
  Docker storage driver, kernel and ``btrfs-progs`` versions, git config).

All mutations require an explicit ``apply=True`` flag; the module defaults to
read-only reporting and planning, consistent with the substrate autonomy tier
rules (Tier 2 actions always require an explicit human directive).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Minimum kernel that includes all recommended features (space_cache=v2,
# async discard, stable zstd compression, skinny-metadata support).
MIN_KERNEL = (5, 10)
# btrfs-progs >= 5.15 adds `-O no-holes` and stable duperemove behaviour.
MIN_BTRFS_PROGS = (5, 15)

# Default snapshot retention policy (kept in addition to the latest snapshot).
DEFAULT_KEEP_SNAPSHOTS = 7
DEFAULT_DEDUP_HASHFILE = "state/btrfs-dedup-hashes.db"

# Substrate directories that hold SQLite databases and high-frequency JSONL
# appends. These should live on a CoW-disabled (nodatacow) subvolume.
COW_DISABLED_DIRS = ("state", "memory")
# Substrate directories that benefit from CoW + compression + dedup.
COW_ENABLED_DIRS = ("artifacts", "resources", "docs", "substrate", "scripts")


@dataclass(slots=True)
class MkfsParameters:
    """Recommended ``mkfs.btrfs`` parameters with per-option rationale."""

    metadata_profile: str = "dup"
    data_profile: str = "single"
    nodesize: str = "16384"
    ssd: bool = True
    features: tuple[str, ...] = ("extref", "skinny-metadata", "no-holes")

    def to_args(self, device: str) -> list[str]:
        args = [
            "mkfs.btrfs",
            "-f",
            "-m",
            self.metadata_profile,
            "-d",
            self.data_profile,
            "-n",
            self.nodesize,
        ]
        if self.ssd:
            args.append("-s")
        args.append("-O")
        args.append(",".join(self.features))
        args.append(device)
        return args

    def as_dict(self) -> dict[str, Any]:
        return {
            "metadata_profile": self.metadata_profile,
            "data_profile": self.data_profile,
            "nodesize": self.nodesize,
            "ssd": self.ssd,
            "features": list(self.features),
        }


@dataclass(slots=True)
class MountOptions:
    """Recommended fstab mount options split by profile."""

    general: tuple[str, ...] = (
        "defaults",
        "ssd",
        "space_cache=v2",
        "noatime",
        "compress=zstd:1",
        "autodefrag",
    )
    # For SSD/NVMe: async discard avoids TRIM storms during snapshot bursts.
    ssd_async_discard: tuple[str, ...] = ("discard=async",)
    # For the volatile state/memory subvolumes: disable CoW on databases/logs.
    nodatacow: tuple[str, ...] = ("nodatacow",)

    def fstab_options(
        self, *, ssd: bool = True, cow_enabled: bool = True
    ) -> str:
        options = list(self.general)
        if ssd:
            options.append(self.ssd_async_discard[0])
        if not cow_enabled:
            options.append(self.nodatacow[0])
        return ",".join(options)

    def as_dict(self) -> dict[str, Any]:
        return {
            "general": list(self.general),
            "ssd_async_discard": list(self.ssd_async_discard),
            "nodatacow": list(self.nodatacow),
        }


@dataclass(slots=True)
class CompatibilityIssue:
    """A single compatibility finding between Btrfs settings and tooling."""

    severity: str  # "error" | "warning" | "info"
    component: str
    message: str
    action: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "component": self.component,
            "message": self.message,
            "action": self.action,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable int tuple.

    Handles common kernel/distro suffixes by taking only the leading digits of
    each component (e.g. ``5.19.0-arch1-1`` -> ``(5, 19, 0)``).
    """
    parts: list[int] = []
    for token in str(raw).strip().split("."):
        token = token.lstrip("vV")  # tolerate "v6.6.3" style prefixes
        digits = ""
        for char in token:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
        if len(parts) >= 3:
            break
    return tuple(parts)


def _run_command(
    command: list[str], *, timeout_seconds: int = 15
) -> subprocess.CompletedProcess[str] | None:
    """Run a command, returning None when the tool is unavailable."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def detect_btrfs(path: Path | str) -> dict[str, Any]:
    """Return filesystem facts for ``path`` without requiring btrfs tools.

    Detection uses ``st_dev`` plus ``/proc/self/mounts`` (and ``/proc/mounts``
    as fallback) so it works on any Linux system, even without ``btrfs-progs``.

    Returns a dict with keys: ``is_btrfs``, ``fstype``, ``mount_point``,
    ``device``, ``mount_options`` (list of strings), and ``path``.
    """
    target = Path(path).resolve()
    try:
        target_stat = target.stat()
    except OSError:
        return {"is_btrfs": False, "fstype": None, "error": "path not accessible"}

    dev = target_stat.st_dev
    mounts = _read_mounts()
    best: dict[str, Any] | None = None
    for entry in mounts:
        mnt_point = Path(entry["mount_point"])
        try:
            mnt_stat = mnt_point.stat()
        except OSError:
            continue
        if mnt_stat.st_dev != dev:
            continue
        # Prefer the deepest mount that contains the path.
        if best is None or len(mnt_point.parts) > len(Path(best["mount_point"]).parts):
            best = entry
    if best is None:
        return {
            "is_btrfs": False,
            "fstype": None,
            "mount_point": None,
            "device": None,
            "mount_options": [],
            "path": str(target),
        }
    return {
        "is_btrfs": best["fstype"] == "btrfs",
        "fstype": best["fstype"],
        "mount_point": best["mount_point"],
        "device": best["device"],
        "mount_options": best["options"],
        "path": str(target),
    }


def _read_mounts() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for filename in ("/proc/self/mounts", "/proc/mounts"):
        try:
            raw = Path(filename).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            device, mount_point, fstype, options = parts[0], parts[1], parts[2], parts[3]
            entries.append(
                {
                    "device": _unescape_mount(device),
                    "mount_point": _unescape_mount(mount_point),
                    "fstype": fstype,
                    "options": [opt for opt in options.split(",") if opt],
                }
            )
        break
    return entries


def _unescape_mount(value: str) -> str:
    """Decode the octal escapes used by the kernel in /proc/mounts."""
    if "\\" not in value:
        return value
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 3 < len(value) and value[index + 1 : index + 4].isdigit():
            out.append(chr(int(value[index + 1 : index + 4], 8)))
            index += 4
        else:
            out.append(char)
            index += 1
    return "".join(out)


def kernel_version() -> tuple[int, ...]:
    import platform

    return _parse_version(platform.release())


def btrfs_progs_version() -> tuple[int, ...] | None:
    completed = _run_command(["btrfs", "--version"])
    if completed is None or completed.returncode != 0:
        return None
    # e.g. "btrfs-progs v6.6.3"
    for token in completed.stdout.split():
        if token.lower().startswith("v") and token[1:2].isdigit():
            return _parse_version(token[1:])
    return None


def tool_available(tool: str) -> bool:
    return shutil.which(tool) is not None


def recommend_mkfs_params(*, ssd: bool = True, single_device: bool = True) -> MkfsParameters:
    """Return the production-tested mkfs baseline.

    * ``-m dup`` protects metadata (the substrate's SQLite state and git
      objects) against corruption on single-device filesystems at a modest
      space cost.
    * ``-d single`` avoids mirroring data that is regenerable (cache blobs,
      agent worktrees, generated artifacts).
    * 16 KiB nodes keep inode density high for the substrate's many small
      files (state JSON, JSONL logs, uv environments).
    * ``extref,skinny-metadata,no-holes`` harden link handling, shrink
      metadata, and improve ``df``/``du`` accuracy.
    """
    return MkfsParameters(
        metadata_profile="dup" if single_device else "raid1",
        data_profile="single" if single_device else "raid0",
        ssd=ssd,
    )


def recommend_mount_options(*, ssd: bool = True) -> MountOptions:
    """Return the production-tested mount baseline (see docs for tradeoffs)."""
    return MountOptions()


def subvolume_layout(root: Path | str) -> dict[str, Any]:
    """Plan a subvolume layout aligned with the substrate directory tree.

    Volatile state (SQLite databases, JSONL logs, chat sessions) goes on a
    CoW-disabled subvolume to prevent fragmentation and snapshot metadata
    explosion. Regenerable/compressible trees stay CoW-enabled so compression
    and dedup apply. Returns a dict of named plans; all paths are
    workspace-relative.
    """
    root = Path(root)
    return {
        "state": {
            "path": str(root / "state"),
            "subvolume": "@state",
            "cow_enabled": False,
            "mount_options": "nodatacow,noatime,space_cache=v2",
            "contents": "SQLite DBs, learning index, agent state, crypto vault",
        },
        "memory": {
            "path": str(root / "memory"),
            "subvolume": "@memory",
            "cow_enabled": False,
            "mount_options": "nodatacow,noatime,space_cache=v2",
            "contents": "dev-history.jsonl, run logs, community sim, task runs",
        },
        "workspace": {
            "path": str(root),
            "subvolume": "@workspace",
            "cow_enabled": True,
            "mount_options": "compress=zstd:1,autodefrag,noatime,space_cache=v2",
            "contents": "source code, docs, resources, artifacts, git objects",
        },
        "dedup_candidates": {
            "path": str(root / "artifacts"),
            "subvolume": "@artifacts",
            "cow_enabled": True,
            "mount_options": "compress=zstd:1,autodefrag",
            "contents": "generated binaries, ISOs, images — best dedup targets",
        },
    }


def snapshot_plan(
    root: Path | str, ignored_paths: list[str] | None = None
) -> dict[str, Any]:
    """Build a snapshot layout that excludes volatile/generated paths.

    Exclusions default to the substrate ``workspace.yaml`` ``ignored_paths``
    list (``.git``, ``.venv``, ``node_modules``, ``tmp``, ``downloads``,
    ``work``, ``tools``, ``site``) plus Btrfs/restic volatile dirs.
    """
    root_path = Path(root)
    exclusions = list(ignored_paths or [])
    defaults = [
        ".git",
        ".venv",
        ".direnv",
        "node_modules",
        "tmp",
        "downloads",
        "work",
        "tools",
        "site",
        "state/btrfs-dedup-hashes.db",
        "*.pyc",
        "__pycache__",
    ]
    for default in defaults:
        if default not in exclusions:
            exclusions.append(default)
    if "state" not in exclusions and "state/**" not in exclusions:
        # Volatile state is captured on its own CoW-disabled subvolume, so the
        # workspace snapshot excludes it to avoid double-storage.
        exclusions.append("state/**")
    if "memory/**" not in exclusions:
        exclusions.append("memory/**")
    return {
        "root": str(root_path),
        "exclusions": exclusions,
        "subvolumes": [
            "@workspace",
            "@state",
            "@memory",
            "@artifacts",
        ],
        "policy": {
            "keep_daily": DEFAULT_KEEP_SNAPSHOTS,
            "keep_weekly": 4,
            "read_only": True,
        },
    }


def compatibility_report(
    root: Path | str, *, fs_info: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate Btrfs recommendations against the substrate tooling stack.

    Checks cover the pieces that actually interact with the filesystem:

    * Kernel and ``btrfs-progs`` versions vs. minimums for the recommended
      features.
    * SQLite journal mode (WAL is required for the CoW/NORMAL pattern).
    * Docker storage driver (legacy ``btrfs`` driver is deprecated; overlay2
      on a btrfs backing store is fine).
    * ``duperemove`` availability for the dedup workflow.
    * Compressibility hints for the substrate's dominant file types.
    * Whether the target path is already on Btrfs (affects whether mkfs
      guidance is actionable or informational).

    Returns a dict with ``compatible``, ``issues``, and ``facts``.
    """
    fs = fs_info or detect_btrfs(root)
    issues: list[CompatibilityIssue] = []

    kernel = kernel_version()
    if kernel and kernel < MIN_KERNEL:
        issues.append(
            CompatibilityIssue(
                severity="error",
                component="kernel",
                message=(
                    f"Kernel {'.'.join(map(str, kernel))} predates the {'.'.join(map(str, MIN_KERNEL))} "
                    "minimum for space_cache=v2 / async discard / stable zstd."
                ),
                action="Upgrade the kernel before enabling the recommended mount options.",
            )
        )
    else:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="kernel",
                message=f"Kernel {'.'.join(map(str, kernel)) if kernel else 'unknown'} meets the minimum.",
            )
        )

    progs = btrfs_progs_version()
    if progs is None:
        issues.append(
            CompatibilityIssue(
                severity="error",
                component="btrfs-progs",
                message="btrfs command not found; btrfs-progs must be installed.",
                action="Install btrfs-progs (e.g. apt install btrfs-progs).",
            )
        )
    elif progs < MIN_BTRFS_PROGS:
        issues.append(
            CompatibilityIssue(
                severity="warning",
                component="btrfs-progs",
                message=(
                    f"btrfs-progs {'.'.join(map(str, progs))} is older than "
                    f"{'.'.join(map(str, MIN_BTRFS_PROGS))}; no-holes and duperemove "
                    "behavior may differ."
                ),
                action="Upgrade btrfs-progs to >= 5.15.",
            )
        )
    else:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="btrfs-progs",
                message=f"btrfs-progs {'.'.join(map(str, progs))} meets the minimum.",
            )
        )

    root_path = Path(root)
    db_path = root_path / "state" / "orchestrator.db"
    if db_path.exists():
        journal_mode = _sqlite_journal_mode(db_path)
        if journal_mode != "wal":
            issues.append(
                CompatibilityIssue(
                    severity="warning",
                    component="sqlite",
                    message=(
                        f"orchestrator.db journal_mode is {journal_mode!r}; WAL is required "
                        "for the recommended synchronous=NORMAL + nodatacow pattern."
                    ),
                    action="Enable WAL: PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                )
            )
        else:
            issues.append(
                CompatibilityIssue(
                    severity="info",
                    component="sqlite",
                    message="orchestrator.db already uses WAL journal mode.",
                )
            )
    else:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="sqlite",
                message="orchestrator.db not present yet; WAL will be applied on first init.",
            )
        )

    docker_driver = _docker_storage_driver()
    if docker_driver is None:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="docker",
                message="Docker not detected; no storage driver check performed.",
            )
        )
    elif docker_driver == "btrfs":
        issues.append(
            CompatibilityIssue(
                severity="error",
                component="docker",
                message=(
                    "Docker is using the legacy 'btrfs' storage driver, which is deprecated "
                    "and conflicts with CoW-heavy Btrfs layouts."
                ),
                action="Switch to overlay2 (set \"storage-driver\": \"overlay2\" in daemon.json).",
            )
        )
    else:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="docker",
                message=f"Docker storage driver is '{docker_driver}' (compatible).",
            )
        )

    if not tool_available("duperemove"):
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="duperemove",
                message="duperemove not installed; offline dedup step is unavailable.",
                action="Install duperemove to enable the weekly dedup workflow.",
            )
        )
    else:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="duperemove",
                message="duperemove is available for the dedup workflow.",
            )
        )

    if not fs.get("is_btrfs"):
        issues.append(
            CompatibilityIssue(
                severity="warning",
                component="filesystem",
                message=(
                    f"{root} is on {fs.get('fstype') or 'an unknown'} filesystem; mkfs "
                    "guidance applies only after migration."
                ),
                action="Plan a Btrfs migration (see scripts/btrfs_setup.sh) before applying.",
            )
        )
    else:
        issues.append(
            CompatibilityIssue(
                severity="info",
                component="filesystem",
                message=f"{root} is already on Btrfs ({fs.get('mount_point')}).",
            )
        )

    issues.sort(key=lambda issue: {"error": 0, "warning": 1, "info": 2}[issue.severity])
    return {
        "compatible": not any(issue.severity == "error" for issue in issues),
        "issues": [issue.as_dict() for issue in issues],
        "facts": {
            "kernel": ".".join(map(str, kernel)) if kernel else None,
            "btrfs_progs": ".".join(map(str, progs)) if progs else None,
            "docker_storage_driver": docker_driver,
            "duperemove": tool_available("duperemove"),
            "path_fs": fs,
        },
    }


def _sqlite_journal_mode(db_path: Path) -> str | None:
    import sqlite3

    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2) as conn:
            row = conn.execute("PRAGMA journal_mode;").fetchone()
            return str(row[0]) if row else None
    except (sqlite3.Error, OSError):
        return None


def _docker_storage_driver() -> str | None:
    docker = shutil.which("docker")
    if not docker:
        return None
    completed = _run_command([docker, "info", "--format", "{{.Driver}}"])
    if completed is None or completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def status_report(root: Path | str) -> dict[str, Any]:
    """Produce a JSON status report for the workspace storage layer.

    Combines filesystem detection, the current fstab mount options (best
    effort), the recommended plan, and the compatibility report into one
    substrate-idiomatic JSON payload.
    """
    root_path = Path(root)
    fs = detect_btrfs(root_path)
    compat = compatibility_report(root_path, fs_info=fs)
    fstab_options = _current_fstab_options(fs)
    return {
        "generated_at": _now_iso(),
        "workspace": str(root_path),
        "filesystem": {
            "is_btrfs": fs.get("is_btrfs", False),
            "fstype": fs.get("fstype"),
            "mount_point": fs.get("mount_point"),
            "device": fs.get("device"),
            "mount_options": fs.get("mount_options", []),
            "fstab_options": fstab_options,
        },
        "recommended_mkfs": recommend_mkfs_params().as_dict(),
        "recommended_mount": recommend_mount_options().as_dict(),
        "subvolume_layout": subvolume_layout(root_path),
        "snapshot_plan": snapshot_plan(root_path),
        "compatibility": compat,
    }


def _current_fstab_options(fs: dict[str, Any]) -> str | None:
    device = fs.get("device")
    mount_point = fs.get("mount_point")
    if not device or not mount_point:
        return None
    try:
        for line in Path("/etc/fstab").read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            # Match by UUID label, device path, or mount point.
            fstab_spec = parts[0]
            fstab_mount = parts[1]
            if fstab_mount == mount_point or fstab_spec == device:
                return parts[3]
    except OSError:
        return None
    return None


def run_maintenance(
    root: Path | str,
    *,
    apply: bool = False,
    dedup: bool = True,
    defrag: bool = True,
    compress_level: str = "zstd:1",
    hashfile: str = DEFAULT_DEDUP_HASHFILE,
    dry_run_output: bool = True,
) -> dict[str, Any]:
    """Run the dedup + defrag maintenance workflow.

    Read-only by default: returns the exact commands that would run plus the
    plan metadata. With ``apply=True`` the commands are executed via
    ``subprocess``. Each step is guarded:

    * Skip step when the tool is unavailable.
    * Skip when the target filesystem is not Btrfs.
    * ``defrag`` never targets CoW-disabled subvolumes' volatile paths.
    * Never runs against ``state/orchestrator.db`` or cache DBs while live.

    Returns a dict with per-step status and, when in dry-run mode, the planned
    command lines.
    """
    root_path = Path(root)
    fs = detect_btrfs(root_path)
    result: dict[str, Any] = {
        "generated_at": _now_iso(),
        "workspace": str(root_path),
        "apply": apply,
        "is_btrfs": fs.get("is_btrfs", False),
        "steps": [],
    }
    if not fs.get("is_btrfs"):
        result["error"] = "workspace is not on Btrfs; maintenance skipped."
        return result

    hashfile_path = root_path / hashfile if not Path(hashfile).is_absolute() else Path(hashfile)

    if dedup and tool_available("duperemove"):
        duperemove = shutil.which("duperemove")
        command = [
            duperemove,
            "-r",
            "-h",
            "-d",  # actually submit dedupes (btrfs/xfs only; guarded above)
            "-B",  # batched dedupe for large trees (ISOs, model weights)
            f"--hashfile={hashfile_path}",
            str(root_path / "artifacts"),
        ]
        if not apply:
            result["steps"].append(
                {
                    "step": "dedup",
                    "status": "planned",
                    "command": command,
                    "note": "duperemove full-tree scan; schedule during low I/O windows.",
                }
            )
        else:
            completed = _run_command(command, timeout_seconds=1800)
            result["steps"].append(
                {
                    "step": "dedup",
                    "status": "ok" if completed and completed.returncode == 0 else "failed",
                    "command": command,
                    "returncode": completed.returncode if completed else None,
                }
            )
    elif dedup:
        result["steps"].append(
            {
                "step": "dedup",
                "status": "skipped",
                "note": "duperemove not available.",
            }
        )

    if defrag:
        # Defrag+compress the CoW-enabled trees only; never the volatile dirs.
        targets = [
            root_path / "artifacts",
            root_path / "resources",
            root_path / "docs",
        ]
        targets = [target for target in targets if target.is_dir()]
        commands = [
            ["btrfs", "filesystem", "defrag", "-r", "-c", compress_level, str(target)]
            for target in targets
        ]
        if not apply:
            result["steps"].append(
                {
                    "step": "defrag",
                    "status": "planned",
                    "commands": commands,
                    "note": "Compress + defrag CoW-enabled trees; excludes state/memory.",
                }
            )
        else:
            statuses = []
            for command in commands:
                completed = _run_command(command, timeout_seconds=1800)
                statuses.append(
                    {
                        "command": command,
                        "status": "ok" if completed and completed.returncode == 0 else "failed",
                    }
                )
            result["steps"].append({"step": "defrag", "status": "ok", "runs": statuses})

    return result


def apply_nodatacow(paths: list[Path | str], *, apply: bool = False) -> dict[str, Any]:
    """Mark directories with the Btrfs ``noCoW`` attribute.

    For existing directories Btrfs uses the ``C`` attribute (``lsattr`` /
    ``chattr +C``). New files inherit the attribute only when the directory
    carries it *before* creation, so the correct order is: chattr the
    directory, then move data in. Returns planned/executed actions.
    """
    actions: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        actions.append(
            {
                "path": str(path),
                "command": ["chattr", "+C", str(path)],
                "note": "Directories only; files created afterward inherit noCoW.",
            }
        )
    if not apply:
        return {"apply": False, "actions": actions}

    results = []
    for action in actions:
        path = Path(action["path"])
        if not path.is_dir():
            results.append({"path": str(path), "status": "skipped", "note": "not a directory"})
            continue
        completed = _run_command(action["command"])
        results.append(
            {
                "path": str(path),
                "status": "ok" if completed and completed.returncode == 0 else "failed",
                "stderr": completed.stderr.strip() if completed else None,
            }
        )
    return {"apply": True, "actions": results}


def create_snapshot(
    source: Path | str,
    snapshot_root: Path | str,
    *,
    label: str | None = None,
    read_only: bool = True,
    apply: bool = False,
) -> dict[str, Any]:
    """Create a Btrfs subvolume snapshot.

    Read-only snapshots are the default; they avoid accidental writes into
    snapshot space and keep COW metadata growth bounded. With ``apply=False``
    only the command is reported.
    """
    source_path = Path(source)
    root_path = Path(snapshot_root)
    if label is None:
        label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = root_path / f"{source_path.name}-{label}"
    command = ["btrfs", "subvolume", "snapshot"]
    if read_only:
        command.append("-r")
    command.extend([str(source_path), str(destination)])
    if not apply:
        return {
            "apply": False,
            "source": str(source_path),
            "destination": str(destination),
            "command": command,
            "read_only": read_only,
        }
    completed = _run_command(command, timeout_seconds=120)
    return {
        "apply": True,
        "source": str(source_path),
        "destination": str(destination),
        "command": command,
        "status": "ok" if completed and completed.returncode == 0 else "failed",
        "stderr": completed.stderr.strip() if completed else None,
    }


def list_snapshots(subvolume: Path | str) -> dict[str, Any]:
    """List Btrfs snapshots of a subvolume (read-only)."""
    completed = _run_command(["btrfs", "subvolume", "list", "-s", str(subvolume)])
    if completed is None or completed.returncode != 0:
        return {"available": False, "snapshots": [], "error": "btrfs subvolume list unavailable"}
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return {
        "available": True,
        "snapshots": lines,
        "count": len(lines),
    }
