"""Revenue ledger and trend tracking.

Records settled payments and computes month-over-month trends. The trend is
the guard for competitive price undercutting (PF-011): price cuts are refused
while revenue is flat or declining. The ledger lives in
``state/crypto/revenue.json`` (gitignored); every settled payment is also
appended to the hash-chained audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..security.audit_trail import AuditTrail

LEDGER_RELATIVE = Path("state") / "crypto" / "revenue.json"


class RevenueTracker:
    def __init__(self, root: Path, *, audit: AuditTrail | None = None) -> None:
        self.root = Path(root)
        self.ledger_path = self.root / LEDGER_RELATIVE
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")

    def _load(self) -> dict[str, Any]:
        payload = _utils.load_json(self.ledger_path, default={"payments": []})
        payments = payload.get("payments")
        if not isinstance(payments, list):
            payload["payments"] = []
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        _utils.write_json(self.ledger_path, payload)

    def record_payment(
        self,
        resource_id: str,
        amount_usd: float,
        *,
        token: str = "USDC",
        payer: str = "",
        tx_hash: str = "",
        channel: str = "web",
    ) -> dict[str, Any]:
        """Record a settled payment. The tx_hash is a replay guard."""
        payload = self._load()
        for existing in payload["payments"]:
            if existing.get("tx_hash") and existing["tx_hash"] == tx_hash:
                raise ValueError(f"payment for tx {tx_hash} already recorded")
        entry = {
            "resource_id": resource_id,
            "amount_usd": round(float(amount_usd), 2),
            "token": token,
            "payer": payer,
            "tx_hash": tx_hash,
            "channel": channel,
            "paid_at": _utils.utc_now_iso(),
        }
        payload["payments"].append(entry)
        self._save(payload)
        self.audit.append(
            "revenue_recorded",
            tier=0,
            details={
                "resource_id": resource_id,
                "amount_usd": entry["amount_usd"],
                "token": token,
                "tx_hash": tx_hash[:16] if tx_hash else "",
            },
        )
        return entry

    def monthly_totals(self, months: int = 6) -> list[dict[str, Any]]:
        """Return monthly revenue buckets, oldest first."""
        buckets: dict[str, float] = {}
        now = datetime.now(UTC)
        for payment in self._load()["payments"]:
            try:
                paid_at = datetime.fromisoformat(str(payment.get("paid_at") or ""))
                if paid_at.tzinfo is None:
                    paid_at = paid_at.replace(tzinfo=UTC)
            except ValueError:
                continue
            key = paid_at.strftime("%Y-%m")
            months_ago = (now.year - paid_at.year) * 12 + (now.month - paid_at.month)
            if months_ago >= months:
                continue
            buckets[key] = buckets.get(key, 0.0) + float(payment.get("amount_usd", 0))
        keys = sorted(buckets.keys())
        return [{"month": key, "total_usd": round(buckets[key], 2)} for key in keys]

    def trend(self) -> dict[str, Any]:
        """Summarize revenue movement: is the number going up?"""
        monthly = self.monthly_totals()
        totals = [entry["total_usd"] for entry in monthly]
        if len(totals) < 2:
            return {
                "upward": False,
                "note": "need at least two months of data to judge a trend",
                "monthly": monthly,
            }
        prev, current = totals[-2], totals[-1]
        growth = (current - prev) / prev if prev else 0.0
        return {
            "upward": current > prev,
            "growth_pct": round(growth * 100, 1),
            "previous_month": prev,
            "current_month": current,
            "monthly": monthly,
        }
