#!/usr/bin/env python3
"""Tests for the OpenClaw Gateway Watchdog."""

from __future__ import annotations

import builtins
import io
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure substrate is importable (repo root is the parent of tests/)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from substrate.watchdog.gateway_watchdog import (  # noqa: E402
    AUDIT_FILE,
    DEFAULT_INTERVAL,
    GRACE_AFTER_RESTART,
    LOG_FILE,
    MAX_RESTARTS,
    RESTART_WINDOW,
    STATE_DIR,
    STATUS_FILE,
    check_config,
    check_http_health,
    check_port,
    check_resource_usage,
    check_systemd,
    check_upstream_dns,
    diagnose,
    rate_limit_exceeded,
    record_restart,
    run_checks,
    run_once,
    write_audit,
    write_status,
)


def test_check_http_health_ok(monkeypatch):
    """HTTP health check returns ok when endpoint responds 200."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: mock_resp)

    result = check_http_health()
    assert result["ok"] is True
    assert result["status_code"] == 200


def test_check_http_health_fail(monkeypatch):
    """HTTP health check reports failure on exception."""
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("refused")))

    result = check_http_health()
    assert result["ok"] is False
    assert "ConnectionError" in result["detail"]


def test_check_systemd_active(monkeypatch):
    """systemd check returns ok when unit is active."""
    proc = MagicMock()
    proc.stdout.strip.return_value = "active"
    proc.stderr.strip.return_value = ""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run", lambda *a, **k: proc)

    result = check_systemd()
    assert result["ok"] is True
    assert result["active"] is True


def test_check_systemd_inactive(monkeypatch):
    """systemd check reports failure when unit is inactive."""
    proc = MagicMock()
    proc.stdout.strip.return_value = "inactive"
    proc.stderr.strip.return_value = ""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run", lambda *a, **k: proc)

    result = check_systemd()
    assert result["ok"] is False
    assert result["active"] is False


def test_check_port_open(monkeypatch):
    """Port check returns ok when port is listening."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.is_port_open", lambda *a, **k: True)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.pid_on_port", lambda *a, **k: 1234)

    result = check_port()
    assert result["ok"] is True
    assert result["pid"] == 1234


def test_check_port_closed(monkeypatch):
    """Port check reports failure when port is not listening."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.is_port_open", lambda *a, **k: False)

    result = check_port()
    assert result["ok"] is False
    assert "not listening" in result["detail"]


def _patch_proc_status(monkeypatch, pid: int, content: str) -> None:
    """Redirect reads of /proc/<pid>/status to in-memory content.

    The real builtin is captured before patching so the fake can delegate for
    every other path without recursing into itself.
    """
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path) == f"/proc/{pid}/status":
            return io.StringIO(content)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)


def test_check_resource_usage_ok(monkeypatch):
    """Resource check passes when memory is below threshold."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.pid_on_port", lambda *a, **k: 5555)
    _patch_proc_status(monkeypatch, 5555, "VmRSS:\t  512000 kB\n")

    result = check_resource_usage()
    assert result["ok"] is True
    assert result["memory_mb"] == 500.0


