from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from substrate.crypto import (
    MICRO_SPEND_FLOOR_USD,
    Opportunity,
    OpportunityEngine,
    PricingEngine,
    RevenueTracker,
)

DIRECTIVE = "human: apply price update"


def _pricing(tmp: str) -> PricingEngine:
    return PricingEngine(
        {"alpha": 100.0, "beta": 50.0},
        rate_fetcher=lambda: {"POL": 0.5, "ETH": 2000.0},
        state_path=Path(tmp) / "prices.json",
    )


class PricingEngineTest(unittest.TestCase):
    def test_stablecoin_prices_always_available(self) -> None:
        engine = _pricing(tempfile.mkdtemp())
        price = engine.get_price("alpha")
        self.assertEqual(100.0, price["usdc"])
        self.assertEqual(100.0, price["dai"])

    def test_volatile_price_uses_network_rate(self) -> None:
        engine = _pricing(tempfile.mkdtemp())
        price = engine.get_price("alpha", network="polygon")
        self.assertEqual(100.0 / 0.5, price["pol"])

    def test_update_prices_requires_directive(self) -> None:
        engine = _pricing(tempfile.mkdtemp())
        with self.assertRaises(PermissionError):
            engine.update_prices({"alpha": 90.0})

    def test_update_prices_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = _pricing(tmp)
            result = engine.update_prices({"alpha": 90.0}, directive=DIRECTIVE)
            self.assertIn("alpha", result["updated"])
            self.assertEqual(90.0, engine.effective_base_prices()["alpha"])

    def test_competitive_proposal_respects_floor(self) -> None:
        engine = _pricing(tempfile.mkdtemp())
        proposals = engine.propose_competitive_prices(
            comparator_prices={"alpha": 60.0, "beta": 40.0},
        )
        self.assertIn("alpha", proposals)
        self.assertGreaterEqual(proposals["alpha"]["to_usd"], 100.0 * 0.5)

    def test_competitive_update_blocked_when_trend_down(self) -> None:
        engine = _pricing(tempfile.mkdtemp())
        with self.assertRaises(PermissionError):
            engine.apply_competitive_update(
                comparator_prices={"alpha": 60.0},
                revenue_trend_ok=False,
                directive=DIRECTIVE,
            )


class RevenueTrackerTest(unittest.TestCase):
    def test_record_and_trend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tracker = RevenueTracker(Path(tmp))
            tracker.record_payment("alpha", 10.0, tx_hash="0x1")
            tracker.record_payment("beta", 15.0, tx_hash="0x2")
            self.assertEqual(25.0, tracker.monthly_totals()[0]["total_usd"])
            with self.assertRaises(ValueError):
                tracker.record_payment("alpha", 5.0, tx_hash="0x1")

    def test_trend_needs_two_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tracker = RevenueTracker(Path(tmp))
            trend = tracker.trend()
            self.assertFalse(trend["upward"])
            self.assertIn("two months", trend["note"])


class OpportunityEngineTest(unittest.TestCase):
    def _engine(self, tmp: str, stack: float = 1.0) -> OpportunityEngine:
        engine = OpportunityEngine(Path(tmp))
        engine._save({"allocations": [], "stack_usd": stack})
        return engine

    def test_opportunity_below_floor_blocked(self) -> None:
        engine = self._engine(tempfile.mkdtemp())
        opp = Opportunity("o1", title="t", cost_usd=0.0001, expected_return_usd=0.0005)
        result = engine.evaluate(opp)
        self.assertFalse(result["approved"])
        self.assertIn("above_micro_floor", result["blocked_reasons"])

    def test_opportunity_at_floor_and_ev_positive_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._engine(tmp, stack=1.0)
            opp = Opportunity(
                "o2",
                title="micro ad",
                cost_usd=MICRO_SPEND_FLOOR_USD,
                expected_return_usd=0.01,
            )
            result = engine.evaluate(opp)
            self.assertTrue(result["approved"])
            allocation = engine.allocate(opp, directive="human: run micro ad")
            self.assertTrue(allocation["approved"])
            self.assertLess(allocation["stack_after_usd"], 1.0)

    def test_allocation_requires_directive(self) -> None:
        engine = self._engine(tempfile.mkdtemp())
        opp = Opportunity("o3", title="t", cost_usd=0.001, expected_return_usd=0.01)
        with self.assertRaises(PermissionError):
            engine.allocate(opp)

    def test_principal_never_allocated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._engine(tmp, stack=0.0)
            opp = Opportunity("o4", title="t", cost_usd=0.001, expected_return_usd=0.01)
            result = engine.evaluate(opp)
            self.assertFalse(result["approved"])
            self.assertIn("within_allocation", result["blocked_reasons"])

    def test_return_credits_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._engine(tmp, stack=1.0)
            opp = Opportunity("o5", title="t", cost_usd=0.001, expected_return_usd=0.01)
            engine.allocate(opp, directive="human: run")
            before = engine.stack_balance()
            engine.record_return("o5", 0.005)
            self.assertGreater(engine.stack_balance(), before)


if __name__ == "__main__":
    unittest.main()
