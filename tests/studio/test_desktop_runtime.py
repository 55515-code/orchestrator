from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from substrate.studio.main import create_app
from substrate.studio.models import AppConfig
from substrate.studio.runtime_config import RuntimeOptions


def _desktop_client(tmp_path: Path) -> tuple[TestClient, RuntimeOptions]:
    bundled_codex = tmp_path / "bundled-backend" / "runtime" / "codex.cmd"
    bundled_codex.parent.mkdir(parents=True, exist_ok=True)
    bundled_codex.write_text("@echo off\r\n", encoding="utf-8")

    options = RuntimeOptions(
        mode="desktop",
        channel="dev",
        host="127.0.0.1",
        port=8787,
        data_dir=tmp_path / "desktop-data",
        session_token="desktop-session-token",
        bundled_codex_executable=str(bundled_codex),
        update_base_url="https://releases.example.internal/codex-scheduler-studio",
        version="0.1.0-rc1",
    )
    app = create_app(
        start_scheduler=False,
        runtime_options=options,
        db_url=f"sqlite:///{tmp_path / 'desktop-test.db'}",
    )
    return TestClient(app), options


def test_desktop_runtime_bootstrap_sets_cookie_and_local_defaults(tmp_path: Path) -> None:
    client, options = _desktop_client(tmp_path)

    with client:
        rejected = client.get("/desktop/bootstrap?token=wrong-token", follow_redirects=False)
        assert rejected.status_code == 403

        bootstrap = client.get("/desktop/bootstrap?token=desktop-session-token", follow_redirects=False)
        assert bootstrap.status_code == 303
        assert bootstrap.headers["location"] == "/"
        assert client.cookies.get("codex_desktop_session") == "desktop-session-token"

        runtime = client.get("/api/system/runtime")
        assert runtime.status_code == 200
        body = runtime.json()
        assert body["mode"] == "desktop"
        assert body["channel"] == "dev"
        assert body["update_capable"] is True
        assert body["bundled_codex_cli"] is True
        assert body["data_dir"] == str(options.data_dir)
        assert body["packaged_backend_status"] == "ok"
        assert body["diagnostic_code"] is None

        with client.app.state.session_factory() as session:
            config = session.query(AppConfig).filter(AppConfig.id == 1).one()
            assert config.codex_home == str(options.data_dir / "codex-home")
            assert config.codex_executable == str(tmp_path / "bundled-backend" / "runtime" / "codex.cmd")
            assert config.default_working_directory == str(Path.home())

        desktop_state = options.desktop_state_path(client.app.state.run_root.parent.parent)
        assert desktop_state.exists()
        payload = json.loads(desktop_state.read_text(encoding="utf-8"))
        assert payload["healthy"] is True
        assert payload["channel"] == "dev"

    shutdown_payload = json.loads(desktop_state.read_text(encoding="utf-8"))
    assert shutdown_payload["healthy"] is False


def test_desktop_restart_and_update_status_use_runtime_files(tmp_path: Path) -> None:
    client, options = _desktop_client(tmp_path)

    with client:
        denied = client.post("/api/system/restart-backend")
        assert denied.status_code == 403

        client.get("/desktop/bootstrap?token=desktop-session-token", follow_redirects=False)
        accepted = client.post("/api/system/restart-backend")
        assert accepted.status_code == 200
        assert accepted.json()["accepted"] is True

        restart_request = options.restart_request_path(client.app.state.run_root.parent.parent)
        assert restart_request.exists()
        restart_payload = json.loads(restart_request.read_text(encoding="utf-8"))
        assert restart_payload["channel"] == "dev"

        update_status = options.update_status_path(client.app.state.run_root.parent.parent)
        update_status.write_text(
            json.dumps(
                {
                    "last_check_at": "2026-03-31T23:30:00",
                    "last_result": "no_update",
                    "last_error": None,
                }
            ),
            encoding="utf-8",
        )

        response = client.get("/api/system/update-status")
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["channel"] == "dev"
        assert body["last_result"] == "no_update"


def test_desktop_runtime_reports_blocked_packaged_backend_from_env(tmp_path: Path, monkeypatch) -> None:
    client, _ = _desktop_client(tmp_path)
    monkeypatch.setenv("CODEX_PACKAGED_BACKEND_STATUS", "blocked")
    monkeypatch.setenv("CODEX_PACKAGED_BACKEND_DIAGNOSTIC", "desktop_binary_blocked")
    with client:
        runtime = client.get("/api/system/runtime")
        assert runtime.status_code == 200
        payload = runtime.json()
        assert payload["packaged_backend_status"] == "blocked"
        assert payload["diagnostic_code"] == "desktop_binary_blocked"
