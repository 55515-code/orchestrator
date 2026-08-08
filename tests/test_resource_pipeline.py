from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from substrate.crypto import ResourceInventory
from substrate.pipelines.expansion_trigger import ExpansionTrigger
from substrate.pipelines.quality_gate import QualityGate
from substrate.pipelines.resource_pipeline import ResourcePipeline


class QualityGateTest(unittest.TestCase):
    def test_good_checklist_passes(self) -> None:
        content = _good_checklist()
        result = QualityGate().validate(content, resource_type="checklist", title="A Real Checklist")
        self.assertTrue(result["passed"], result["issues"])

    def test_banned_term_fails(self) -> None:
        content = _good_checklist().replace("Educational material", "Free money now")
        result = QualityGate().validate(content, resource_type="checklist", title="A Real Checklist")
        self.assertFalse(result["passed"])
        self.assertTrue(any("banned term" in issue for issue in result["issues"]))

    def test_placeholder_fails(self) -> None:
        content = _good_checklist().replace("Adapt this", "TODO: adapt this")
        result = QualityGate().validate(content, resource_type="checklist", title="A Real Checklist")
        self.assertFalse(result["passed"])
        self.assertTrue(any("placeholder" in issue for issue in result["issues"]))

    def test_short_content_fails(self) -> None:
        result = QualityGate().validate(
            "# T\n\n## A\n\n- [ ] one\n- [ ] two\n",
            resource_type="checklist",
            title="A Real Checklist",
        )
        self.assertFalse(result["passed"])
        self.assertTrue(any("too short" in issue for issue in result["issues"]))


def _good_checklist() -> str:
    lines = [
        "# A Real Checklist",
        "",
        "Practical checklist for small teams implementing a control program.",
        "Each item below is a concrete, verifiable step that produces evidence",
        "an auditor or reviewer can inspect and confirm during an assessment.",
        "Work through the phases in order and record owners and dates as you go.",
        "",
        "## Phase 1 — Scope and Ownership",
        "",
        "- [ ] Name an owner",
        "- [ ] Define in-scope systems",
        "- [ ] Record the business drivers",
        "- [ ] Set a review date",
        "- [ ] Identify stakeholders who approve the scope",
        "- [ ] Document out-of-scope items with rationale",
        "",
        "## Phase 2 — Implementation",
        "",
        "- [ ] Inventory current controls",
        "- [ ] Identify gaps against the baseline",
        "- [ ] Assign each gap an owner",
        "- [ ] Document compensating controls for deferred items",
        "- [ ] Map controls to framework requirements",
        "- [ ] Confirm compensating controls are reviewed",
        "",
        "## Phase 3 — Verification",
        "",
        "- [ ] Collect evidence for each control",
        "- [ ] Sample controls to confirm operation",
        "- [ ] Record exceptions with remediation plans",
        "- [ ] Store evidence for auditor retrieval",
        "- [ ] Timestamp and attribute evidence",
        "- [ ] Cross-check evidence against the inventory",
        "",
        "## Phase 4 — Operate and Improve",
        "",
        "- [ ] Add recurring review to the calendar",
        "- [ ] Track metrics: coverage, exceptions, time to remediate",
        "- [ ] Re-run after any significant change",
        "- [ ] Fold lessons learned into the next cycle",
        "- [ ] Publish a one-page leadership summary",
        "",
        "## Notes",
        "",
        "Adapt this checklist to your environment. Items marked in scope must",
        "have evidence; out-of-scope items need a written rationale. Every",
        "control should have a named owner, a review cadence, and a place",
        "where its evidence lives so audits run smoothly.",
        "",
        "---",
        "Educational material.",
        "",
    ]
    return "\n".join(lines)


