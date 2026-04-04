from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from substrate.orchestrator import Orchestrator
from substrate.registry import SubstrateRuntime
from substrate.reliability import IdempotencyStore, make_idempotency_key
from substrate.resource_orchestration import ElasticScaleHooks, NoOpScaleHook


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, invoke_impl) -> None:
        self._invoke_impl = invoke_impl

    def invoke(self, prompt: str) -> _FakeMessage:
        return self._invoke_impl(prompt)


class _RecordingScaleHook(NoOpScaleHook):
    def __init__(self) -> None:
        self.scale_out_calls: list[dict[str, str | int]] = []
        self.scale_in_calls: list[dict[str, str | int]] = []

    def scale_out(
        self,
        *,
        pool_name: str,
        capability: str,
        delta: int,
        reason: str,
    ) -> None:
        self.scale_out_calls.append(
            {
                "pool_name": pool_name,
                "capability": capability,
                "delta": delta,
                "reason": reason,
            }
        )

    def scale_in(
        self,
        *,
        pool_name: str,
        capability: str,
        delta: int,
        reason: str,
    ) -> None:
        self.scale_in_calls.append(
            {
                "pool_name": pool_name,
                "capability": capability,
                "delta": delta,
                "reason": reason,
            }
        )


def _write_test_workspace(root: Path, *, retry_max_attempts: int = 1) -> None:
    (root / "chains").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)

    (root / "workspace.yaml").write_text(
        """
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
  rc1_openclaw_internal_assist_enabled: false
  rc1_openclaw_manual_trigger_required: true
  rc1_openclaw_revetting_required: true
  rc1_openclaw_allowed_stages:
    - local
    - hosted_dev
  rc1_openclaw_allowed_passes:
    - research
  rc1_openclaw_allowed_data_classes:
    - synthetic
    - redacted
repositories:
  - slug: test-repo
    path: .
    allow_mutations: false
    default_mode: observe
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (root / "chains" / "test-chain.yaml").write_text(
        f"""
name: test-chain
description: Reliability test chain
defaults:
  provider: local
  models:
    openai: gpt-primary
    anthropic: claude-fallback
  retry_policy:
    max_attempts: {retry_max_attempts}
    base_delay_seconds: 0
    max_delay_seconds: 0
    jitter_ratio: 0
  failover_order:
    - anthropic
steps:
  - id: scope
    pass: research
    prompt: prompts/step.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "prompts" / "step.md").write_text(
        """
Objective: {objective}

Context:
{context}

Previous:
{previous_outputs}

Outputs JSON:
{outputs_json}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _enable_openclaw_policy(
    root: Path,
    *,
    allowed_stages: tuple[str, ...] = ("local", "hosted_dev"),
) -> None:
    workspace_path = root / "workspace.yaml"
    raw = workspace_path.read_text(encoding="utf-8")
    raw = raw.replace(
        "rc1_openclaw_internal_assist_enabled: false",
        "rc1_openclaw_internal_assist_enabled: true",
    )
    if allowed_stages != ("local", "hosted_dev"):
        lines = raw.splitlines()
        output: list[str] = []
        skip = False
        for line in lines:
            if line.strip() == "rc1_openclaw_allowed_stages:":
                skip = True
                output.append(line)
                for stage in allowed_stages:
                    output.append(f"    - {stage}")
                continue
            if skip:
                if line.startswith("    - "):
                    continue
                skip = False
            output.append(line)
        raw = "\n".join(output) + "\n"
    workspace_path.write_text(raw, encoding="utf-8")


def _set_workspace_policy_flag(root: Path, *, key: str, value: str) -> None:
    workspace_path = root / "workspace.yaml"
    raw = workspace_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{key}:"):
            indent = line[: len(line) - len(line.lstrip(" "))]
            updated.append(f"{indent}{key}: {value}")
            replaced = True
            continue
        updated.append(line)
    if not replaced:
        raise AssertionError(f"Policy key not found in test workspace: {key}")
    workspace_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


class OrchestratorReliabilityIntegrationTest(unittest.TestCase):
    def test_failover_hook_invoked_on_primary_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)
            attempts: dict[str, int] = {"local": 0, "anthropic": 0}

            def fake_build_model(provider: str, model: str):
                del model

                def _invoke(_prompt: str) -> _FakeMessage:
                    attempts[provider] = attempts.get(provider, 0) + 1
                    if provider == "local":
                        raise TimeoutError("primary timeout")
                    return _FakeMessage("fallback succeeded")

                return _FakeLLM(_invoke)

            with patch("substrate.orchestrator._build_model", side_effect=fake_build_model):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="validate failover",
                    chain_path="chains/test-chain.yaml",
                    provider="local",
                    model="gpt-primary",
                    dry_run=False,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                )

            self.assertEqual(1, attempts["local"])
            self.assertEqual(1, attempts["anthropic"])

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(event["message"] == "Failover for step 'scope'" for event in events)
            )

            checkpoint_path = (
                root / "memory" / "reliability" / "checkpoints" / f"{run_id}.jsonl"
            )
            self.assertTrue(checkpoint_path.exists())
            checkpoints = [
                json.loads(line)
                for line in checkpoint_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(
                any(
                    cp.get("scope") == "recovery"
                    and cp.get("status") == "provider_failure"
                    for cp in checkpoints
                )
            )

    def test_idempotent_replay_recovers_without_reinvoking_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)

            run_id = "idempotent-replay-run"
            prior_artifact = root / "memory" / "runs" / "prior" / "01_scope.md"
            prior_artifact.parent.mkdir(parents=True, exist_ok=True)
            prior_artifact.write_text("recovered from checkpoint", encoding="utf-8")

            idempotency_store = IdempotencyStore(
                root / "memory" / "reliability" / "idempotency"
            )
            step_key = make_idempotency_key(run_id, "chain-step", "local", "1", "scope")
            idempotency_store.begin(run_id, step_key)
            idempotency_store.mark_completed(
                run_id,
                step_key,
                payload={
                    "artifact": str(prior_artifact),
                    "provider": "openai",
                    "model": "gpt-primary",
                },
            )

            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.orchestrator._build_model",
                side_effect=AssertionError("provider should not be invoked during replay"),
            ):
                returned_run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="recover idempotent step",
                    chain_path="chains/test-chain.yaml",
                    provider="local",
                    model="gpt-primary",
                    dry_run=False,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    run_id=run_id,
                )

            self.assertEqual(run_id, returned_run_id)
            run_row = runtime.db.get_run(run_id)
            self.assertIsNotNone(run_row)
            assert run_row is not None

            run_dir = Path(run_row["run_dir"])
            output_path = run_dir / "01_scope.md"
            self.assertTrue(output_path.exists())
            self.assertEqual(
                "recovered from checkpoint", output_path.read_text(encoding="utf-8")
            )

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"]
                    == "Recovered step 'scope' from idempotent state."
                    for event in events
                )
            )

    def test_resource_scheduler_executes_in_run_path_and_invokes_scale_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            (root / "chains" / "test-chain.yaml").write_text(
                """
name: test-chain
description: Resource orchestration integration test
defaults:
  provider: local
  models:
    openai: gpt-primary
    anthropic: claude-fallback
  retry_policy:
    max_attempts: 1
    base_delay_seconds: 0
    max_delay_seconds: 0
    jitter_ratio: 0
  failover_order:
    - anthropic
  resource_policy:
    high_pressure_queue_depth: 0
    high_pressure_latency_seconds: 0
    scale_out_queue_depth: 0
    scale_out_latency_seconds: 0
    pools:
      api_model_pool:
        location: cloud
        capability: api
        max_workers: 2
steps:
  - id: scope
    prompt: prompts/step.md
""".strip()
                + "\n",
                encoding="utf-8",
            )

            cloud_hook = _RecordingScaleHook()
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(
                runtime,
                scale_hooks=ElasticScaleHooks(cloud_hook=cloud_hook),
            )

            run_id = orchestrator.run_chain(
                repo_slug="test-repo",
                objective="exercise resource scheduler",
                chain_path="chains/test-chain.yaml",
                provider="local",
                model="gpt-primary",
                dry_run=True,
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
            )

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(event["message"] == "Resource scheduling policy attached" for event in events)
            )
            self.assertTrue(
                any(event["message"] == "Scheduled step 'scope'" for event in events)
            )

            run_row = runtime.db.get_run(run_id)
            self.assertIsNotNone(run_row)
            assert run_row is not None
            run_dir = Path(run_row["run_dir"])
            summary = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertIn("step_resource_decisions", summary)
            self.assertIn("scope", summary["step_resource_decisions"])
            self.assertIn("resource_scheduler_final_state", summary)
            self.assertGreaterEqual(len(cloud_hook.scale_out_calls), 1)

    def test_openclaw_default_off_blocks_side_lane_even_with_manual_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                side_effect=AssertionError("OpenClaw must not be invoked when feature is off"),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="openclaw off",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    and event.get("payload", {}).get("status") == "blocked"
                    and event.get("payload", {}).get("reason") == "feature_disabled"
                    for event in events
                )
            )

    def test_openclaw_manual_trigger_required_no_autonomous_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                side_effect=AssertionError(
                    "OpenClaw must not be invoked without manual trigger"
                ),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="manual trigger required",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=False,
                    openclaw_data_class="synthetic",
                )

            events = runtime.db.list_run_events(run_id)
            self.assertFalse(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    for event in events
                )
            )

    def test_openclaw_research_only_not_routed_on_non_research_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            (root / "chains" / "test-chain.yaml").write_text(
                """
name: test-chain
description: Non-research pass test
defaults:
  provider: mock
  models:
    mock: mock-model
steps:
  - id: execute
    pass: development
    prompt: prompts/step.md
""".strip()
                + "\n",
                encoding="utf-8",
            )

            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                side_effect=AssertionError("OpenClaw must stay on research pass only"),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="no production path coupling",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            events = runtime.db.list_run_events(run_id)
            self.assertFalse(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    for event in events
                )
            )

    def test_openclaw_unavailable_degrades_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                side_effect=RuntimeError("missing openclaw"),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="degrade safely",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            run_row = runtime.db.get_run(run_id)
            self.assertIsNotNone(run_row)
            assert run_row is not None
            self.assertEqual("success", run_row["status"])

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    and event.get("payload", {}).get("status") == "degraded_unavailable"
                    for event in events
                )
            )

    def test_openclaw_quarantine_and_revetting_accept_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            raw = (
                "source: internal-redacted\n"
                "Architectural lesson learned from historical failure data and safeguards.\n"
                "Operational hardening recommendation with bounded retry ceilings and policy gates.\n"
            )
            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                return_value=(raw, {"adapter": "test-adapter", "collected_at": "now"}),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="accept vetted insights",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            run_dir = root / ".research" / "openclaw" / run_id
            raw_artifact = run_dir / "research_openclaw_raw_quarantine.json"
            vetting_artifact = run_dir / "research_openclaw_vetting_report.json"
            vetted_artifact = run_dir / "research_vetted_research_artifact.json"
            self.assertTrue(raw_artifact.exists())
            self.assertTrue(vetting_artifact.exists())
            self.assertTrue(vetted_artifact.exists())

            vetting = json.loads(vetting_artifact.read_text(encoding="utf-8"))
            self.assertEqual("pass", vetting["decision"])

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    and event.get("payload", {}).get("status") == "accepted"
                    and event.get("payload", {}).get("imported_insight_count", 0) > 0
                    for event in events
                )
            )

    def test_openclaw_rejects_direct_external_code_ingestion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            raw = (
                "source: external\n"
                "```python\n"
                "def copied():\n"
                "    return 'copied verbatim'\n"
                "```\n"
            )
            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                return_value=(raw, {"adapter": "test-adapter", "collected_at": "now"}),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="reject direct ingestion",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            run_dir = root / ".research" / "openclaw" / run_id
            vetting_artifact = run_dir / "research_openclaw_vetting_report.json"
            rejected_artifact = run_dir / "research_openclaw_rejected_artifact.json"
            self.assertTrue(vetting_artifact.exists())
            self.assertTrue(rejected_artifact.exists())

            vetting = json.loads(vetting_artifact.read_text(encoding="utf-8"))
            self.assertEqual("fail", vetting["decision"])
            self.assertEqual("external_code_ingestion_detected", vetting["reason"])

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    and event.get("payload", {}).get("status") == "rejected"
                    and event.get("payload", {}).get("reason")
                    == "external_code_ingestion_detected"
                    for event in events
                )
            )

    def test_openclaw_production_stage_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                side_effect=AssertionError(
                    "OpenClaw must never invoke on production stage"
                ),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="production isolation",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="production",
                    requested_mode="observe",
                    allow_mutations=False,
                    allow_stage_skip=True,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    and event.get("payload", {}).get("status") == "blocked"
                    and event.get("payload", {}).get("reason")
                    == "stage_production_blocked"
                    for event in events
                )
            )

    def test_openclaw_revetting_cannot_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_workspace(root, retry_max_attempts=1)
            _enable_openclaw_policy(root)
            _set_workspace_policy_flag(
                root,
                key="rc1_openclaw_revetting_required",
                value="false",
            )
            runtime = SubstrateRuntime(root)
            orchestrator = Orchestrator(runtime)

            with patch(
                "substrate.research._invoke_openclaw_untrusted_output",
                side_effect=AssertionError(
                    "OpenClaw invocation must be blocked when revetting is disabled"
                ),
            ):
                run_id = orchestrator.run_chain(
                    repo_slug="test-repo",
                    objective="revetting mandatory",
                    chain_path="chains/test-chain.yaml",
                    provider="mock",
                    model="mock-model",
                    dry_run=True,
                    stage="local",
                    requested_mode="observe",
                    allow_mutations=False,
                    openclaw_manual_trigger=True,
                    openclaw_data_class="synthetic",
                )

            events = runtime.db.list_run_events(run_id)
            self.assertTrue(
                any(
                    event["message"].startswith("OpenClaw side-lane outcome")
                    and event.get("payload", {}).get("status") == "blocked"
                    and event.get("payload", {}).get("reason") == "revetting_required"
                    for event in events
                )
            )


if __name__ == "__main__":
    unittest.main()
