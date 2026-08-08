from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from substrate import btrfs
from substrate.btrfs import (
    CompatibilityIssue,
    MkfsParameters,
    MountOptions,
    _parse_version,
    apply_nodatacow,
    btrfs_progs_version,
    compatibility_report,
    create_snapshot,
    detect_btrfs,
    kernel_version,
    list_snapshots,
    recommend_mkfs_params,
    recommend_mount_options,
    run_maintenance,
    snapshot_plan,
    status_report,
    subvolume_layout,
    tool_available,
)


# ---------------------------------------------------------------------------
# Version parsing and helpers
# ---------------------------------------------------------------------------


def test_parse_version_handles_dotted_and_variants() -> None:
    assert _parse_version("6.6.3") == (6, 6, 3)
    assert _parse_version("v5.19.0-arch1-1") == (5, 19, 0)
    assert _parse_version("5.10") == (5, 10)
    assert _parse_version("unknown") == ()


def test_parse_version_compares_correctly() -> None:
    assert _parse_version("5.19") > _parse_version("5.10")
    assert _parse_version("7.1.61") > _parse_version("5.10")
    assert _parse_version("5.9.0") < _parse_version("5.10")


def test_tool_available_is_boolean() -> None:
    assert isinstance(tool_available("btrfs"), bool)
    # btrfs exists in the test environment only when installed; assert type only.
    assert tool_available("this-command-surely-does-not-exist-xyz") is False


def test_kernel_version_returns_tuple() -> None:
    version = kernel_version()
    assert isinstance(version, tuple)
    assert len(version) >= 1


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def test_recommend_mkfs_params_defaults() -> None:
    params = recommend_mkfs_params()
    assert params.metadata_profile == "dup"
    assert params.data_profile == "single"
    assert params.nodesize == "16384"
    assert params.ssd is True
    assert params.features == ("extref", "skinny-metadata", "no-holes")


def test_recommend_mkfs_params_multi_device() -> None:
    params = recommend_mkfs_params(single_device=False)
    assert params.metadata_profile == "raid1"
    assert params.data_profile == "raid0"


def test_mkfs_params_to_args() -> None:
    params = MkfsParameters()
    args = params.to_args("/dev/sdb1")
    assert args[0] == "mkfs.btrfs"
    assert "/dev/sdb1" in args
    assert "-O" in args
    features = args[args.index("-O") + 1]
    assert features == "extref,skinny-metadata,no-holes"
    assert "-s" in args  # ssd flag present


def test_recommend_mount_options_fstab_options() -> None:
    opts = recommend_mount_options()
    # CoW-enabled + SSD includes the async discard.
    fstab = opts.fstab_options(ssd=True, cow_enabled=True)
    assert "compress=zstd:1" in fstab
    assert "space_cache=v2" in fstab
    assert "discard=async" in fstab
    assert "nodatacow" not in fstab


def test_mount_options_nodatacow_variant() -> None:
    opts = MountOptions()
    fstab = opts.fstab_options(ssd=False, cow_enabled=False)
    assert "nodatacow" in fstab
    assert "discard=async" not in fstab


# ---------------------------------------------------------------------------
# Filesystem detection
# ---------------------------------------------------------------------------


def test_detect_btrfs_falls_back_gracefully(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "_read_mounts", lambda: [])
    result = detect_btrfs(tmp_path)
    assert result["is_btrfs"] is False
    assert result["fstype"] is None
    assert result["mount_point"] is None


def _patch_path_stat(monkeypatch, mapping: dict[str, object]) -> None:
    """Patch Path.stat only for exact paths in mapping; delegate otherwise."""
    real_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if str(self) in mapping:
            return mapping[str(self)]
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)


def test_detect_btrfs_matches_btrfs_mount(tmp_path: Path, monkeypatch) -> None:
    _patch_path_stat(
        monkeypatch,
        {
            str(tmp_path): SimpleNamespace(st_dev=99),
            "/": SimpleNamespace(st_dev=1),
            "/home": SimpleNamespace(st_dev=99),
        },
    )
    monkeypatch.setattr(
        btrfs,
        "_read_mounts",
        lambda: [
            {
                "device": "/dev/nvme0n1p2",
                "mount_point": "/",
                "fstype": "ext4",
                "options": ["rw"],
            },
            {
                "device": "/dev/nvme0n1p2",
                "mount_point": "/home",
                "fstype": "btrfs",
                "options": ["rw", "compress=zstd:1"],
            },
        ],
    )
    result = detect_btrfs(tmp_path)
    assert result["is_btrfs"] is True
    assert result["mount_point"] == "/home"
    assert result["device"] == "/dev/nvme0n1p2"
    assert "compress=zstd:1" in result["mount_options"]


