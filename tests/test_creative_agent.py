"""Tests for the creative-agent role (ARIN creative production substrate).

Covers the bounded, zero-cost scheduled maintenance behavior, directive
classification and Tier gating, scaffold/hash/quality self-checks, and
resumable state handling. Mirrors the runtime stub style used in
``tests/test_agents.py``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from substrate import _utils
from substrate.agents import creative


def _make_runtime(tmp: Path) -> SimpleNamespace:
    """Build a runtime stub backed by a real temp directory tree."""
    (tmp / "creative" / "ARIN").mkdir(parents=True, exist_ok=True)
    (tmp / "state").mkdir(parents=True, exist_ok=True)
    (tmp / "research").mkdir(parents=True, exist_ok=True)

    def resolve_repo(slug: str) -> Any:
        return SimpleNamespace(slug=slug)

    return SimpleNamespace(
        root=tmp,
        paths={"state": tmp / "state", "research": tmp / "research"},
        resolve_repo=resolve_repo,
    )


def _make_agent(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": "creative-arin",
        "repo_slug": "substrate-core",
        "autonomy_tier": 1,
        "provider": "local",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _build_scaffold(tmp: Path) -> Path:
    """Recreate the ARIN module scaffold with a canonical poster."""
    project = tmp / "creative" / "ARIN"
    for module in creative.MODULES:
        (project / module).mkdir(parents=True, exist_ok=True)
    for rel in creative.REQUIRED_FILES:
        (project / rel).write_text(f"# {rel}\n", encoding="utf-8")
    source_poster = (
        Path(__file__).resolve().parents[1]
        / "creative"
        / "ARIN"
        / "assets"
        / "ARIN_final_poster.png"
    )
    if source_poster.exists():
        shutil.copy2(source_poster, project / creative.CANONICAL_ASSET)
    return project


def _state(runtime: Any) -> dict[str, Any]:
    return _utils.load_json(
        runtime.paths["state"] / "arin-production.json", default={}
    )


class CreativeAgentRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.runtime = _make_runtime(self.tmp)
        _build_scaffold(self.tmp)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_scheduled_maintenance_run_is_success(self) -> None:
        result = creative.run(self.runtime, None, _make_agent())
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["actions"][0]["action"], "scheduled-maintenance")
        self.assertEqual(result["actions"][0]["tier"], 0)
        self.assertTrue(result["actions"][0]["allowed"])

        state = _state(self.runtime)
        self.assertEqual(state["ledger"]["runs"], 1)
        self.assertEqual(state["ledger"]["cash_costs_usd"], 0.0)
        self.assertEqual(state["telemetry"]["runs"], 1)
        self.assertEqual(state["phases"]["A"], "not_started")

        note = (self.runtime.paths["research"] / "creative-arin").glob("*.md")
        notes = list(note)
        self.assertEqual(len(notes), 1)
        self.assertIn("Routine scheduled maintenance", notes[0].read_text(encoding="utf-8"))

    def test_state_resumes_existing_counts(self) -> None:
        path = self.runtime.paths["state"] / "arin-production.json"
        path.write_text(
            json.dumps(
                {
                    "phases": {"A": "in_progress"},
                    "ledger": {"cash_costs_usd": 0.0, "runs": 5},
                    "telemetry": {"last_run": "2026-08-08T00:00:00+00:00", "runs": 5},
                }
            ),
            encoding="utf-8",
        )
        result = creative.run(self.runtime, None, _make_agent())
        self.assertEqual(result["status"], "success")
        state = _state(self.runtime)
        self.assertEqual(state["ledger"]["runs"], 6)
        self.assertEqual(state["telemetry"]["runs"], 6)
        self.assertEqual(state["phases"]["A"], "in_progress")

    def test_draft_directive_classified_tier1(self) -> None:
        result = creative.run(
            self.runtime,
            None,
            _make_agent(),
            directive="phase-a: draft the world bible outline",
        )
        self.assertEqual(result["actions"][0]["action"], "draft-or-plan")
        self.assertEqual(result["actions"][0]["tier"], 1)
        self.assertTrue(result["actions"][0]["allowed"])

    def test_publish_directive_classified_tier2(self) -> None:
        # Tier 2 gates are directive-based by design: an explicit human
        # directive authorizes the action; the unattended cadence never
        # passes one, so publishing cannot fire from the timer.
        result = creative.run(
            self.runtime,
            None,
            _make_agent(),
            directive="publish the finished manuscript to the storefront",
        )
        action = result["actions"][0]
        self.assertEqual(action["action"], "publish")
        self.assertEqual(action["tier"], 2)
        self.assertTrue(action["allowed"])
        self.assertEqual(action["reason"], "human_directive")

    def test_missing_required_file_marks_attention(self) -> None:
        (self.tmp / "creative" / "ARIN" / "canon" / "ARIN_CANON.md").unlink()
        result = creative.run(self.runtime, None, _make_agent())
        self.assertEqual(result["status"], "attention")
        self.assertIn("scaffold incomplete", result["note"])

    def test_missing_module_marks_attention(self) -> None:
        shutil.rmtree(self.tmp / "creative" / "ARIN" / "telemetry")
        result = creative.run(self.runtime, None, _make_agent())
        self.assertEqual(result["status"], "attention")
        self.assertIn("scaffold incomplete", result["note"])

    def test_asset_hash_mismatch_marks_attention(self) -> None:
        poster = self.tmp / "creative" / "ARIN" / creative.CANONICAL_ASSET
        poster.write_bytes(b"tampered-poster-bytes")
        result = creative.run(self.runtime, None, _make_agent())
        self.assertEqual(result["status"], "attention")
        self.assertIn("canonical asset hash mismatch", result["note"])

    def test_quality_gate_flags_secret_marker(self) -> None:
        manuscript = self.tmp / "creative" / "ARIN" / "manuscript"
        manuscript.mkdir(parents=True, exist_ok=True)
        (manuscript / "chapter-01.md").write_text(
            "draft text with api_key=sk-abc123 inside", encoding="utf-8"
        )
        result = creative.run(self.runtime, None, _make_agent())
        self.assertEqual(result["status"], "attention")
        self.assertIn("quality self-check findings", result["note"])

    def test_quality_finding_blocks_tier1_directive(self) -> None:
        manuscript = self.tmp / "creative" / "ARIN" / "manuscript"
        manuscript.mkdir(parents=True, exist_ok=True)
        (manuscript / "chapter-01.md").write_text(
            "draft text with api_key=sk-abc123 inside", encoding="utf-8"
        )
        result = creative.run(
            self.runtime,
            None,
            _make_agent(),
            directive="phase-a: draft the world bible outline",
        )
        # Tier 1 actions require green validation; a secret-marker finding
        # fails the quality gate, so the draft action must be denied.
        self.assertEqual(result["actions"][0]["tier"], 1)
        self.assertFalse(result["actions"][0]["allowed"])
        self.assertEqual(result["actions"][0]["reason"], "validation_not_green")
        self.assertEqual(result["status"], "attention")

    def test_unknown_repo_raises(self) -> None:
        runtime = SimpleNamespace(
            root=self.tmp,
            paths={"state": self.tmp / "state", "research": self.tmp / "research"},
            resolve_repo=lambda slug: (_ for _ in ()).throw(KeyError(slug)),
        )
        with self.assertRaises(KeyError):
            creative.run(runtime, None, _make_agent())


class CreativeHelpersTest(unittest.TestCase):
    def test_directive_classification(self) -> None:
        self.assertEqual(
            creative._classify_directive(""), ("scheduled-maintenance", 0)
        )
        self.assertEqual(
            creative._classify_directive("draft chapter one"),
            ("draft-or-plan", 1),
        )
        tag, tier = creative._classify_directive("spend on advertising")
        self.assertEqual(tier, 2)
        self.assertIn(tag, creative.TIER2_ACTION_KEYWORDS)


if __name__ == "__main__":
    unittest.main()
