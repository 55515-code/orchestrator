from __future__ import annotations

import unittest
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if "yaml" not in sys.modules:
    sys.modules["yaml"] = types.ModuleType("yaml")

from substrate.cli import _build_parser


class CliAliasParsingTest(unittest.TestCase):
    def test_spawn_agent_workloads_alias_maps_to_community_cycle_arguments(self) -> None:
        parser = _build_parser()
        parsed = parser.parse_args(
            [
                "spawn-agent-workloads",
                "--cycle",
                "7",
                "--repo",
                "substrate-core",
                "--stage",
                "local",
                "--concurrency-limit",
                "12",
                "--agent-provider",
                "mock",
                "--agent-model",
                "roo-router",
                "--seed",
                "100",
            ]
        )
        self.assertEqual("spawn-agent-workloads", parsed.command)
        self.assertEqual(7, parsed.cycle)
        self.assertEqual("substrate-core", parsed.repo)
        self.assertEqual("local", parsed.stage)
        self.assertEqual(12, parsed.concurrency_limit)
        self.assertEqual("mock", parsed.agent_provider)
        self.assertEqual("roo-router", parsed.agent_model)
        self.assertEqual(100, parsed.seed)


if __name__ == "__main__":
    unittest.main()
