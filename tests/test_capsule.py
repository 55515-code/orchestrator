from __future__ import annotations

import json
from pathlib import Path

from substrate import capsule


def test_probe_is_read_only_and_secret_free(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "workspace.yaml").write_text("repositories: {}\n")
    monkeypatch.setattr(capsule.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(capsule, "_filesystem_type", lambda path: "btrfs")
    monkeypatch.setattr(capsule, "_version", lambda command, root: "1.0")
    monkeypatch.setattr(capsule, "_port_available", lambda port, host="127.0.0.1": port != 8090)
    monkeypatch.setattr(
        capsule,
        "_run",
        lambda command, cwd, timeout=8: {"ok": True, "exit_code": 0, "output": "true"},
    )

    result = capsule.probe_capsule(tmp_path)

    assert result["mode"] == "read-only"
    assert result["filesystem"]["btrfs"] is True
    assert result["ports"]["current_gateway"]["available"] is False
    assert "token" not in json.dumps(result).lower()


def test_plan_blocks_missing_required_tools(tmp_path: Path, monkeypatch) -> None:
    probe = {
        "tools": {"podman": {"available": False}},
        "rootless_podman": False,
        "ports": {
            "candidate_gateway": {"available": True},
            "candidate_panel": {"available": True},
        },
    }
    monkeypatch.setattr(capsule, "probe_capsule", lambda root: probe)

    result = capsule.plan_capsule(tmp_path)

    assert result["ready_for_disposable_capsule"] is False
    assert {item["code"] for item in result["blocked"]} == {
        "missing_tools",
        "podman_not_rootless",
    }
    assert result["live_gateway_untouched"] is True


def test_manifest_has_checksums_and_no_secret_values(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "compose.yaml").write_text("services: {}\n")
    monkeypatch.setattr(
        capsule,
        "probe_capsule",
        lambda root: {"git": {"commit": "abc", "dirty": False}, "versions": {"podman": "6"}},
    )

    result = capsule.write_manifest(tmp_path, tmp_path / "out" / "release.json")
    written = json.loads((tmp_path / "out" / "release.json").read_text())

    assert written["schema_version"] == 1
    assert written["config_sha256"]["deploy/compose.yaml"]
    assert written["images"]["openclaw"]["digest_required"] is True
    assert all("=" not in reference for reference in written["secret_references"])
    assert result["output"].endswith("release.json")


def test_cli_parser_exposes_capsule_commands() -> None:
    from substrate.cli import _build_parser

    parser = _build_parser()
    assert parser.parse_args(["capsule", "probe"]).capsule_command == "probe"
    assert parser.parse_args(["capsule", "plan"]).capsule_command == "plan"
    args = parser.parse_args(["capsule", "manifest", "--output", "release.json"])
    assert args.output == Path("release.json")
