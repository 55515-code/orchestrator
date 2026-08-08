from __future__ import annotations

import unittest
from pathlib import Path

from substrate.models import PolicyConfig, WorkspaceConfig
from substrate.orchestrator import Orchestrator
from substrate.registry import SubstrateRuntime


class TestRestrictedTerms(unittest.TestCase):
    def _make_orchestrator(self, restricted_terms=None):
        root = Path(".")
        runtime = SubstrateRuntime(root)
        policy = PolicyConfig(restricted_terms=restricted_terms or [])
        runtime.workspace.policy = policy
        return Orchestrator(runtime)

    def test_no_restricted_terms_passes(self):
        orch = self._make_orchestrator(restricted_terms=[])
        orch._assert_restricted_terms("hello world", context="test")

    def test_restricted_term_detected(self):
        orch = self._make_orchestrator(restricted_terms=["concepts2code", "dialconnection"])
        with self.assertRaises(PermissionError) as ctx:
            orch._assert_restricted_terms("work at concepts2code", context="resume")
        self.assertIn("concepts2code", str(ctx.exception))

    def test_restricted_term_case_insensitive(self):
        orch = self._make_orchestrator(restricted_terms=["concepts2code"])
        with self.assertRaises(PermissionError):
            orch._assert_restricted_terms("Concepts2Code LLC", context="profile")

    def test_multiple_restricted_terms(self):
        orch = self._make_orchestrator(restricted_terms=["concepts2code", "dialconnection"])
        with self.assertRaises(PermissionError) as ctx:
            orch._assert_restricted_terms("dialconnection and concepts2code", context="test")
        self.assertIn("dialconnection", str(ctx.exception))
        self.assertIn("concepts2code", str(ctx.exception))

    def test_partial_match_detected(self):
        orch = self._make_orchestrator(restricted_terms=["concepts2code.com"])
        with self.assertRaises(PermissionError):
            orch._assert_restricted_terms("visit concepts2code.com for more", context="url")

    def test_clean_text_passes_with_terms_configured(self):
        orch = self._make_orchestrator(restricted_terms=["concepts2code", "dialconnection"])
        orch._assert_restricted_terms("safe clean text about linux and kubernetes", context="test")


if __name__ == "__main__":
    unittest.main()