def _seed_market_demand(root: Path) -> None:
    sidecar = root / ".research" / "market-demand"
    sidecar.mkdir(parents=True, exist_ok=True)
    (sidecar / "2026-08-08-x402-payment-protocol.json").write_text(
        json.dumps(
            {
                "target_id": "x402-payment-protocol",
                "kind": "protocol",
                "demand_score": 0.9,
                "competition": 0.3,
            }
        ),
        encoding="utf-8",
    )
    (sidecar / "2026-08-08-msp-partner-channel.json").write_text(
        json.dumps(
            {
                "target_id": "msp-partner-channel",
                "kind": "channel",
                "demand_score": 0.4,
                "competition": 0.5,
            }
        ),
        encoding="utf-8",
    )


class ResourcePipelineTest(unittest.TestCase):
    def test_skipped_below_demand_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_market_demand(root)
            pipeline = ResourcePipeline(root)
            report = pipeline.run("msp-partner-channel", "checklist")
            self.assertEqual("skipped", report["status"])

    def test_draft_then_publish_with_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_market_demand(root)
            pipeline = ResourcePipeline(root)
            report = pipeline.run("x402-payment-protocol", "checklist", category="ai-tooling")
            self.assertEqual("pending_approval", report["status"])
            draft = root / str(report["draft"])
            self.assertTrue(draft.exists())

            published = pipeline.run(
                "x402-payment-protocol",
                "checklist",
                category="ai-tooling",
                price_usdc=15.0,
                directive="human: publish x402 checklist",
            )
            self.assertEqual("published", published["status"])
            catalog = json.loads((root / "resources" / "catalog.json").read_text(encoding="utf-8"))
            self.assertTrue(any(r["id"] == "x402-payment-protocol" for r in catalog["resources"]))

    def test_quality_gate_rejects_bad_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_market_demand(root)
            pipeline = ResourcePipeline(root)
            bad_title, bad_content = pipeline.generate_content("x402-payment-protocol", "checklist")
            bad_content = bad_content.replace("Phase 1", "Phase 1 — Free money now")
            gate = QualityGate()
            result = gate.validate(bad_content, resource_type="checklist", title=bad_title)
            self.assertFalse(result["passed"])


class ExpansionTriggerTest(unittest.TestCase):
    def test_candidates_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_market_demand(root)
            trigger = ExpansionTrigger(root)
            candidates = trigger.candidates()
            ids = {c["target_id"] for c in candidates}
            self.assertIn("x402-payment-protocol", ids)
            self.assertNotIn("msp-partner-channel", ids)

    def test_queue_requires_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_market_demand(root)
            trigger = ExpansionTrigger(root)
            with self.assertRaises(PermissionError):
                trigger.queue_tasks()

    def test_queue_and_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_market_demand(root)
            trigger = ExpansionTrigger(root)
            result = trigger.queue_tasks(directive="human: queue expansion tasks")
            self.assertIn("x402-payment-protocol", result["queued"])
            backlog = trigger.backlog()
            self.assertEqual(1, len(backlog))


class ResourceInventoryTest(unittest.TestCase):
    def test_publish_requires_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "resources" / "drafts").mkdir(parents=True)
            draft = root / "resources" / "drafts" / "x.md"
            draft.write_text("# Draft\n", encoding="utf-8")
            inventory = ResourceInventory(root)
            with self.assertRaises(PermissionError):
                inventory.publish(
                    {"id": "x", "file_path": str(draft.relative_to(root))}
                )

    def test_checksum_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "resources" / "compliance").mkdir(parents=True)
            (root / "resources" / "compliance" / "a.md").write_text("# A\n", encoding="utf-8")
            inventory = ResourceInventory(root)
            inventory.publish(
                {
                    "id": "a",
                    "file_path": "resources/compliance/a.md",
                    "price_usdc": 10.0,
                },
                directive="human: publish a",
            )
            report = inventory.validate_checksums()
            self.assertTrue(report["ok"])
            (root / "resources" / "compliance" / "a.md").write_text("# CHANGED\n", encoding="utf-8")
            report = inventory.validate_checksums()
            self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
