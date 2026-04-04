from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from substrate.studio.main import create_app
from substrate.studio.models import AppConfig
from substrate.studio.preflight import CheckResult


def _payload(name: str = "daily-check") -> dict:
    return {
        "name": name,
        "mode": "exec",
        "enabled": True,
        "schedule_type": "cron",
        "cron_expr": "*/30 * * * *",
        "interval_minutes": None,
        "prompt": "Summarize changes.",
        "sandbox": "read-only",
        "working_directory": ".",
        "timeout_seconds": 1800,
        "cloud_env_id": None,
        "attempts": 1,
        "codex_args": None,
        "env_json": None,
        "notify_email_enabled": False,
        "notify_email_to": None,
    }


def _cloud_payload(name: str = "cloud-check") -> dict:
    payload = _payload(name=name)
    payload["mode"] = "cloud_exec"
    payload["cloud_env_id"] = "env_test_123"
    payload["attempts"] = 1
    return payload


def _client(tmp_path: Path) -> TestClient:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    app = create_app(start_scheduler=False, db_url=db_url)
    return TestClient(app)


def test_create_list_and_update_job(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post("/api/jobs", json=_payload()).json()
    assert created["name"] == "daily-check"

    listed = client.get("/api/jobs").json()
    assert len(listed) == 1
    assert listed[0]["name"] == "daily-check"

    update_payload = _payload(name="daily-check-updated")
    updated = client.put(f"/api/jobs/{created['id']}", json=update_payload).json()
    assert updated["name"] == "daily-check-updated"


def test_index_page_loads(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "Codex Scheduler Studio" in response.text


def test_toggle_enabled(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = client.post("/api/jobs", json=_payload()).json()
    toggled = client.patch(f"/api/jobs/{created['id']}/enabled", json={"enabled": False}).json()
    assert toggled["enabled"] is False


def test_reject_invalid_job_env_json(tmp_path: Path) -> None:
    client = _client(tmp_path)
    payload = _payload()
    payload["name"] = "bad-json"
    payload["env_json"] = "{bad"
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 422


def test_run_now_with_stubbed_runner(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)
    created = client.post("/api/jobs", json=_payload()).json()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    class FakeRun:
        id = 10
        job_id = created["id"]
        status = "completed"
        return_code = 0
        command = "codex exec ..."
        started_at = now
        finished_at = now
        stdout_path = "stdout.log"
        stderr_path = "stderr.log"
        metadata_path = "meta.json"
        message = "ok"
        failure_category = None
        diagnostic_code = "cloud_probe"
        retryable = False
        notification_status = "sent"
        notification_error = None
        notification_sent_at = now
        notification_recipient = "adarnell@concepts2code.com"

    monkeypatch.setattr(
        "substrate.studio.main.execute_now",
        lambda session, job, run_root, orchestrator: FakeRun(),
    )

    run_response = client.post(f"/api/jobs/{created['id']}/run")
    assert run_response.status_code == 200
    body = run_response.json()
    assert body["status"] == "completed"
    assert body["return_code"] == 0
    assert body["diagnostic_code"] == "cloud_probe"


def test_settings_roundtrip_and_api_key(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    secret_state = {"value": None}

    def fake_save(secret_ref: str, value: str) -> None:
        secret_state["value"] = value

    def fake_clear(secret_ref: str) -> None:
        secret_state["value"] = None

    monkeypatch.setattr("substrate.studio.main.save_secret", fake_save)
    monkeypatch.setattr("substrate.studio.main.clear_secret", fake_clear)

    settings_payload = {
        "codex_executable": "C:/Tools/codex.exe",
        "codex_home": "C:/codex_home",
        "default_working_directory": "C:/repo",
        "default_cloud_env_id": "env-default-1",
        "api_key_env_var": "OPENAI_API_KEY",
        "global_env_json": '{"HTTP_PROXY":"http://proxy"}',
        "deployment_task_name": "CodexHost",
        "deployment_host": "127.0.0.1",
        "deployment_port": 8787,
        "deployment_user": "AzureAD\\\\Tester",
        "auth_mode": "chatgpt_account",
        "smtp_host": "smtp.sendgrid.net",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "apikey",
        "smtp_from_email": "noreply@example.com",
        "notifications_enabled": True,
        "default_notification_to": "adarnell@concepts2code.com",
    }
    put_response = client.put("/api/settings", json=settings_payload)
    assert put_response.status_code == 200
    assert put_response.json()["codex_executable"] == "C:/Tools/codex.exe"

    with client.app.state.session_factory() as session:
        config = session.query(AppConfig).filter(AppConfig.id == 1).one()
        assert config.default_cloud_env_id == "env-default-1"

    api_key_response = client.post("/api/settings/api-key", json={"api_key": "sk-test-1234567890"})
    assert api_key_response.status_code == 200
    assert secret_state["value"] == "sk-test-1234567890"

    delete_response = client.delete("/api/settings/api-key")
    assert delete_response.status_code == 200
    assert secret_state["value"] is None


def test_settings_auto_heal_stale_codex_executable(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    with client.app.state.session_factory() as session:
        config = session.query(AppConfig).filter(AppConfig.id == 1).one()
        config.codex_executable = "/tmp/definitely-missing-codex"
        session.add(config)
        session.commit()

    def fake_which(token: str) -> str | None:
        if token == "codex":
            return "/usr/bin/codex"
        return None

    monkeypatch.setattr(
        "substrate.studio.rc2.services.settings_service.shutil.which",
        fake_which,
    )

    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["codex_executable"] == "codex"


def test_deployment_endpoints(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    monkeypatch.setattr("substrate.studio.main.install_headless_task", lambda request: {"task_name": request.task_name, "status": "installed"})
    monkeypatch.setattr("substrate.studio.main.get_task_status", lambda task_name: {"exists": True, "state": "Ready", "taskName": task_name})
    monkeypatch.setattr("substrate.studio.main.uninstall_headless_task", lambda task_name: {"task_name": task_name, "status": "removed"})

    install_payload = {
        "task_name": "CodexSchedulerStudioHost",
        "host": "127.0.0.1",
        "port": 8787,
        "python_path": "python",
        "user": "AzureAD\\\\Tester",
        "logon_type": "interactive",
        "password": None,
        "run_level": "limited",
        "codex_scheduler_db": None,
        "codex_scheduler_disable_autostart": False,
    }
    install_response = client.post("/api/deployment/install", json=install_payload)
    assert install_response.status_code == 200
    assert install_response.json()["status"] == "installed"

    status_response = client.get("/api/deployment/CodexSchedulerStudioHost")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "Ready"

    remove_response = client.delete("/api/deployment/CodexSchedulerStudioHost")
    assert remove_response.status_code == 200
    assert remove_response.json()["status"] == "removed"


def test_connection_and_preflight_endpoints(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)
    monkeypatch.setattr(
        "substrate.studio.main.codex_diagnostics",
        lambda executable, codex_home: {
            "installed": True,
            "resolved_executable": "/usr/bin/codex",
            "version": "codex 1.0.0",
            "auth_file_exists": True,
            "auth_file_path": "/tmp/auth.json",
            "error": None,
        },
    )
    monkeypatch.setattr(
        "substrate.studio.main.start_device_auth",
        lambda executable, codex_home: {
            "ok": True,
            "verification_url": "https://example.com/verify",
            "user_code": "ABCD-1234",
            "raw_output": "ok",
            "rate_limited": False,
            "retry_after_seconds": None,
            "error": None,
        },
    )
    monkeypatch.setattr("substrate.studio.main.test_connection", lambda executable, codex_home, working_directory: {"ok": True, "output": "connection_ok"})
    monkeypatch.setattr(
        "substrate.studio.main.run_preflight",
        lambda executable: [
            CheckResult(name="codex_cli", status="ok", detail="found"),
            CheckResult(name="dep:fastapi", status="ok", detail="0.135.2"),
        ],
    )

    mode_response = client.post("/api/connection/mode", json={"auth_mode": "api_key"})
    assert mode_response.status_code == 200
    assert mode_response.json()["auth_mode"] == "api_key"

    status_response = client.get("/api/connection/status")
    assert status_response.status_code == 200
    assert status_response.json()["installed"] is True

    auth_response = client.post("/api/connection/device-auth/start")
    assert auth_response.status_code == 200
    assert auth_response.json()["ok"] is True

    test_response = client.post("/api/connection/test")
    assert test_response.status_code == 200
    assert test_response.json()["ok"] is True

    preflight_response = client.get("/api/preflight")
    assert preflight_response.status_code == 200
    assert preflight_response.json()["status"] == "ok"

    health_response = client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"


def test_device_auth_rate_limit_guardrails(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    monkeypatch.setattr(
        "substrate.studio.main.start_device_auth",
        lambda executable, codex_home: {
            "ok": False,
            "verification_url": None,
            "user_code": None,
            "raw_output": "Error logging in with device code: status 429 Too Many Requests",
            "rate_limited": True,
            "retry_after_seconds": 30,
            "error": "Error logging in with device code: status 429 Too Many Requests",
        },
    )

    first_attempt = client.post("/api/connection/device-auth/start")
    assert first_attempt.status_code == 429
    assert first_attempt.json()["detail"]["retry_after_seconds"] == 30

    status_response = client.get("/api/connection/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["rate_limited"] is True
    assert body["retry_after_seconds"] > 0

    second_attempt = client.post("/api/connection/device-auth/start")
    assert second_attempt.status_code == 429


def test_cloud_readiness_endpoint_and_gating(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    def fake_assert_cloud_readiness(**kwargs) -> None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cloud execution is not ready.",
                "readiness": {
                    "ready": False,
                    "category": "auth_missing",
                    "summary": "No account auth session found for headless cloud execution.",
                    "retryable": False,
                    "diagnostic_code": "auth_session_missing",
                    "actions": [{"action": "reauth_account", "label": "Reconnect account"}],
                },
            },
        )

    monkeypatch.setattr(
        "substrate.studio.main.compute_cloud_readiness",
        lambda **kwargs: {
            "ready": False,
            "category": "auth_missing",
            "summary": "No account auth session found for headless cloud execution.",
            "retryable": False,
            "diagnostic_code": "auth_session_missing",
            "env_source": "none",
            "resolved_cloud_env_id": None,
            "actions": [{"action": "reauth_account", "label": "Reconnect account"}],
        },
    )
    monkeypatch.setattr("substrate.studio.main.assert_cloud_readiness", fake_assert_cloud_readiness)

    readiness_response = client.get("/api/cloud/readiness?cloud_env_id=env_test_123&working_directory=.")
    assert readiness_response.status_code == 200
    assert readiness_response.json()["ready"] is False
    assert readiness_response.json()["category"] == "auth_missing"
    assert readiness_response.json()["diagnostic_code"] == "auth_session_missing"
    assert readiness_response.json()["env_source"] == "none"
    assert readiness_response.json()["resolved_cloud_env_id"] is None

    create_blocked = client.post("/api/jobs", json=_cloud_payload())
    assert create_blocked.status_code == 409
    assert create_blocked.json()["detail"]["readiness"]["category"] == "auth_missing"


def test_cloud_enable_and_run_blocked_when_not_ready(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    created = client.post("/api/jobs", json={**_cloud_payload(), "enabled": False})
    assert created.status_code == 201
    job_id = created.json()["id"]

    def fake_assert_cloud_readiness(**kwargs) -> None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cloud execution is not ready.",
                "readiness": {
                    "ready": False,
                    "category": "auth_invalid",
                    "summary": "Cloud credentials are invalid for cloud execution.",
                    "retryable": False,
                    "actions": [{"action": "reauth_account", "label": "Reconnect account"}],
                },
            },
        )

    monkeypatch.setattr(
        "substrate.studio.main.assert_cloud_readiness",
        fake_assert_cloud_readiness,
    )

    enable_blocked = client.patch(f"/api/jobs/{job_id}/enabled", json={"enabled": True})
    assert enable_blocked.status_code == 409
    assert enable_blocked.json()["detail"]["readiness"]["category"] == "auth_invalid"

    run_blocked = client.post(f"/api/jobs/{job_id}/run")
    assert run_blocked.status_code == 409
    assert run_blocked.json()["detail"]["readiness"]["category"] == "auth_invalid"


def test_notification_readiness_and_test_email_endpoints(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    monkeypatch.setattr(
        "substrate.studio.main.compute_notification_readiness",
        lambda config: {
            "ready": True,
            "category": None,
            "summary": "Email delivery is ready.",
            "actions": [],
        },
    )
    monkeypatch.setattr(
        "substrate.studio.main.send_test_notification",
        lambda config, recipient=None: {
            "ok": True,
            "category": None,
            "summary": "Test email sent.",
            "recipient": recipient or "adarnell@concepts2code.com",
        },
    )

    readiness = client.get("/api/notifications/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True

    test_send = client.post("/api/notifications/test", json={"recipient": "adarnell@concepts2code.com"})
    assert test_send.status_code == 200
    assert test_send.json()["ok"] is True
    assert test_send.json()["recipient"] == "adarnell@concepts2code.com"


def test_smtp_password_endpoints(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)
    secret_state = {"value": None}

    monkeypatch.setattr("substrate.studio.main.save_secret", lambda ref, value: secret_state.__setitem__("value", value))
    monkeypatch.setattr("substrate.studio.main.clear_secret", lambda ref: secret_state.__setitem__("value", None))

    store = client.post("/api/settings/smtp-password", json={"password": "smtp-pass-123"})
    assert store.status_code == 200
    assert store.json()["status"] == "stored"
    assert secret_state["value"] == "smtp-pass-123"

    clear = client.delete("/api/settings/smtp-password")
    assert clear.status_code == 200
    assert clear.json()["status"] == "deleted"
    assert secret_state["value"] is None


def test_windows_integration_endpoints(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)
    client.app.state.runtime.workspace.scheduler.windows_features_enabled = True
    client.app.state.runtime.workspace.scheduler.windows_app_mode_enabled = True

    monkeypatch.setattr("substrate.studio.main.windows_app_mode_install", lambda: {"ok": True, "message": "installed", "code": 0})
    monkeypatch.setattr("substrate.studio.main.windows_app_mode_uninstall", lambda: {"ok": True, "message": "removed", "code": 0})
    monkeypatch.setattr("substrate.studio.main.windows_host_start", lambda: {"ok": True, "message": "started", "code": 0})
    monkeypatch.setattr("substrate.studio.main.windows_host_stop", lambda: {"ok": True, "message": "stopped", "code": 0})

    install = client.post("/api/windows/app-mode/install")
    assert install.status_code == 200
    assert install.json()["ok"] is True

    uninstall = client.delete("/api/windows/app-mode/install")
    assert uninstall.status_code == 200
    assert uninstall.json()["ok"] is True

    start = client.post("/api/windows/host/start")
    assert start.status_code == 200
    assert start.json()["ok"] is True

    stop = client.post("/api/windows/host/stop")
    assert stop.status_code == 200
    assert stop.json()["ok"] is True


def test_cloud_targets_endpoint_returns_account_targets(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)

    monkeypatch.setattr(
        "substrate.studio.main.discover_cloud_targets",
        lambda **kwargs: {
            "ok": True,
            "category": None,
            "summary": None,
            "targets": [
                {
                    "id": "owner/repo",
                    "label": "Repo target",
                    "repo": "owner/repo",
                    "detail": "owner/repo  •  today",
                    "is_recommended": True,
                }
            ],
        },
    )

    response = client.get("/api/cloud/targets?working_directory=.")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["targets"][0]["id"] == "owner/repo"
    assert body["targets"][0]["is_recommended"] is True