def test_check_resource_usage_high_memory(monkeypatch):
    """Resource check fails when memory exceeds threshold."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.pid_on_port", lambda *a, **k: 5555)
    _patch_proc_status(monkeypatch, 5555, "VmRSS:\t 2097152 kB\n")  # 2GB

    result = check_resource_usage()
    assert result["ok"] is False
    assert result["memory_mb"] == 2048.0
    assert "1024MB threshold" in result["detail"]


def test_check_config_valid(monkeypatch, tmp_path):
    """Config check passes with valid JSON and expected bind."""
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps({"gateway": {"bind": "lan"}}))
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.OPENCLAW_CONFIG", cfg)

    result = check_config()
    assert result["ok"] is True
    assert result["bind"] == "lan"


def test_check_config_invalid_json(monkeypatch, tmp_path):
    """Config check fails on invalid JSON."""
    cfg = tmp_path / "openclaw.json"
    cfg.write_text("not json")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.OPENCLAW_CONFIG", cfg)

    result = check_config()
    assert result["ok"] is False
    assert "invalid JSON" in result["detail"]


def test_check_config_missing(monkeypatch, tmp_path):
    """Config check fails when file is missing."""
    cfg = tmp_path / "missing.json"
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.OPENCLAW_CONFIG", cfg)

    result = check_config()
    assert result["ok"] is False
    assert "missing" in result["detail"]


def test_diagnose_healthy():
    """Diagnosis returns HEALTHY when all checks pass."""
    checks = {
        "http_health": {"ok": True},
        "systemd": {"ok": True},
        "port_listener": {"ok": True},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    assert diagnose(checks) == "HEALTHY"


def test_diagnose_systemd_failed():
    """Diagnosis returns SYSTEMD_FAILED when systemd is down."""
    checks = {
        "http_health": {"ok": False},
        "systemd": {"ok": False},
        "port_listener": {"ok": False},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    assert diagnose(checks) == "SYSTEMD_FAILED"


def test_diagnose_port_down():
    """Diagnosis returns PORT_DOWN when port is not listening."""
    checks = {
        "http_health": {"ok": False},
        "systemd": {"ok": True},
        "port_listener": {"ok": False},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    assert diagnose(checks) == "PORT_DOWN"


def test_diagnose_http_unhealthy():
    """Diagnosis returns HTTP_UNHEALTHY when port is up but HTTP fails."""
    checks = {
        "http_health": {"ok": False},
        "systemd": {"ok": True},
        "port_listener": {"ok": True},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    assert diagnose(checks) == "HTTP_UNHEALTHY"


def test_diagnose_config_drift():
    """Diagnosis returns CONFIG_DRIFT when config is invalid."""
    checks = {
        "http_health": {"ok": True},
        "systemd": {"ok": True},
        "port_listener": {"ok": True},
        "config": {"ok": False, "bind": "loopback"},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    assert diagnose(checks) == "CONFIG_DRIFT"


def test_rate_limit_not_exceeded():
    """Rate limit not exceeded with few restarts."""
    state = {"restart_timestamps": []}
    assert rate_limit_exceeded(state) is False


def test_rate_limit_exceeded():
    """Rate limit exceeded after max restarts in window."""
    now = time.time()
    state = {"restart_timestamps": [now - 1, now - 2, now - 3]}
    assert rate_limit_exceeded(state) is True


def test_rate_limit_expired():
    """Rate limit resets after window expires."""
    now = time.time()
    state = {"restart_timestamps": [now - 700, now - 701, now - 702]}
    assert rate_limit_exceeded(state) is False


def test_record_restart():
    """Record restart appends timestamp."""
    state = {}
    record_restart(state)
    assert len(state["restart_timestamps"]) == 1
    assert abs(state["restart_timestamps"][0] - time.time()) < 1.0


def test_run_once_healthy(monkeypatch, tmp_path):
    """run_once returns healthy state when all checks pass."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATE_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_FILE", tmp_path / "log.txt")

    checks = {
        "http_health": {"ok": True},
        "systemd": {"ok": True},
        "port_listener": {"ok": True},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run_checks", lambda: checks)

    state = run_once()
    assert state.get("healthy") is True
    assert state.get("last_diagnosis") == "HEALTHY"


def test_run_once_unhealthy_restarts(monkeypatch, tmp_path):
    """run_once performs remediation when unhealthy."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATE_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_FILE", tmp_path / "log.txt")

    checks = {
        "http_health": {"ok": False},
        "systemd": {"ok": False, "substate": "inactive"},
        "port_listener": {"ok": False},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run_checks", lambda: checks)
    monkeypatch.setattr(
        "substrate.watchdog.gateway_watchdog.run",
        lambda *a, **k: MagicMock(returncode=0, stdout="", stderr=""),
    )
    # Do not burn the grace period in tests.
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.time.sleep", lambda *_: None)

    state = run_once()
    assert state.get("healthy") is False
    assert state.get("last_diagnosis") == "SYSTEMD_FAILED"
    assert len(state.get("restart_timestamps", [])) == 1


def test_run_once_rate_limited(monkeypatch, tmp_path):
    """run_once escalates when rate limit exceeded."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATE_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_FILE", tmp_path / "log.txt")

    now = time.time()
    state = {
        "restart_timestamps": [now - 1, now - 2, now - 3],
        "consecutive_failures": 1,
    }

    checks = {
        "http_health": {"ok": False},
        "systemd": {"ok": False},
        "port_listener": {"ok": False},
        "config": {"ok": True},
        "resource_usage": {"ok": True},
        "upstream_dns": {"ok": True},
    }
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run_checks", lambda: checks)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.load_state", lambda: state)

    result = run_once()
    assert result.get("last_diagnosis") == "SYSTEMD_FAILED"
    # No new restart should have been recorded because of rate limit
    assert len(result.get("restart_timestamps", [])) == 3


def test_check_upstream_dns_ok(monkeypatch):
    """DNS check passes when resolution works."""
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "Host not found"  # irrelevant for ok case
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run", lambda *a, **k: proc)

    result = check_upstream_dns()
    assert result["ok"] is True


def test_check_upstream_dns_fail(monkeypatch):
    """DNS check fails when resolution fails."""
    proc = MagicMock()
    proc.returncode = 1
    proc.stderr = "NXDOMAIN"
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.run", lambda *a, **k: proc)

    result = check_upstream_dns()
    assert result["ok"] is False


def test_audit_log_written(monkeypatch, tmp_path):
    """Audit entries are appended to JSONL file."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATE_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_DIR", tmp_path)

    write_audit({"event": "test", "detail": "hello"})
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "test"
    assert record["detail"] == "hello"
    assert "_ts" in record


def test_audit_log_survives_non_serializable_values(monkeypatch, tmp_path):
    """A non-serializable value must not crash or drop the audit record.

    The watchdog exists to keep the gateway available; losing the audit trail
    (or raising out of watchdog_cycle) because a subprocess wrapper leaked into
    the record would defeat that purpose.
    """
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATE_DIR", tmp_path)
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.LOG_DIR", tmp_path)

    write_audit({"event": "remediation", "detail": MagicMock(name="leaked")})

    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "remediation"
    assert isinstance(record["detail"], str)


def test_write_status_survives_non_serializable_values(monkeypatch, tmp_path):
    """Status snapshots degrade to string rather than raising."""
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr("substrate.watchdog.gateway_watchdog.STATE_DIR", tmp_path)

    write_status({"healthy": False, "probe": MagicMock(name="leaked")})

    payload = json.loads((tmp_path / "status.json").read_text())
    assert payload["healthy"] is False
    assert isinstance(payload["probe"], str)
