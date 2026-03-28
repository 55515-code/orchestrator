from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from substrate.reliability import (
    CheckpointStore,
    ExecutionTarget,
    FailureClassification,
    ProviderFailoverHook,
    RetryPolicy,
    decide_restart_action,
    execute_with_retry,
    make_idempotency_key,
)


class ReliabilityPrimitivesTest(unittest.TestCase):
    def test_checkpoint_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CheckpointStore(Path(tmp) / "checkpoints")
            run_id = "run-checkpoint-roundtrip"

            first = store.create_checkpoint(
                run_id=run_id,
                scope="run",
                status="started",
                stage="local",
                payload={"note": "boot"},
            )
            second = store.create_checkpoint(
                run_id=run_id,
                scope="step",
                status="completed",
                stage="local",
                step_id="scope",
                payload={"artifact": "memory/runs/mock/01_scope.md"},
            )

            all_records = store.read_checkpoints(run_id)
            self.assertEqual(2, len(all_records))
            self.assertEqual(first.checkpoint_id, all_records[0].checkpoint_id)
            self.assertEqual(second.checkpoint_id, all_records[1].checkpoint_id)

            latest_step = store.latest_checkpoint(
                run_id,
                scope="step",
                step_id="scope",
            )
            self.assertIsNotNone(latest_step)
            assert latest_step is not None
            self.assertEqual("completed", latest_step.status)
            self.assertEqual("memory/runs/mock/01_scope.md", latest_step.payload["artifact"])

    def test_retry_backoff_behavior(self) -> None:
        policy = RetryPolicy(
            max_attempts=4,
            base_delay_seconds=0.25,
            max_delay_seconds=1.0,
            jitter_ratio=0.0,
        )
        attempts = {"count": 0}
        delays: list[float] = []

        def flaky_operation() -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise TimeoutError("temporary timeout")
            return "ok"

        result = execute_with_retry(
            flaky_operation,
            policy=policy,
            sleep=lambda delay: delays.append(delay),
        )

        self.assertEqual("ok", result)
        self.assertEqual(3, attempts["count"])
        self.assertEqual([0.25, 0.5], delays)

    def test_terminal_error_is_not_retried(self) -> None:
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_seconds=0.1,
            max_delay_seconds=1.0,
            jitter_ratio=0.0,
        )
        attempts = {"count": 0}

        def terminal_operation() -> None:
            attempts["count"] += 1
            raise ValueError("invalid request payload")

        with self.assertRaises(ValueError):
            execute_with_retry(
                terminal_operation,
                policy=policy,
                sleep=lambda delay: None,
            )
        self.assertEqual(1, attempts["count"])

    def test_idempotency_key_is_deterministic(self) -> None:
        key_a = make_idempotency_key("run-a", "step", "1", "scope")
        key_b = make_idempotency_key("run-a", "step", "1", "scope")
        key_c = make_idempotency_key("run-a", "step", "2", "scope")
        self.assertEqual(key_a, key_b)
        self.assertNotEqual(key_a, key_c)

    def test_failover_hook_selects_next_provider(self) -> None:
        hook = ProviderFailoverHook(
            fallback_order=["anthropic", "ollama"],
            provider_models={
                "local": "roo-router",
                "anthropic": "claude-sonnet",
                "ollama": "llama3.2",
            },
        )

        next_target = hook.next_target(
            run_id="run-1",
            step_id="scope",
            attempt=1,
            current=ExecutionTarget(provider="local", model="o1-mini"),
            failure=FailureClassification(
                kind="transient",
                reason="network_or_timeout",
            ),
            error=TimeoutError("timeout"),
        )
        self.assertIsNotNone(next_target)
        assert next_target is not None
        self.assertEqual("anthropic", next_target.provider)
        self.assertEqual("claude-sonnet", next_target.model)

    def test_failover_hook_skips_terminal_failure_by_default(self) -> None:
        hook = ProviderFailoverHook(
            fallback_order=["anthropic"],
            provider_models={"local": "roo-router", "anthropic": "claude-sonnet"},
            allow_terminal_failover=False,
        )
        next_target = hook.next_target(
            run_id="run-2",
            step_id="scope",
            attempt=1,
            current=ExecutionTarget(provider="local", model="o1-mini"),
            failure=FailureClassification(
                kind="terminal",
                reason="deterministic_or_policy",
            ),
            error=ValueError("bad request"),
        )
        self.assertIsNone(next_target)

    def test_restart_decision_uses_respawn_when_budget_is_available(self) -> None:
        decision = decide_restart_action(
            attempts_used=1,
            max_attempts=3,
            respawns_used=0,
            max_respawns=1,
            respawn_enabled=True,
            failure_state="terminated",
        )
        self.assertEqual("respawn_pending", decision.next_state)
        self.assertEqual("respawn", decision.action)
        self.assertEqual("respawn_budget_available", decision.reason)

    def test_restart_decision_honors_retry_ceiling(self) -> None:
        decision = decide_restart_action(
            attempts_used=2,
            max_attempts=2,
            respawns_used=0,
            max_respawns=10,
            respawn_enabled=True,
            failure_state="terminated",
        )
        self.assertEqual("failed_terminal", decision.next_state)
        self.assertEqual("none", decision.action)
        self.assertEqual("retry_ceiling_reached", decision.reason)

    def test_restart_decision_uses_retry_when_respawn_is_disabled(self) -> None:
        decision = decide_restart_action(
            attempts_used=1,
            max_attempts=3,
            respawns_used=0,
            max_respawns=1,
            respawn_enabled=False,
            failure_state="terminated",
        )
        self.assertEqual("respawn_pending", decision.next_state)
        self.assertEqual("retry", decision.action)
        self.assertEqual("retry_budget_available", decision.reason)


if __name__ == "__main__":
    unittest.main()
