from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from substrate.agents import AgentConfigError, load_agents_config, run_agent
from substrate.orchestrator import Orchestrator
from substrate.registry import SubstrateRuntime


def _write_workspace_yaml(root: Path) -> None:
    (root / "workspace.yaml").write_text(
        """
version: 1
policy:
  default_mode: observe
  require_source_facts_before_mutation: true
  enforce_stage_flow: false
  stage_sequence:
    - local
  pass_sequence:
    - research
    - development
repositories:
  - slug: test-repo
    path: .
    allow_mutations: true
    default_mode: observe
    tasks: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_agents_yaml(root: Path, role: str, agent_id: str, tier: int, cadence: str = "weekly") -> None:
    (root / "agents.yaml").write_text(
        f"""
version: 1
agents:
  - id: {agent_id}
    role: {role}
    repo_slug: test-repo
    pass: research
    cadence: {cadence}
    autonomy_tier: {tier}
    provider: mock
    command: agent-run --role {role} --repo test-repo
""".strip()
        + "\n",
        encoding="utf-8",
    )


class MarketResearchAgentTest(unittest.TestCase):
    def test_writes_findings_and_posture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_agents_yaml(root, "market-research", "market-research", 0)
            (root / "research-targets.yaml").write_text(
                """
version: 1
targets:
  - id: x402-payment-protocol
    kind: protocol
    name: x402
    focus: agent micropayments
    questions:
      - what manifest format?
    demand_score: 0.8
    competition: 0.3
""".strip()
                + "\n",
                encoding="utf-8",
            )
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agent = load_agents_config(root)[0]
            result = run_agent(runtime, orchestrator, agent)
            self.assertEqual("success", result.status)
            notes = list((root / ".research" / "market-demand").glob("*.md"))
            self.assertEqual(1, len(notes))
            posture = json.loads((root / "state" / "sales-posture.json").read_text(encoding="utf-8"))
            self.assertTrue(posture["always_selling"])
            self.assertGreaterEqual(posture["live_count"], 0)

    def test_unknown_role_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_agents_yaml(root, "market-research", "market-research", 0)
            (root / "agents.yaml").write_text(
                (root / "agents.yaml").read_text(encoding="utf-8").replace(
                    "role: market-research", "role: rogue-research"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(AgentConfigError):
                load_agents_config(root)


class ResourceGeneratorAgentTest(unittest.TestCase):
    def _backlog(self, root: Path) -> None:
        state = root / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "resource-backlog.json").write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "target_id": "llm-discovery",
                            "kind": "channel",
                            "demand_score": 0.9,
                            "queued_at": "2026-08-08T00:00:00Z",
                            "status": "queued",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def test_draft_without_directive_stays_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_agents_yaml(root, "resource-generator", "resource-gen", 1)
            self._backlog(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agent = load_agents_config(root)[0]
            result = run_agent(runtime, orchestrator, agent)
            self.assertEqual("success", result.status)
            self.assertTrue(result.actions)
            self.assertEqual("pending_approval", result.actions[0]["status"])
            drafts = list((root / "resources" / "drafts").glob("*.md"))
            self.assertEqual(1, len(drafts))
            backlog = json.loads((root / "state" / "resource-backlog.json").read_text(encoding="utf-8"))
            self.assertNotEqual("queued", backlog["tasks"][0]["status"])
            rationale = list((root / ".research" / "resource-generation").glob("*.md"))
            self.assertEqual(1, len(rationale))

    def test_idempotency_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_workspace_yaml(root)
            _write_agents_yaml(root, "resource-generator", "resource-gen", 1)
            self._backlog(root)
            runtime = SubstrateRuntime(root=root)
            orchestrator = Orchestrator(runtime)
            agent = load_agents_config(root)[0]
            first = run_agent(runtime, orchestrator, agent)
            self.assertEqual("success", first.status)
            second = run_agent(runtime, orchestrator, agent)
            self.assertEqual("skipped", second.status)


if __name__ == "__main__":
    unittest.main()
