from __future__ import annotations

import unittest

from fastapi import HTTPException

from substrate.cli import _build_parser
from substrate.web import _validate_openclaw_data_class


class OpenClawEntrypointValidationTest(unittest.TestCase):
    def test_cli_spawn_agent_workloads_aliases_parse(self) -> None:
        parser = _build_parser()
        parsed = parser.parse_args(
            [
                "spawn-agent-workloads",
                "--cycle",
                "3",
                "--repo",
                "substrate-core",
                "--stage",
                "local",
                "--concurrency-limit",
                "10",
                "--agent-provider",
                "mock",
            ]
        )
        self.assertEqual("spawn-agent-workloads", parsed.command)
        self.assertEqual(3, parsed.cycle)
        self.assertEqual(10, parsed.concurrency_limit)

    def test_cli_rejects_unapproved_openclaw_data_class(self) -> None:
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "run-chain",
                    "--repo",
                    "substrate-core",
                    "--objective",
                    "validate",
                    "--openclaw-manual-trigger",
                    "--openclaw-data-class",
                    "production",
                ]
            )

    def test_cli_accepts_approved_openclaw_data_class(self) -> None:
        parser = _build_parser()
        parsed = parser.parse_args(
            [
                "run-chain",
                "--repo",
                "substrate-core",
                "--objective",
                "validate",
                "--openclaw-manual-trigger",
                "--openclaw-data-class",
                "synthetic",
            ]
        )
        self.assertTrue(parsed.openclaw_manual_trigger)
        self.assertEqual("synthetic", parsed.openclaw_data_class)

    def test_web_rejects_unapproved_openclaw_data_class(self) -> None:
        with self.assertRaises(HTTPException):
            _validate_openclaw_data_class("production")

    def test_web_accepts_approved_openclaw_data_class(self) -> None:
        self.assertEqual("redacted", _validate_openclaw_data_class("redacted"))


if __name__ == "__main__":
    unittest.main()
