from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from substrate.registry import SubstrateRuntime


def _workspace_yaml(*, include_production_stage: bool = False, include_dev_pass: bool = False) -> str:
    stage_extra = "\n    - production" if include_production_stage else ""
    pass_extra = "\n    - development" if include_dev_pass else ""
    return (
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
  rc1_openclaw_internal_assist_enabled: true
  rc1_openclaw_manual_trigger_required: true
  rc1_openclaw_revetting_required: true
  rc1_openclaw_allowed_stages:
    - local
    - hosted_dev{stage_extra}
  rc1_openclaw_allowed_passes:
    - research{pass_extra}
  rc1_openclaw_allowed_data_classes:
    - synthetic
    - redacted
repositories:
  - slug: test-repo
    path: .
    allow_mutations: false
    default_mode: observe
""".strip()
        + "\n"
    )


class OpenClawPolicyTest(unittest.TestCase):
    def test_workspace_policy_rejects_production_openclaw_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace.yaml").write_text(
                _workspace_yaml(include_production_stage=True),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                SubstrateRuntime(root)
            self.assertIn("cannot include 'production'", str(raised.exception))

    def test_workspace_policy_rejects_non_research_openclaw_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace.yaml").write_text(
                _workspace_yaml(include_dev_pass=True),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as raised:
                SubstrateRuntime(root)
            self.assertIn("must stay within research", str(raised.exception))

    def test_runtime_openclaw_policy_production_hard_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspace.yaml").write_text(_workspace_yaml(), encoding="utf-8")
            runtime = SubstrateRuntime(root)

            allowed, reason = runtime.evaluate_openclaw_policy(
                stage="production",
                pass_name="research",
                manual_trigger=True,
                data_class="synthetic",
            )
            self.assertFalse(allowed)
            self.assertEqual("stage_production_blocked", reason)


if __name__ == "__main__":
    unittest.main()

