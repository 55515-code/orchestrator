from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from substrate.studio.cloud_exec import (
    assess_cloud_readiness,
    build_cloud_exec_command,
    classify_cloud_failure,
    parse_cloud_targets,
    run_cloud_exec,
)
from substrate.studio.db import init_database
from substrate.studio.models import AppConfig
from substrate.studio.rc2.services.cloud_service import resolve_cloud_env


def test_classify_cloud_failure_rate_limit() -> None:
    failure = classify_cloud_failure("Error: 429 Too Many Requests", 1)
    assert failure.category == "rate_limited"
    assert failure.retryable is True


def test_classify_cloud_failure_auth_invalid() -> None:
    failure = classify_cloud_failure("401 unauthorized", 1)
    assert failure.category == "auth_invalid"
    assert failure.retryable is False


def test_classify_cloud_failure_env_not_found() -> None:
    failure = classify_cloud_failure("Error: environment 'test' not found", 1)
    assert failure.category == "env_missing"
    assert failure.retryable is False


def test_classify_cloud_failure_cli_incompatible() -> None:
    failure = classify_cloud_failure("error: unexpected argument '--skip-git-repo-check' found", 2)
    assert failure.category == "cli_incompatible"
    assert failure.retryable is False


def test_build_cloud_exec_command_excludes_repo_flag() -> None:
    command = build_cloud_exec_command("codex", "env-test", "hello", 1, codex_args='["--verbose"]')
    assert "--skip-git-repo-check" not in command
    assert command[:4] == ["codex", "cloud", "exec", "--env"]
    assert "env-test" in command


def test_run_cloud_exec_retries_transient(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(returncode=1, stdout="", stderr="503 service unavailable")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("substrate.studio.cloud_exec.subprocess.run", fake_run)
    monkeypatch.setattr("substrate.studio.cloud_exec.time.sleep", lambda seconds: None)

    result = run_cloud_exec(
        executable="codex",
        cloud_env_id="env_test",
        prompt="hello",
        attempts=1,
        codex_args=None,
        cwd=tmp_path,
        env={},
        timeout_seconds=60,
        max_retries=2,
    )

    assert result["ok"] is True
    assert calls["count"] == 2


def test_run_cloud_exec_no_retry_for_auth(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        return SimpleNamespace(returncode=1, stdout="", stderr="401 unauthorized")

    monkeypatch.setattr("substrate.studio.cloud_exec.subprocess.run", fake_run)
    monkeypatch.setattr("substrate.studio.cloud_exec.time.sleep", lambda seconds: None)

    result = run_cloud_exec(
        executable="codex",
        cloud_env_id="env_test",
        prompt="hello",
        attempts=1,
        codex_args=None,
        cwd=tmp_path,
        env={},
        timeout_seconds=60,
        max_retries=2,
    )

    assert result["ok"] is False
    assert result["failure_category"] == "auth_invalid"
    assert calls["count"] == 1


def test_assess_cloud_readiness_includes_env_metadata(monkeypatch, tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    config = AppConfig(
        id=1,
        codex_executable="codex",
        codex_home=str(codex_home),
        default_working_directory=str(tmp_path),
        auth_mode="chatgpt_account",
    )

    monkeypatch.setattr(
        "substrate.studio.cloud_exec.run_cloud_exec",
        lambda **kwargs: {
            "ok": True,
            "return_code": 0,
            "output": "cloud_ready_ok",
            "command": ["codex", "cloud", "exec"],
            "failure_category": None,
            "retryable": False,
        },
    )

    readiness = assess_cloud_readiness(
        config=config,
        cloud_env_id="env-123",
        working_directory=str(tmp_path),
        env={},
        env_source="global_default",
        resolved_cloud_env_id="env-123",
    )

    assert readiness["ready"] is True
    assert readiness["diagnostic_code"] == "cloud_ready"
    assert readiness["env_source"] == "global_default"
    assert readiness["resolved_cloud_env_id"] == "env-123"


def test_parse_cloud_targets_normalizes_list_output(tmp_path: Path) -> None:
    output = """
https://chatgpt.com/codex/tasks/task_b_123
  [READY] Implement email signing alignment
  c2cadarnell/fd_stale_tagger  •  Dec 30 16:59
"""
    targets = parse_cloud_targets(output, str(tmp_path / "fd_stale_tagger"))
    assert len(targets) == 1
    assert targets[0].id == "c2cadarnell/fd_stale_tagger"
    assert targets[0].label == "Implement email signing alignment"
    assert targets[0].is_recommended is True


def test_resolve_cloud_env_never_uses_latest_job() -> None:
    config = AppConfig(id=1, codex_executable="codex", default_working_directory=".", auth_mode="chatgpt_account")
    env_id, source = resolve_cloud_env(config, None)
    assert env_id is None
    assert source == "none"


def test_resolve_cloud_env_ignores_blank_default() -> None:
    config = AppConfig(
        id=1,
        codex_executable="codex",
        default_working_directory=".",
        auth_mode="chatgpt_account",
        default_cloud_env_id="   ",
    )
    env_id, source = resolve_cloud_env(config, None)
    assert env_id is None
    assert source == "none"


def test_database_migration_adds_new_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE app_config (id INTEGER PRIMARY KEY, codex_executable VARCHAR(512) NOT NULL, codex_home VARCHAR(512), default_working_directory VARCHAR(512) NOT NULL, api_key_env_var VARCHAR(128) NOT NULL, api_key_secret_ref VARCHAR(256), global_env_json TEXT, deployment_task_name VARCHAR(128), deployment_host VARCHAR(64) NOT NULL, deployment_port INTEGER NOT NULL, deployment_user VARCHAR(256), auth_mode VARCHAR(32) NOT NULL, last_connection_status VARCHAR(32), last_connection_message TEXT, auth_rate_limited_until DATETIME, auth_rate_limit_hits INTEGER NOT NULL DEFAULT 0, updated_at DATETIME NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(120) NOT NULL UNIQUE, mode VARCHAR(32) NOT NULL, enabled BOOLEAN NOT NULL, schedule_type VARCHAR(16) NOT NULL, cron_expr VARCHAR(64), interval_minutes INTEGER, prompt TEXT NOT NULL, sandbox VARCHAR(32) NOT NULL, working_directory VARCHAR(512) NOT NULL, timeout_seconds INTEGER NOT NULL, cloud_env_id VARCHAR(128), attempts INTEGER NOT NULL, codex_args TEXT, env_json TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, last_run_at DATETIME, last_status VARCHAR(32), last_message TEXT)"
    )
    conn.execute(
        "CREATE TABLE run_records (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL, status VARCHAR(32) NOT NULL, return_code INTEGER, command TEXT NOT NULL, started_at DATETIME NOT NULL, finished_at DATETIME, stdout_path VARCHAR(512), stderr_path VARCHAR(512), metadata_path VARCHAR(512), message TEXT, failure_category VARCHAR(32), retryable BOOLEAN NOT NULL DEFAULT 0)"
    )
    conn.commit()
    conn.close()

    init_database(f"sqlite:///{db_path}")
    conn = sqlite3.connect(db_path)
    app_config_cols = {row[1] for row in conn.execute("PRAGMA table_info(app_config)").fetchall()}
    job_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    run_record_cols = {row[1] for row in conn.execute("PRAGMA table_info(run_records)").fetchall()}
    conn.close()

    assert "default_cloud_env_id" in app_config_cols
    assert "smtp_host" in app_config_cols
    assert "default_notification_to" in app_config_cols
    assert "notify_email_enabled" in job_cols
    assert "diagnostic_code" in run_record_cols
    assert "notification_status" in run_record_cols
