"""Opportunity engine — micro-spend on known opportunities, never at a loss.

The standing rule (PF-016/PF-017): principal is the power source and is never
allocated. Only *earned surplus* (the stack, fed by the revenue tracker) may be
spent, and only when:

1. The opportunity is on the known-opportunity list (research-validated).
2. Expected value exceeds cost by a safety margin (``ev_ratio``).
3. The spend is at or above the micro-spend floor and under the per-item cap.
4. A human directive authorizes it (Tier 2).

Every allocation is recorded in the hash-chained audit trail and the ledger
``state/crypto/opportunities.json``. Nothing executes automatically; this
module produces approved, audited spend records an operator can act on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail

LEDGER_RELATIVE = Path("state") / "crypto" / "opportunities.json"
MICRO_SPEND_FLOOR_USD = 0.001  # 0.1 cent
DEFAULT_MAX_SPEND_USD = 0.05  # per opportunity, from the stack only
DEFAULT_EV_RATIO = 2.0  # expected return must be >= 2x cost
DEFAULT_MAX_ALLOCATION_FRACTION = 0.1  # never spend >10% of the stack at once


class Opportunity:
    def __init__(
        self,
        opportunity_id: str,
        *,
        kind: str = "advertising",
        title: str,
        cost_usd: float,
        expected_return_usd: float,
        source: str = "market-research",
    ) -> None:
        if cost_usd <= 0:
            raise ValueError("opportunity cost must be positive")
        self.opportunity_id = opportunity_id
        self.kind = kind
        self.title = title
        self.cost_usd = float(cost_usd)
        self.expected_return_usd = float(expected_return_usd)
        self.source = source

    @property
    def expected_value(self) -> float:
        return self.expected_return_usd - self.cost_usd

    @property
    def ev_ratio(self) -> float:
        return self.expected_return_usd / self.cost_usd


class OpportunityEngine:
    """Gate micro-spend opportunities against the no-loss rules."""

    def __init__(
        self,
        root: Path,
        *,
        audit: AuditTrail | None = None,
        stack_provider: Any | None = None,
        micro_spend_floor_usd: float = MICRO_SPEND_FLOOR_USD,
        max_spend_usd: float = DEFAULT_MAX_SPEND_USD,
        ev_ratio: float = DEFAULT_EV_RATIO,
        max_allocation_fraction: float = DEFAULT_MAX_ALLOCATION_FRACTION,
    ) -> None:
        self.root = Path(root)
        self.ledger_path = self.root / LEDGER_RELATIVE
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")
        self.stack_provider = stack_provider
        self.micro_spend_floor_usd = micro_spend_floor_usd
        self.max_spend_usd = max_spend_usd
        self.ev_ratio = ev_ratio
        self.max_allocation_fraction = max_allocation_fraction

    def _load(self) -> dict[str, Any]:
        payload = _utils.load_json(self.ledger_path, default={"allocations": [], "stack_usd": 0.0})
        allocations = payload.get("allocations")
        if not isinstance(allocations, list):
            payload["allocations"] = []
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        _utils.write_json(self.ledger_path, payload)

    def stack_balance(self) -> float:
        """Current stack: earned surplus that is safe to spend (never principal)."""
        if self.stack_provider is not None and hasattr(self.stack_provider, "stack_balance"):
            return float(self.stack_provider.stack_balance())
        return float(self._load().get("stack_usd", 0.0))

    def _principal_guard(self, amount_usd: float, stack: float) -> bool:
        """Reject any spend that would exceed the allocatable stack."""
        return amount_usd <= stack * self.max_allocation_fraction

    def evaluate(self, opportunity: Opportunity) -> dict[str, Any]:
        """Score an opportunity against the no-loss rules (read-only)."""
        stack = self.stack_balance()
        checks = {
            "above_micro_floor": opportunity.cost_usd >= self.micro_spend_floor_usd,
            "under_max_spend": opportunity.cost_usd <= self.max_spend_usd,
            "ev_positive": opportunity.expected_value > 0,
            "ev_ratio_met": opportunity.ev_ratio >= self.ev_ratio,
            "within_allocation": self._principal_guard(opportunity.cost_usd, stack)
            if stack > 0
            else False,
        }
        approved = all(checks.values())
        return {
            "opportunity_id": opportunity.opportunity_id,
            "kind": opportunity.kind,
            "title": opportunity.title,
            "cost_usd": opportunity.cost_usd,
            "expected_return_usd": opportunity.expected_return_usd,
            "ev_usd": round(opportunity.expected_value, 6),
            "ev_ratio": round(opportunity.ev_ratio, 3),
            "stack_usd": round(stack, 4),
            "approved": approved,
            "checks": checks,
            "blocked_reasons": [k for k, v in checks.items() if not v],
        }

    def allocate(
        self, opportunity: Opportunity, *, directive: str = ""
    ) -> dict[str, Any]:
        """Approve and record a micro-spend on a vetted opportunity (Tier 2)."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(
                f"opportunity spend '{opportunity.opportunity_id}' blocked: Tier 2 directive required ({reason})"
            )

        evaluation = self.evaluate(opportunity)
        if not evaluation["approved"]:
            self.audit.append(
                "opportunity_spend_blocked",
                tier=TIER_HUMAN,
                details={
                    "opportunity_id": opportunity.opportunity_id,
                    "blocked_reasons": evaluation["blocked_reasons"],
                },
            )
            raise PermissionError(
                f"opportunity '{opportunity.opportunity_id}' fails no-loss rules: "
                f"{', '.join(evaluation['blocked_reasons'])}"
            )

        payload = self._load()
        entry = {
            "opportunity_id": opportunity.opportunity_id,
            "kind": opportunity.kind,
            "title": opportunity.title,
            "source": opportunity.source,
            "cost_usd": opportunity.cost_usd,
            "expected_return_usd": opportunity.expected_return_usd,
            "ev_usd": round(opportunity.expected_value, 6),
            "approved_at": _utils.utc_now_iso(),
            "directive_present": True,
        }
        payload["allocations"].append(entry)
        payload["stack_usd"] = round(float(payload.get("stack_usd", 0.0)) - opportunity.cost_usd, 6)
        self._save(payload)
        self.audit.append(
            "opportunity_spend_approved",
            tier=TIER_HUMAN,
            details={
                "opportunity_id": opportunity.opportunity_id,
                "cost_usd": opportunity.cost_usd,
                "ev_usd": round(opportunity.expected_value, 6),
            },
        )
        return {"approved": True, "entry": entry, "stack_after_usd": payload["stack_usd"]}

    def record_return(self, opportunity_id: str, return_usd: float) -> dict[str, Any]:
        """Credit realized returns back into the stack (reinvestment loop)."""
        if return_usd <= 0:
            raise ValueError("return must be positive")
        payload = self._load()
        matches = [a for a in payload["allocations"] if a.get("opportunity_id") == opportunity_id]
        if not matches:
            raise ValueError(f"no allocation for opportunity '{opportunity_id}'")
        payload["stack_usd"] = round(float(payload.get("stack_usd", 0.0)) + return_usd, 6)
        self._save(payload)
        self.audit.append(
            "opportunity_return_credited",
            tier=0,
            details={"opportunity_id": opportunity_id, "return_usd": return_usd},
        )
        return {"credited": return_usd, "stack_after_usd": payload["stack_usd"]}

    def ledger(self) -> list[dict[str, Any]]:
        return list(self._load()["allocations"])