def test_detect_btrfs_prefers_deepest_ancestor(tmp_path: Path, monkeypatch) -> None:
    _patch_path_stat(
        monkeypatch,
        {
            str(tmp_path): SimpleNamespace(st_dev=77),
            str(tmp_path / "sub"): SimpleNamespace(st_dev=77),
            "/home": SimpleNamespace(st_dev=77),
        },
    )
    monkeypatch.setattr(
        btrfs,
        "_read_mounts",
        lambda: [
            {
                "device": "/dev/sda1",
                "mount_point": "/home",
                "fstype": "btrfs",
                "options": ["rw"],
            },
            {
                "device": "/dev/sda1",
                "mount_point": "/home/ahron/codespace/state",
                "fstype": "btrfs",
                "options": ["rw", "nodatacow"],
            },
        ],
    )
    result = detect_btrfs(tmp_path / "sub")
    # The deeper mount is not an ancestor of the target; /home wins.
    assert result["mount_point"] == "/home"


def test_unescape_mount_decodes_octal() -> None:
    assert btrfs._unescape_mount("/home/ahron/my\\040codespace") == "/home/ahron/my codespace"
    assert btrfs._unescape_mount("/plain/path") == "/plain/path"


# ---------------------------------------------------------------------------
# Layout and snapshot planning
# ---------------------------------------------------------------------------


def test_subvolume_layout_structure(tmp_path: Path) -> None:
    layout = subvolume_layout(tmp_path)
    assert set(layout.keys()) == {"state", "memory", "workspace", "dedup_candidates"}
    assert layout["state"]["cow_enabled"] is False
    assert layout["memory"]["cow_enabled"] is False
    assert layout["workspace"]["cow_enabled"] is True
    assert layout["dedup_candidates"]["cow_enabled"] is True
    assert layout["state"]["path"] == str(tmp_path / "state")
    # Path values must be strings for JSON output.
    for plan in layout.values():
        assert isinstance(plan["path"], str)


def test_snapshot_plan_includes_ignored_paths(tmp_path: Path) -> None:
    plan = snapshot_plan(tmp_path, ignored_paths=[".venv", "node_modules", "tmp"])
    exclusions = plan["exclusions"]
    assert ".venv" in exclusions
    assert "node_modules" in exclusions
    assert "tmp" in exclusions
    # Defaults are always present.
    assert ".git" in exclusions
    # Volatile state/memory are excluded from workspace snapshots.
    assert "state/**" in exclusions
    assert "memory/**" in exclusions


def test_snapshot_plan_policy(tmp_path: Path) -> None:
    plan = snapshot_plan(tmp_path)
    assert plan["policy"]["keep_daily"] == 7
    assert plan["policy"]["read_only"] is True
    assert "@workspace" in plan["subvolumes"]


# ---------------------------------------------------------------------------
# Compatibility report
# ---------------------------------------------------------------------------


def test_compatibility_report_non_btrfs_fs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "kernel_version", lambda: (6, 6, 0))
    monkeypatch.setattr(btrfs, "btrfs_progs_version", lambda: (6, 6, 3))
    monkeypatch.setattr(btrfs, "tool_available", lambda tool: True)
    monkeypatch.setattr(btrfs, "_docker_storage_driver", lambda: "overlay2")
    monkeypatch.setattr(btrfs, "_sqlite_journal_mode", lambda path: None)
    fs_info = {"is_btrfs": False, "fstype": "ext4", "mount_point": None}
    report = compatibility_report(tmp_path, fs_info=fs_info)
    assert report["compatible"] is True  # warnings don't fail compatibility
    severities = [issue["severity"] for issue in report["issues"]]
    assert "warning" in severities


def test_compatibility_report_fails_on_old_kernel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "kernel_version", lambda: (4, 19))
    monkeypatch.setattr(btrfs, "btrfs_progs_version", lambda: (6, 6, 3))
    fs_info = {"is_btrfs": True, "fstype": "btrfs", "mount_point": "/"}
    report = compatibility_report(tmp_path, fs_info=fs_info)
    assert report["compatible"] is False
    errors = [i for i in report["issues"] if i["severity"] == "error"]
    assert any(i["component"] == "kernel" for i in errors)


