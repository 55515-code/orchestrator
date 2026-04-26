from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from substrate.orchestrator import Orchestrator
from substrate.registry import SubstrateRuntime
from substrate.reliability import make_idempotency_key


def _write_workspace(
    root: Path,
    *,
    command: list[str],
    task_id: str = "probe_system",
    description: str = "Hardware probe validation task.",
    hardware_probe_enabled: bool,
    max_attempts: int,
    attempt_timeout_seconds: int,
    deadline_seconds: int,
    watchdog_enabled: bool = False,
    respawn_enabled: bool = False,
    watchdog_max_respawns: int = 1,
    watchdog_heartbeat_timeout_seconds: float = 1.0,
    watchdog_stuck_confirmation_seconds: float = 0.5,
    watchdog_poll_interval_seconds: float = 0.1,
    watchdog_terminate_grace_seconds: float = 0.1,
) -> None:
    command_lines = "\n".join(f"          - {json.dumps(token)}" for token in command)
    (root / "workspace.yaml").write_text(
        f"""
version: 1
policy:
  default_mode: observe
  require_source_facts_before_mutation: false
  enforce_stage_flow: true
  stage_sequence:
    - local
    - hosted_dev
    - production
  pass_sequence:
    - research
    - development
    - testing
  rc1_bounded_validation_enabled: true
  rc1_hardware_probe_enabled: {'true' if hardware_probe_enabled else 'false'}
  rc1_validation_max_attempts: {max_attempts}
  rc1_validation_attempt_timeout_seconds: {attempt_timeout_seconds}
  rc1_validation_deadline_seconds: {deadline_seconds}
  rc1_watchdog_enabled: {'true' if watchdog_enabled else 'false'}
  rc1_respawn_enabled: {'true' if respawn_enabled else 'false'}
  rc1_watchdog_max_respawns: {watchdog_max_respawns}
  rc1_watchdog_heartbeat_timeout_seconds: {watchdog_heartbeat_timeout_seconds}
  rc1_watchdog_stuck_confirmation_seconds: {watchdog_stuck_confirmation_seconds}
  rc1_watchdog_poll_interval_seconds: {watchdog_poll_interval_seconds}
  rc1_watchdog_terminate_grace_seconds: {watchdog_terminate_grace_seconds}
repositories:
  - slug: test-repo
    path: .
    allow_mutations: false
    default_mode: observe
    tasks:
      {task_id}:
        description: {json.dumps(description)}
        mode: observe
        command:
{command_lines}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _read_checkpoint_rows(root: Path, run_id: str) -> list[dict[str, object]]:
    path = root / "memory" / "reliability" / "checkpoints" / f"{run_id}.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class BoundedValidationExecutionTest(unittest.TestCase):
    def test_codex_scheduled_prompt_text_does_not_trigger_hardware_probe_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=[
                    "codex",
                    "cloud",
                    "exec",
                    "--env",
                    "orchestrator",
                    "Run validation and testing work.",
                ],
                task_id="studio_scheduled_abc123",
                description="Scheduler job 'self dev'",
                hardware_probe_enabled=False,
                max_attempts=2,
                attempt_timeout_seconds=1,
                deadline_seconds=5,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            self.assertFalse(
                orchestrator._is_bounded_validation_task(  # noqa: SLF001
                    task_id="studio_scheduled_abc123",
                    description="Scheduler job 'self dev'",
                    command=[
                        "codex",
                        "cloud",
                        "exec",
                        "--env",
                        "orchestrator",
                        "Run validation and testing work.",
                    ],
                )
            )

    def test_probe_task_is_disabled_by_default_and_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=["definitely-not-a-real-binary-xyz"],
                hardware_probe_enabled=False,
                max_attempts=2,
                attempt_timeout_seconds=1,
                deadline_seconds=5,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            run_id = orchestrator.run_task(
                repo_slug="test-repo",
                task_id="probe_system",
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
            )

            run = runtime.db.get_run(run_id)
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual("success", run["status"])
            self.assertEqual(0, run["exit_code"])

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"] == "Validation task 'probe_system' skipped by policy"
                    and event.get("payload", {}).get("reason")
                    == "hardware_probe_disabled_by_default"
                    for event in events
                )
            )

    def test_timeout_is_enforced_and_gracefully_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=["python", "-c", "import time; time.sleep(5)"],
                hardware_probe_enabled=True,
                max_attempts=2,
                attempt_timeout_seconds=1,
                deadline_seconds=5,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            run_id = "timeout-skip-run"
            started_at = time.monotonic()
            returned_run_id = orchestrator.run_task(
                repo_slug="test-repo",
                task_id="probe_system",
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
                run_id=run_id,
            )
            elapsed_seconds = time.monotonic() - started_at

            self.assertEqual(run_id, returned_run_id)
            self.assertLess(elapsed_seconds, 4.5)

            run = runtime.db.get_run(run_id)
            self.assertIsNotNone(run)
            assert run is not None
            self.assertEqual("success", run["status"])
            self.assertEqual(124, run["exit_code"])

            events = runtime.db.list_run_events(run_id)
            started_events = [
                event for event in events if event["message"] == "Validation attempt started"
            ]
            timeout_events = [
                event
                for event in events
                if event["message"] == "Validation attempt timed out"
            ]
            self.assertEqual(2, len(started_events))
            self.assertEqual(2, len(timeout_events))
            self.assertTrue(
                any(
                    event["message"]
                    == "Validation task 'probe_system' timed out and was skipped"
                    and event.get("payload", {}).get("skip_reason") == "timeout"
                    for event in events
                )
            )

            checkpoints = _read_checkpoint_rows(root, run_id)
            self.assertTrue(
                any(checkpoint.get("status") == "skipped_timeout" for checkpoint in checkpoints)
            )

    def test_failed_validation_task_honors_max_attempt_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=["python", "-c", "raise SystemExit(1)"],
                hardware_probe_enabled=True,
                max_attempts=3,
                attempt_timeout_seconds=2,
                deadline_seconds=10,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            run_id = "attempt-ceiling-run"
            with self.assertRaises(RuntimeError):
                orchestrator.run_task(
                    repo_slug="test-repo",
                    task_id="probe_system",
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    run_id=run_id,
                )

            events = runtime.db.list_run_events(run_id)
            started_events = [
                event for event in events if event["message"] == "Validation attempt started"
            ]
            failed_events = [
                event for event in events if event["message"] == "Validation attempt failed"
            ]
            recovery_decisions = [
                event for event in events if event["message"] == "Validation recovery decision"
            ]
            self.assertEqual(3, len(started_events))
            self.assertEqual(3, len(failed_events))
            self.assertEqual(3, len(recovery_decisions))
            self.assertEqual("none", recovery_decisions[-1]["payload"]["decision_action"])
            self.assertEqual(
                "failed_terminal",
                recovery_decisions[-1]["payload"]["decision_next_state"],
            )

    def test_watchdog_detects_stuck_and_records_deterministic_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=["python", "-c", "import time; time.sleep(5)"],
                hardware_probe_enabled=True,
                max_attempts=1,
                attempt_timeout_seconds=4,
                deadline_seconds=8,
                watchdog_enabled=True,
                respawn_enabled=False,
                watchdog_max_respawns=0,
                watchdog_heartbeat_timeout_seconds=0.4,
                watchdog_stuck_confirmation_seconds=0.2,
                watchdog_poll_interval_seconds=0.1,
                watchdog_terminate_grace_seconds=0.1,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            run_id = orchestrator.run_task(
                repo_slug="test-repo",
                task_id="probe_system",
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
            )

            events = runtime.db.list_run_events(run_id)
            lifecycle_states = [
                event.get("payload", {}).get("state")
                for event in events
                if event["message"] == "Task lifecycle transitioned to 'suspect_stuck'"
                or event["message"] == "Task lifecycle transitioned to 'stuck_confirmed'"
                or event["message"] == "Task lifecycle transitioned to 'terminate_requested'"
                or event["message"] == "Task lifecycle transitioned to 'terminated'"
            ]
            self.assertEqual(
                ["suspect_stuck", "stuck_confirmed", "terminate_requested", "terminated"],
                lifecycle_states,
            )

            timeout_events = [
                event
                for event in events
                if event["message"] == "Validation attempt timed out"
            ]
            self.assertEqual(1, len(timeout_events))
            self.assertTrue(timeout_events[0]["payload"]["stuck_detected"])

            checkpoints = _read_checkpoint_rows(root, run_id)
            transition_statuses = [
                checkpoint.get("status")
                for checkpoint in checkpoints
                if str(checkpoint.get("status", "")).startswith("task_state_")
            ]
            self.assertIn("task_state_suspect_stuck", transition_statuses)
            self.assertIn("task_state_stuck_confirmed", transition_statuses)
            self.assertIn("task_state_terminate_requested", transition_statuses)
            self.assertIn("task_state_terminated", transition_statuses)

    def test_respawn_path_is_deterministic_and_does_not_loop_infinitely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=["python", "-c", "import time; time.sleep(4)"],
                hardware_probe_enabled=True,
                max_attempts=3,
                attempt_timeout_seconds=3,
                deadline_seconds=12,
                watchdog_enabled=True,
                respawn_enabled=True,
                watchdog_max_respawns=1,
                watchdog_heartbeat_timeout_seconds=0.4,
                watchdog_stuck_confirmation_seconds=0.2,
                watchdog_poll_interval_seconds=0.1,
                watchdog_terminate_grace_seconds=0.1,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            run_id = orchestrator.run_task(
                repo_slug="test-repo",
                task_id="probe_system",
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
            )

            events = runtime.db.list_run_events(run_id)
            started_events = [
                event for event in events if event["message"] == "Validation attempt started"
            ]
            self.assertEqual(3, len(started_events))

            recovery_decisions = [
                event for event in events if event["message"] == "Validation recovery decision"
            ]
            self.assertEqual(3, len(recovery_decisions))
            self.assertEqual("respawn", recovery_decisions[0]["payload"]["decision_action"])
            self.assertEqual("retry", recovery_decisions[1]["payload"]["decision_action"])
            self.assertEqual("none", recovery_decisions[2]["payload"]["decision_action"])
            self.assertEqual(
                "failed_terminal",
                recovery_decisions[2]["payload"]["decision_next_state"],
            )

            timeout_summary = next(
                event
                for event in events
                if event["message"] == "Validation task 'probe_system' timed out and was skipped"
            )
            self.assertEqual(1, timeout_summary["payload"]["respawns_used"])
            self.assertEqual(3, timeout_summary["payload"]["restart_events"])

    def test_checkpoint_and_idempotency_metadata_preserved_for_watchdog_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace(
                root,
                command=["python", "-c", "import time; time.sleep(4)"],
                hardware_probe_enabled=True,
                max_attempts=2,
                attempt_timeout_seconds=3,
                deadline_seconds=8,
                watchdog_enabled=True,
                respawn_enabled=True,
                watchdog_max_respawns=1,
                watchdog_heartbeat_timeout_seconds=0.4,
                watchdog_stuck_confirmation_seconds=0.2,
                watchdog_poll_interval_seconds=0.1,
                watchdog_terminate_grace_seconds=0.1,
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            run_id = "watchdog-metadata-run"
            returned = orchestrator.run_task(
                repo_slug="test-repo",
                task_id="probe_system",
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
                run_id=run_id,
            )
            self.assertEqual(run_id, returned)

            checkpoints = _read_checkpoint_rows(root, run_id)
            recovery_rows = [
                cp for cp in checkpoints if cp.get("status") == "validation_recovery_decision"
            ]
            self.assertTrue(recovery_rows)
            self.assertEqual(
                "respawn", recovery_rows[0].get("payload", {}).get("decision_action")
            )

            skipped_timeout = [
                cp for cp in checkpoints if cp.get("status") == "skipped_timeout"
            ]
            self.assertEqual(1, len(skipped_timeout))
            skipped_payload = skipped_timeout[0].get("payload", {})
            self.assertEqual(1, skipped_payload.get("respawns_used"))
            self.assertEqual(2, skipped_payload.get("attempts_used"))

            idem_path = root / "memory" / "reliability" / "idempotency" / f"{run_id}.json"
            idempotency_raw = json.loads(idem_path.read_text(encoding="utf-8"))
            key = make_idempotency_key(run_id, "task", "local", "probe_system")
            payload = idempotency_raw[key]["payload"]
            self.assertEqual(1, payload["respawns_used"])
            self.assertEqual(2, payload["attempts_used"])
            self.assertEqual(2, payload["restart_events"])


if __name__ == "__main__":
    unittest.main()
