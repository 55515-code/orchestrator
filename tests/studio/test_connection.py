from __future__ import annotations

from pathlib import Path

from substrate.studio.connection import codex_diagnostics
from substrate.studio.connection import start_device_auth
from substrate.studio.connection import test_connection as run_connection_test


def test_connection_adds_skip_git_check_outside_repo(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompleted:
        returncode = 0
        stdout = "connection_ok"
        stderr = ""

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return FakeCompleted()

    monkeypatch.setattr("substrate.studio.connection.subprocess.run", fake_run)

    result = run_connection_test("codex", None, str(tmp_path))
    assert result["ok"] is True
    command = captured["command"]
    assert isinstance(command, list)
    assert "--skip-git-repo-check" in command


def test_connection_skips_flag_inside_repo(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    captured: dict[str, object] = {}

    class FakeCompleted:
        returncode = 0
        stdout = "connection_ok"
        stderr = ""

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        return FakeCompleted()

    monkeypatch.setattr("substrate.studio.connection.subprocess.run", fake_run)

    result = run_connection_test("codex", None, str(tmp_path))
    assert result["ok"] is True
    command = captured["command"]
    assert isinstance(command, list)
    assert "--skip-git-repo-check" not in command


def test_connection_falls_back_when_configured_executable_missing(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    class FakeCompleted:
        returncode = 0
        stdout = "connection_ok"
        stderr = ""

    def fake_which(token: str) -> str | None:
        if token == "/missing/codex":
            return None
        if token == "codex":
            return "/usr/bin/codex"
        return None

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        return FakeCompleted()

    monkeypatch.setattr("substrate.studio.connection.shutil.which", fake_which)
    monkeypatch.setattr("substrate.studio.connection.subprocess.run", fake_run)

    result = run_connection_test("/missing/codex", None, str(tmp_path))
    assert result["ok"] is True
    assert "warning" in result
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == "/usr/bin/codex"


def test_codex_diagnostics_reports_fallback_warning(monkeypatch) -> None:
    class FakeCompleted:
        returncode = 0
        stdout = "codex 1.0.0"
        stderr = ""

    def fake_which(token: str) -> str | None:
        if token == "codex":
            return "/usr/bin/codex"
        return None

    monkeypatch.setattr("substrate.studio.connection.shutil.which", fake_which)
    monkeypatch.setattr("substrate.studio.connection.subprocess.run", lambda *args, **kwargs: FakeCompleted())

    diagnostics = codex_diagnostics("/broken/codex", None)
    assert diagnostics["installed"] is True
    assert diagnostics["resolved_executable"] == "/usr/bin/codex"
    assert diagnostics["warning"]


def test_start_device_auth_falls_back_when_configured_executable_missing(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeCompleted:
        returncode = 0
        stdout = "Visit https://example.com/device and enter ABCD-1234"
        stderr = ""

    def fake_which(token: str) -> str | None:
        if token == "/broken/codex":
            return None
        if token == "codex":
            return "/usr/bin/codex"
        return None

    def fake_run(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = command
        return FakeCompleted()

    monkeypatch.setattr("substrate.studio.connection.shutil.which", fake_which)
    monkeypatch.setattr("substrate.studio.connection.subprocess.run", fake_run)

    result = start_device_auth("/broken/codex", None)
    assert result["ok"] is True
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == "/usr/bin/codex"
