from __future__ import annotations

import unittest

from substrate.cli import _build_discount_swarm_plan, _build_parser


class DiscountSwarmTest(unittest.TestCase):
    def test_parser_accepts_discount_swarm_command(self) -> None:
        parser = _build_parser()
        parsed = parser.parse_args(
            [
                "discount-swarm",
                "--repo",
                "substrate-core",
                "--merchant",
                "deals",
                "--as-of-date",
                "2026-04-02",
            ]
        )
        self.assertEqual("discount-swarm", parsed.command)
        self.assertEqual("deals", parsed.merchant)
        self.assertEqual("2026-04-02", parsed.as_of_date)

    def test_plan_contains_multiple_agent_commands(self) -> None:
        plan = _build_discount_swarm_plan(
            repo_slug="substrate-core",
            merchant="Acme Shop",
            as_of_date="2026-04-02",
            lookback_days=10,
            provider="local",
            model="roo-router",
            stage="local",
        )
        commands = plan["commands"]
        self.assertEqual(5, len(commands))
        first = commands[0]
        self.assertIn("run-chain", first["command"])
        self.assertIn("Acme Shop", first["objective"])
        self.assertIn("swarm_script", plan)


if __name__ == "__main__":
    unittest.main()
