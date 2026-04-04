from __future__ import annotations

import socket
from datetime import datetime, timezone

from substrate.studio.models import AppConfig, Job, RunRecord
from substrate.studio.notification_service import (
    CLOUD_SUMMARY_END,
    CLOUD_SUMMARY_START,
    build_cloud_summary_prompt,
    compute_notification_readiness,
    extract_cloud_summary_block,
    send_email_smtp,
    send_run_notification,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _config(**overrides) -> AppConfig:
    base = AppConfig(
        id=1,
        codex_executable="codex",
        default_working_directory=".",
        auth_mode="chatgpt_account",
        notifications_enabled=True,
        default_notification_to="adarnell@concepts2code.com",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username=None,
        smtp_from_email="noreply@example.com",
        smtp_password_secret_ref=None,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _job(**overrides) -> Job:
    base = Job(
        id=1,
        name="nightly",
        mode="cloud_exec",
        enabled=True,
        schedule_type="cron",
        cron_expr="*/5 * * * *",
        interval_minutes=None,
        prompt="Run checks",
        sandbox="read-only",
        working_directory=".",
        timeout_seconds=1800,
        cloud_env_id="env_test",
        attempts=1,
        codex_args=None,
        env_json=None,
        notify_email_enabled=True,
        notify_email_to=None,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _run(**overrides) -> RunRecord:
    now = _utcnow()
    base = RunRecord(
        id=1,
        job_id=1,
        status="completed",
        return_code=0,
        command="codex cloud exec",
        started_at=now,
        finished_at=now,
        stdout_path="stdout.log",
        stderr_path="stderr.log",
        metadata_path="meta.json",
        message="done",
        failure_category=None,
        diagnostic_code=None,
        retryable=False,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_compute_notification_readiness_requires_smtp_fields() -> None:
    readiness = compute_notification_readiness(_config(smtp_host=None))
    assert readiness["ready"] is False
    assert readiness["category"] == "config_missing"


def test_build_and_extract_cloud_summary_contract() -> None:
    prompt = build_cloud_summary_prompt("hello")
    assert CLOUD_SUMMARY_START in prompt
    assert CLOUD_SUMMARY_END in prompt

    output = (
        "noise\n"
        f"{CLOUD_SUMMARY_START}\nstatus: completed\nhighlights: first\n{CLOUD_SUMMARY_END}\n"
        "more noise\n"
        f"{CLOUD_SUMMARY_START}\nstatus: completed\nhighlights: second\n{CLOUD_SUMMARY_END}\n"
    )
    summary = extract_cloud_summary_block(output)
    assert summary is not None
    assert "second" in summary


def test_send_email_smtp_retries_transient_errors(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_send_once(**kwargs) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise socket.timeout("temporary timeout")

    monkeypatch.setattr("substrate.studio.notification_service._smtp_send_once", fake_send_once)
    monkeypatch.setattr("substrate.studio.notification_service.time.sleep", lambda seconds: None)

    result = send_email_smtp(
        config=_config(smtp_username=None, smtp_password_secret_ref=None),
        recipient="adarnell@concepts2code.com",
        subject="test",
        body="hello",
        max_attempts=2,
    )
    assert result["ok"] is True
    assert calls["count"] == 2


def test_send_run_notification_skips_when_job_disabled() -> None:
    result = send_run_notification(
        config=_config(),
        job=_job(notify_email_enabled=False),
        run=_run(),
        cloud_output=None,
    )
    assert result["status"] == "skipped"


def test_send_run_notification_uses_cloud_summary(monkeypatch) -> None:
    captured = {"body": ""}

    def fake_send_email_smtp(*, config, recipient, subject, body, timeout_seconds=20, max_attempts=2):
        captured["body"] = body
        return {"ok": True, "category": None, "summary": "Email sent."}

    monkeypatch.setattr("substrate.studio.notification_service.send_email_smtp", fake_send_email_smtp)

    cloud_output = (
        "some output\n"
        f"{CLOUD_SUMMARY_START}\nstatus: completed\nhighlights: cloud checks passed\n{CLOUD_SUMMARY_END}\n"
    )
    result = send_run_notification(
        config=_config(),
        job=_job(mode="cloud_exec"),
        run=_run(status="completed"),
        cloud_output=cloud_output,
    )
    assert result["status"] == "sent"
    assert "Cloud Summary:" in captured["body"]
    assert "cloud checks passed" in captured["body"]
