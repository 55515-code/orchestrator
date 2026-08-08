from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from substrate.crypto import PaymentFlowGovernance

DIRECTIVE = "human: approve payment-flow change"


def _write_rules(root: Path) -> None:
    (root / "crypto-rules.yaml").write_text(
        """
version: 1
documentation:
  runbook: docs/CRYPTO_PAYMENT_RUNBOOK.md
  max_age_days: 90
review:
  state: state/crypto/reviews.json
  required_checklist:
    - docs_updated
    - tests_green
    - threat_model_considered
    - rollback_documented
rules:
  - id: PF-001
    title: Documentation is mandatory and current
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_runbook(root: Path, last_verified: str) -> None:
    path = root / "docs" / "CRYPTO_PAYMENT_RUNBOOK.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: Runbook\nlast_verified: {last_verified}\n"
        "components: [workers/payment-verifier/index.js]\n"
        "---\n\n# Runbook\n",
        encoding="utf-8",
    )


class PaymentFlowGovernanceTest(unittest.TestCase):
    def _governance(self, tmp: str) -> tuple[PaymentFlowGovernance, Path]:
        root = Path(tmp)
        _write_rules(root)
        return PaymentFlowGovernance(root), root

    def test_missing_rules_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(FileNotFoundError):
            PaymentFlowGovernance(Path(tmp))

    def test_gate_change_requires_directive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, _ = self._governance(tmp)
            with self.assertRaises(PermissionError):
                governance.gate_change(
                    "c1", summary="x", directive="", docs_updated=True, tests_green=True
                )

    def test_gate_change_requires_all_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, _ = self._governance(tmp)
            with self.assertRaises(PermissionError) as ctx:
                governance.gate_change(
                    "c2",
                    summary="x",
                    directive=DIRECTIVE,
                    docs_updated=False,
                    tests_green=True,
                )
            self.assertIn("docs_updated", str(ctx.exception))

    def test_gate_change_approves_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, root = self._governance(tmp)
            review = governance.gate_change(
                "c3",
                summary="add undercut pricing",
                directive=DIRECTIVE,
                docs_updated=True,
                tests_green=True,
                checklist={
                    "docs_updated": True,
                    "tests_green": True,
                    "threat_model_considered": True,
                    "rollback_documented": True,
                },
            )
            self.assertEqual("c3", review["change_id"])
            payload = yaml.safe_load(
                (root / "state" / "crypto" / "reviews.json").read_text(encoding="utf-8")
            )
            self.assertEqual(1, len(payload["reviews"]))

    def test_docs_status_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, _ = self._governance(tmp)
            status = governance.docs_status()
            self.assertFalse(status["exists"])
            self.assertFalse(status["current"])

    def test_docs_status_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, root = self._governance(tmp)
            _write_runbook(root, (datetime.now(UTC) - timedelta(days=200)).date().isoformat())
            status = governance.docs_status()
            self.assertTrue(status["exists"])
            self.assertFalse(status["current"])

    def test_docs_status_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, root = self._governance(tmp)
            _write_runbook(root, datetime.now(UTC).date().isoformat())
            status = governance.docs_status()
            self.assertTrue(status["current"])
            self.assertIn("workers/payment-verifier/index.js", status["components"])

    def test_verify_all_requires_green_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            governance, _ = self._governance(tmp)
            report = governance.verify_all()
            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"]["documentation"]["current"])


if __name__ == "__main__":
    unittest.main()