def test_compatibility_report_fails_on_legacy_docker_driver(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(btrfs, "kernel_version", lambda: (6, 6, 0))
    monkeypatch.setattr(btrfs, "btrfs_progs_version", lambda: (6, 6, 3))
    monkeypatch.setattr(btrfs, "tool_available", lambda tool: True)
    monkeypatch.setattr(btrfs, "_docker_storage_driver", lambda: "btrfs")
    monkeypatch.setattr(btrfs, "_sqlite_journal_mode", lambda path: "wal")
    fs_info = {"is_btrfs": True, "fstype": "btrfs", "mount_point": "/"}
    report = compatibility_report(tmp_path, fs_info=fs_info)
    assert report["compatible"] is False
    errors = [i for i in report["issues"] if i["severity"] == "error"]
    assert any(i["component"] == "docker" for i in errors)


def test_compatibility_report_warns_on_missing_btrfs_progs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(btrfs, "kernel_version", lambda: (6, 6, 0))
    monkeypatch.setattr(btrfs, "btrfs_progs_version", lambda: None)
    fs_info = {"is_btrfs": True, "fstype": "btrfs", "mount_point": "/"}
    report = compatibility_report(tmp_path, fs_info=fs_info)
    assert report["compatible"] is False
    errors = [i for i in report["issues"] if i["severity"] == "error"]
    assert any(i["component"] == "btrfs-progs" for i in errors)


def test_compatibility_report_sqlite_wal_detection(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(btrfs, "kernel_version", lambda: (6, 6, 0))
    monkeypatch.setattr(btrfs, "btrfs_progs_version", lambda: (6, 6, 3))
    monkeypatch.setattr(btrfs, "tool_available", lambda tool: True)
    monkeypatch.setattr(btrfs, "_docker_storage_driver", lambda: None)
    # Simulate a live WAL database.
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    db_path = state_dir / "orchestrator.db"
    db_path.write_text("placeholder")
    monkeypatch.setattr(btrfs, "_sqlite_journal_mode", lambda path: "wal")
    fs_info = {"is_btrfs": True, "fstype": "btrfs", "mount_point": "/"}
    report = compatibility_report(tmp_path, fs_info=fs_info)
    sqlite_issues = [i for i in report["issues"] if i["component"] == "sqlite"]
    assert any("WAL" in i["message"] for i in sqlite_issues)
    assert all(i["severity"] == "info" for i in sqlite_issues)


def test_compatibility_issue_sort_order() -> None:
    issues = [
        CompatibilityIssue("info", "a", "info msg"),
        CompatibilityIssue("error", "b", "error msg"),
        CompatibilityIssue("warning", "c", "warn msg"),
    ]
    issues.sort(key=lambda issue: {"error": 0, "warning": 1, "info": 2}[issue.severity])
    assert [issue.severity for issue in issues] == ["error", "warning", "info"]


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------


def test_status_report_is_json_serializable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "_now_iso", lambda: "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(btrfs, "detect_btrfs", lambda path: {
        "is_btrfs": True,
        "fstype": "btrfs",
        "mount_point": "/home",
        "device": "/dev/nvme0n1p2",
        "mount_options": ["rw", "compress=zstd:1"],
        "path": str(tmp_path),
    })
    monkeypatch.setattr(btrfs, "compatibility_report", lambda root, fs_info=None: {
        "compatible": True,
        "issues": [],
        "facts": {},
    })
    monkeypatch.setattr(btrfs, "_current_fstab_options", lambda fs: "defaults,noatime")
    report = status_report(tmp_path)
    # Must serialize without Path errors.
    payload = json.dumps(report)
    assert "recommended_mkfs" in payload
    assert report["filesystem"]["is_btrfs"] is True
    assert report["snapshot_plan"]["policy"]["read_only"] is True


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


def test_run_maintenance_skips_on_non_btrfs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "detect_btrfs", lambda path: {
        "is_btrfs": False,
        "fstype": "ext4",
        "mount_point": None,
        "device": None,
        "mount_options": [],
        "path": str(tmp_path),
    })
    result = run_maintenance(tmp_path, apply=False)
    assert result["steps"] == []
    assert "error" in result


def test_run_maintenance_dry_run_plans_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "detect_btrfs", lambda path: {
        "is_btrfs": True,
        "fstype": "btrfs",
        "mount_point": "/",
        "device": "/dev/sda1",
        "mount_options": [],
        "path": str(tmp_path),
    })
    monkeypatch.setattr(btrfs, "tool_available", lambda tool: tool == "duperemove")
    monkeypatch.setattr(
        btrfs.shutil, "which", lambda tool: f"/usr/bin/{tool}"
    )
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "docs").mkdir()
    result = run_maintenance(tmp_path, apply=False)
    steps = {step["step"]: step for step in result["steps"]}
    assert steps["dedup"]["status"] == "planned"
    assert "duperemove" in steps["dedup"]["command"][0]
    assert steps["defrag"]["status"] == "planned"
    assert len(steps["defrag"]["commands"]) == 3
    # Dry-run must never execute.
    assert result["apply"] is False


