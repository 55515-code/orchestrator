from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agent_hybrid_runner.py"
SPEC = importlib.util.spec_from_file_location("agent_hybrid_runner", MODULE_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_bounded_loop_count_is_clamped() -> None:
    assert RUNNER.bounded_loop_count(0) == 1
    assert RUNNER.bounded_loop_count(1) == 1
    assert RUNNER.bounded_loop_count(6) == 6
    assert RUNNER.bounded_loop_count(20) == 12


def test_parse_publish_markers_reads_expected_fields() -> None:
    text = "\n".join(
        [
            "AGENT_PUBLISH_ACTION=merged",
            "AGENT_PUBLISH_OK=true",
            "AGENT_PUBLISH_BRANCH=agent/swarm-abc",
            "AGENT_PUBLISH_PR_NUMBER=42",
            "AGENT_PUBLISH_PR_URL=https://github.com/owner/repo/pull/42",
            "AGENT_PUBLISH_MERGE_ATTEMPTED=true",
            "AGENT_PUBLISH_MERGED=true",
            "AGENT_PUBLISH_MERGE_ATTEMPTS=2",
            "AGENT_PUBLISH_REBASE_OK=true",
            "AGENT_PUBLISH_PUSH_OK=true",
            "AGENT_PUBLISH_MESSAGE=done",
        ]
    )
    parsed = RUNNER.parse_publish_markers(text)
    assert parsed["action"] == "merged"
    assert parsed["ok"] is True
    assert parsed["branch"] == "agent/swarm-abc"
    assert parsed["pr_number"] == 42
    assert parsed["merged"] is True
    assert parsed["merge_attempts"] == 2


def test_derive_session_status_fallback_success() -> None:
    loop_results = [{"loop_status": "fallback_success"}, {"loop_status": "success"}]
    merge_history = [{"action": "skipped_write_disabled", "merged": False}]
    status = RUNNER.derive_session_status(
        mode="deep",
        loop_results=loop_results,
        merge_history=merge_history,
        allow_write=False,
    )
    assert status == "fallback_success"


def test_derive_session_status_partial_failure_on_merge_failure() -> None:
    loop_results = [{"loop_status": "success"} for _ in range(6)]
    merge_history = [{"action": "merge_failed", "merged": False}]
    status = RUNNER.derive_session_status(
        mode="deep",
        loop_results=loop_results,
        merge_history=merge_history,
        allow_write=True,
    )
    assert status == "partial_failure"


def test_invoke_publish_parses_mocked_marker_output(monkeypatch, tmp_path: Path) -> None:
    def fake_run_command(command, *, cwd, timeout_seconds):  # type: ignore[no-untyped-def]
        return {
            "command": command,
            "command_text": "mock",
            "return_code": 0,
            "ok": True,
            "duration_seconds": 0.01,
            "stdout_tail": "\n".join(
                [
                    "AGENT_PUBLISH_ACTION=pr_updated",
                    "AGENT_PUBLISH_OK=true",
                    "AGENT_PUBLISH_BRANCH=agent/swarm-20260403-abcd",
                    "AGENT_PUBLISH_PR_NUMBER=99",
                    "AGENT_PUBLISH_PR_URL=https://example/pull/99",
                    "AGENT_PUBLISH_MERGE_ATTEMPTED=false",
                    "AGENT_PUBLISH_MERGED=false",
                    "AGENT_PUBLISH_MERGE_ATTEMPTS=0",
                    "AGENT_PUBLISH_REBASE_OK=true",
                    "AGENT_PUBLISH_PUSH_OK=true",
                    "AGENT_PUBLISH_MESSAGE=ok",
                ]
            ),
            "stderr_tail": "",
        }

    monkeypatch.setattr(RUNNER, "run_command", fake_run_command)

    summary_path = tmp_path / "agent_summary.json"
    report_path = tmp_path / "agent_report.md"
    command_result, publish_data = RUNNER.invoke_publish(
        root=tmp_path,
        timeout_seconds=30,
        allow_write=True,
        target_branch="main",
        summary_path=summary_path,
        report_path=report_path,
        loop_index=2,
        loop_count=6,
        session_id="20260403-abcd",
        merge_policy="safe_gate",
        retry_merge=1,
        safe_to_merge=True,
    )

    assert command_result["ok"] is True
    assert publish_data["action"] == "pr_updated"
    assert publish_data["pr_number"] == 99
    assert publish_data["loop_index"] == 2
    assert publish_data["rebase_ok"] is True
