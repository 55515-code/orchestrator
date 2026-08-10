from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from substrate import approvals
from substrate.approvals import (
    CODE_ALPHABET,
    CODE_LEN,
    MAX_VERIFY_ATTEMPTS,
    approval_lane_status,
    email_backend_send,
    load_lane,
    new_code,
    notify_approval_gate,
    poll_for_replies,
    request_approval,
    resolve_approval,
    send_test_message,
    sms_backend_send,
    verify_channel,
    watch_once,
)


def make_runtime(tmp_path: Path) -> SimpleNamespace:
    state_file = tmp_path / "state" / "approval-lane.json"
    return SimpleNamespace(
        root=tmp_path,
        paths={"approval_lane": state_file, "state": tmp_path / "state"},
    )


def state_file(runtime: SimpleNamespace) -> Path:
    return Path(runtime.paths["approval_lane"])


def test_new_code_format() -> None:
    code = new_code()
    assert len(code) == CODE_LEN
    assert all(c in CODE_ALPHABET for c in code)
    # codes are random
    assert len({new_code() for _ in range(50)}) > 1


def test_load_lane_seeds_default_channels(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    lane = load_lane(runtime)
    assert set(lane["channels"]) == {
        "email",
        "sms:7163528536",
        "sms:7162666606",
    }
    assert lane["channels"]["email"]["address"] == "ahronzombi@protonmail.com"
    assert lane["primary"] is None


def test_save_load_roundtrip_preserves_state(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    lane = load_lane(runtime)
    lane["primary"] = "email"
    lane["channels"]["email"]["status"] = "verified"
    approvals.save_lane(runtime, lane)
    reloaded = load_lane(runtime)
    assert reloaded["primary"] == "email"
    assert reloaded["channels"]["email"]["status"] == "verified"
    assert (state_file(runtime).stat().st_mode & 0o777) == 0o600


def test_send_test_message_unknown_channel(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    result = send_test_message(runtime, "bogus")
    assert result["ok"] is False
    assert "unknown channel" in result["detail"]


def test_send_test_message_email_failure_invalidates_code(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(False, "", "bridge rejected: no such user")):
        result = send_test_message(runtime, "email")
    assert result["ok"] is False
    assert "bridge rejected" in result["detail"]
    assert "verification_code" not in result  # undelivered code must not leak
    lane = load_lane(runtime)
    assert lane["channels"]["email"]["status"] == "error"
    assert lane["channels"]["email"]["verification_code"] is None
    assert lane["channels"]["email"]["code_expires_at"] is None


def test_send_test_message_success_stores_code(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "ahronzombi@proton.me", "accepted")):
        result = send_test_message(runtime, "email")
    assert result["ok"] is True
    assert result["verification_code"]
    lane = load_lane(runtime)
    assert lane["channels"]["email"]["status"] == "probe-sent"
    assert lane["channels"]["email"]["verification_code"] == result["verification_code"]


def test_verify_channel_wrong_code_tracks_attempts(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    good_code = lane["channels"]["email"]["verification_code"]
    wrong = ("A" if good_code[0] != "A" else "B") + good_code[1:]
    result = verify_channel(runtime, "email", wrong)
    assert result["ok"] is False
    lane = load_lane(runtime)
    assert lane["channels"]["email"]["verify_attempts"] == 1
    assert lane["channels"]["email"]["status"] != "verified"


def test_verify_channel_wrong_code_exhausts_attempts(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    good_code = lane["channels"]["email"]["verification_code"]
    wrong = ("A" if good_code[0] != "A" else "B") + good_code[1:]
    for _ in range(MAX_VERIFY_ATTEMPTS):
        verify_channel(runtime, "email", wrong)
    result = verify_channel(runtime, "email", good_code)
    assert result["ok"] is False
    assert "too many failed verification attempts" in result["detail"]


def test_verify_channel_promotes_to_primary(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    code = lane["channels"]["email"]["verification_code"]
    result = verify_channel(runtime, "email", code)
    assert result["ok"] is True
    assert result["promoted_to_primary"] is True
    assert result["primary"] == "email"
    lane = load_lane(runtime)
    assert lane["primary"] == "email"
    assert lane["channels"]["email"]["status"] == "verified"
    assert lane["channels"]["email"]["verification_code"] is None


def test_verify_channel_only_verifies_once(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    code = lane["channels"]["email"]["verification_code"]
    verify_channel(runtime, "email", code)
    result = verify_channel(runtime, "email", code)
    assert result["ok"] is False
    assert "already verified" in result["detail"]


def test_request_approval_without_primary(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    result = request_approval(runtime, subject="deploy")
    assert result["ok"] is False
    assert "no primary approval channel" in result["detail"]


def test_request_and_resolve_approval(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    code = lane["channels"]["email"]["verification_code"]
    verify_channel(runtime, "email", code)

    with patch.object(approvals, "_dispatch", return_value={"ok": True, "detail": "sent"}):
        result = request_approval(runtime, subject="deploy staging", body="details")
    assert result["ok"] is True
    assert result["dispatch_ok"] is True
    assert result["approval_id"].startswith("apv-")
    lane = load_lane(runtime)
    assert len(lane["pending_approvals"]) == 1
    pending = lane["pending_approvals"][0]
    assert pending["status"] == "pending"

    resolved = resolve_approval(runtime, pending["id"], pending["code"], "approve")
    assert resolved["ok"] is True
    assert resolved["decision"] == "approve"
    lane = load_lane(runtime)
    assert lane["pending_approvals"] == []
    assert lane["resolved_approvals"][-1]["status"] == "approved"


def test_request_approval_records_even_when_dispatch_fails(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    verify_channel(runtime, "email", lane["channels"]["email"]["verification_code"])
    with patch.object(approvals, "_dispatch", return_value={"ok": False, "detail": "channel down"}):
        result = request_approval(runtime, subject="deploy")
    assert result["ok"] is True          # request recorded
    assert result["dispatch_ok"] is False  # notification failed
    lane = load_lane(runtime)
    assert len(lane["pending_approvals"]) == 1
    assert lane["pending_approvals"][0]["dispatch_ok"] is False


def test_resolve_approval_wrong_code(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    code = lane["channels"]["email"]["verification_code"]
    verify_channel(runtime, "email", code)
    result = request_approval(runtime, subject="deploy")
    lane = load_lane(runtime)
    pending = lane["pending_approvals"][0]
    wrong = ("A" if pending["code"][0] != "A" else "B") + pending["code"][1:]
    resolved = resolve_approval(runtime, pending["id"], wrong, "approve")
    assert resolved["ok"] is False
    lane = load_lane(runtime)
    assert lane["pending_approvals"][0]["status"] == "pending"


def test_resolve_approval_deny(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    verify_channel(runtime, "email", lane["channels"]["email"]["verification_code"])
    result = request_approval(runtime, subject="deploy")
    lane = load_lane(runtime)
    pending = lane["pending_approvals"][0]
    resolved = resolve_approval(runtime, pending["id"], pending["code"], "deny")
    assert resolved["ok"] is True
    assert resolved["status"] == "denied"


def test_notify_approval_gate_without_primary(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    result = notify_approval_gate(runtime, action="config-sync-deploy")
    assert result["dispatched"] is False
    assert "no verified primary" in result["reason"]


def test_notify_approval_gate_dispatches_when_verified(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    verify_channel(runtime, "email", lane["channels"]["email"]["verification_code"])
    with patch.object(approvals, "_dispatch", return_value={"ok": True, "detail": "sent"}):
        result = notify_approval_gate(runtime, action="storage-maintenance --apply")
    assert result["dispatched"] is True
    assert result["approval_id"].startswith("apv-")


def test_sms_backend_reports_missing_provider(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    result = send_test_message(runtime, "sms:7163528536")
    assert result["ok"] is False
    assert "no SMS provider configured" in result["detail"]


def test_poll_without_verified_channel(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    results = poll_for_replies(runtime)
    assert results == [{"ok": False, "detail": "no verified primary channel; nothing to poll"}]


def test_email_backend_send_connection_error() -> None:
    ok, used, detail = email_backend_send(
        "test@example.com", "s", "b", host="127.0.0.1", port=1
    )
    assert ok is False
    assert "connection failed" in detail or "failed" in detail


def test_status_payload_omits_codes(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    status = approval_lane_status(runtime)
    assert status["primary"] is None
    assert set(status["channels"]) == {"email", "sms:7163528536", "sms:7162666606"}
    raw = json.dumps(status)
    assert "verification_code" not in raw
    assert "pending_approvals" in status


def test_watch_once_retries_failed_channels(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(False, "", "bridge down")):
        summary = watch_once(runtime)
    assert len(summary["test_sends"]) == 3  # email + both sms retried
    assert all(s["ok"] is False for s in summary["test_sends"])


def test_watch_once_does_not_resend_pending_probe(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        watch_once(runtime)  # first pass delivers the test
    lane = load_lane(runtime)
    assert lane["channels"]["email"]["status"] == "probe-sent"
    with patch.object(approvals, "email_backend_send", side_effect=AssertionError("resend")) as send:
        watch_once(runtime)  # second pass must NOT resend while awaiting reply
        send.assert_not_called()


def test_watch_once_confirms_primary_exactly_once(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    with patch.object(approvals, "email_backend_send", return_value=(True, "x", "accepted")):
        send_test_message(runtime, "email")
    lane = load_lane(runtime)
    verify_channel(runtime, "email", lane["channels"]["email"]["verification_code"])

    with patch.object(approvals, "_dispatch", return_value={"ok": True, "detail": "sent"}) as dispatch:
        summary = watch_once(runtime)
    assert len(summary["notifications"]) == 1
    assert summary["notifications"][0]["ok"] is True
    lane = load_lane(runtime)
    assert lane.get("primary_confirmed_at") is not None

    with patch.object(approvals, "_dispatch", side_effect=AssertionError("resend")) as dispatch:
        watch_once(runtime)  # already confirmed; must not re-send
        dispatch.assert_not_called()