def test_run_maintenance_defrag_excludes_state_and_memory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(btrfs, "detect_btrfs", lambda path: {
        "is_btrfs": True,
        "fstype": "btrfs",
        "mount_point": "/",
        "device": "/dev/sda1",
        "mount_options": [],
        "path": str(tmp_path),
    })
    monkeypatch.setattr(btrfs, "tool_available", lambda tool: False)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "resources").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "memory").mkdir()
    result = run_maintenance(tmp_path, apply=False)
    defrag_step = next(step for step in result["steps"] if step["step"] == "defrag")
    joined = " ".join(" ".join(cmd) for cmd in defrag_step["commands"])
    assert "state" not in joined
    assert "memory" not in joined


def test_run_maintenance_apply_executes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "detect_btrfs", lambda path: {
        "is_btrfs": True,
        "fstype": "btrfs",
        "mount_point": "/",
        "device": "/dev/sda1",
        "mount_options": [],
        "path": str(tmp_path),
    })
    monkeypatch.setattr(btrfs, "tool_available", lambda tool: False)

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(btrfs, "_run_command", fake_run)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "docs").mkdir()
    result = run_maintenance(tmp_path, apply=True)
    assert result["apply"] is True
    defrag_step = next(step for step in result["steps"] if step["step"] == "defrag")
    assert defrag_step["status"] == "ok"


# ---------------------------------------------------------------------------
# CoW controls and snapshots
# ---------------------------------------------------------------------------


def test_apply_nodatacow_dry_run(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    result = apply_nodatacow([tmp_path / "state"], apply=False)
    assert result["apply"] is False
    assert result["actions"][0]["command"][0] == "chattr"
    assert result["actions"][0]["command"][1] == "+C"


def test_apply_nodatacow_skips_missing_dirs(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(btrfs, "_run_command", fake_run)
    result = apply_nodatacow([tmp_path / "missing"], apply=True)
    assert result["actions"][0]["status"] == "skipped"


def test_apply_nodatacow_apply(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "state").mkdir()

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(btrfs, "_run_command", fake_run)
    result = apply_nodatacow([tmp_path / "state"], apply=True)
    assert result["apply"] is True
    assert result["actions"][0]["status"] == "ok"


def test_create_snapshot_dry_run_defaults_read_only(tmp_path: Path) -> None:
    source = tmp_path / "workspace"
    result = create_snapshot(source, tmp_path / ".snapshots", apply=False)
    assert result["apply"] is False
    assert result["read_only"] is True
    assert result["command"][0] == "btrfs"
    assert "-r" in result["command"]
    assert result["destination"].startswith(str(tmp_path / ".snapshots"))
    assert result["destination"].endswith("workspace-") is False


def test_create_snapshot_apply(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "workspace"
    source.mkdir()

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(btrfs, "_run_command", fake_run)
    result = create_snapshot(source, tmp_path / ".snapshots", apply=True)
    assert result["status"] == "ok"
    assert result["apply"] is True


def test_list_snapshots_graceful_unavailable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(btrfs, "_run_command", lambda command, timeout_seconds=15: None)
    result = list_snapshots(tmp_path)
    assert result["available"] is False
    assert result["snapshots"] == []


def test_list_snapshots_available(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ID 256 gen 42 top level 5 path workspace-20260808T000000Z\n")

    monkeypatch.setattr(btrfs, "_run_command", fake_run)
    result = list_snapshots(tmp_path)
    assert result["available"] is True
    assert result["count"] == 1


# ---------------------------------------------------------------------------
# Integration: real SQLite WAL via the hardened cache store
# ---------------------------------------------------------------------------


def test_cache_store_uses_wal_mode(tmp_path: Path) -> None:
    """The hardened cache store must keep WAL + NORMAL + busy_timeout."""
    from substrate.cache_store import CacheStore

    store = CacheStore(tmp_path / "cache")
    conn = store._connect()
    try:
        journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    finally:
        conn.close()
    assert journal == "wal"
    assert sync == 1  # NORMAL
    assert busy == 5000


def test_orchestrator_db_pragmas(tmp_path: Path) -> None:
    from substrate.db import OrchestratorDB

    db = OrchestratorDB(tmp_path / "state" / "orchestrator.db")
    conn = db._connect()
    try:
        journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        sync = conn.execute("PRAGMA synchronous;").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    finally:
        conn.close()
    assert journal == "wal"
    assert sync == 1  # NORMAL
    assert busy == 5000
