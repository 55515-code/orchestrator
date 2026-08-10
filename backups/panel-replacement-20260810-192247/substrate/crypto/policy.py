"""Payment-flow governance: documentation, vetting, and change gates.

This module enforces the standing rule that payment flows and their technology
must always be documented, kept current, and vetted before use. Concretely:

- Rules live in ``crypto-rules.yaml`` (repo root) and are machine-readable.
- Any change to a payment flow must pass :meth:`PaymentFlowGovernance.gate_change`,
  which requires: an explicit Tier 2 directive, updated documentation, green
  tests, and a completed vetting checklist. Approved changes are recorded in
  ``state/crypto/reviews.json`` and the audit trail.
- :meth:`PaymentFlowGovernance.docs_status` checks that the runbook exists and
  was verified within the rule-defined freshness window.
- :meth:`PaymentFlowGovernance.verify_all` aggregates all enforcement checks
  (docs freshness, catalog integrity, backup verification, audit chain) into a
  single report suitable for monitoring/alerting.

The runbook (``docs/CRYPTO_PAYMENT_RUNBOOK.md``) carries YAML frontmatter with
``last_verified`` and the component inventory; both are machine-checked.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail

RULES_FILE = "crypto-rules.yaml"
REVIEW_STATE_RELATIVE = Path("state") / "crypto" / "reviews.json"


def load_payment_rules(root: Path, *, rules_path: Path | None = None) -> dict[str, Any]:
    path = rules_path or (Path(root) / RULES_FILE)
    if not path.exists():
        raise FileNotFoundError(f"payment-flow rules file missing: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError("crypto-rules.yaml must be a mapping")
    if not payload.get("rules"):
        raise ValueError("crypto-rules.yaml must define a non-empty 'rules' list")
    return payload


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    try:
        payload = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}
    return payload if isinstance(payload, dict) else {}


class PaymentFlowGovernance:
    """Enforce documentation, vetting, and change-control rules for payments."""

    def __init__(
        self,
        root: Path,
        *,
        rules_path: Path | None = None,
        audit: AuditTrail | None = None,
    ) -> None:
        self.root = Path(root)
        self.rules = load_payment_rules(self.root, rules_path=rules_path)
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")

    @property
    def runbook_path(self) -> Path:
        relative = str(self.rules.get("documentation", {}).get("runbook", ""))
        return self.root / relative

    @property
    def max_doc_age_days(self) -> int:
        return int(self.rules.get("documentation", {}).get("max_age_days", 90))

    @property
    def required_checklist(self) -> list[str]:
        checklist = self.rules.get("review", {}).get("required_checklist") or []
        return [str(item) for item in checklist]

    def gate_change(
        self,
        change_id: str,
        *,
        summary: str,
        directive: str,
        docs_updated: bool,
        tests_green: bool,
        checklist: dict[str, bool] | None = None,
        actor: str = "operator",
    ) -> dict[str, Any]:
        """Gate a payment-flow change. Raises on any unmet requirement."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            self.audit.append(
                "payment_flow_change_blocked",
                tier=TIER_HUMAN,
                details={"change_id": change_id, "reason": reason},
            )
            raise PermissionError(
                f"payment-flow change '{change_id}' blocked: Tier 2 directive required ({reason})"
            )

        unmet: list[str] = []
        if not docs_updated:
            unmet.append("docs_updated")
        if not tests_green:
            unmet.append("tests_green")
        provided = checklist or {}
        for item in self.required_checklist:
            if not provided.get(item):
                unmet.append(f"checklist:{item}")
        if unmet:
            self.audit.append(
                "payment_flow_change_blocked",
                tier=TIER_HUMAN,
                details={"change_id": change_id, "unmet": unmet},
            )
            raise PermissionError(
                f"payment-flow change '{change_id}' blocked; unmet requirements: {', '.join(unmet)}"
            )

        review = {
            "change_id": change_id,
            "summary": summary,
            "actor": actor,
            "reviewed_at": _utils.utc_now_iso(),
            "checklist": {item: True for item in self.required_checklist},
            "directive_present": True,
        }
        state_path = self.root / REVIEW_STATE_RELATIVE
        payload = _utils.load_json(state_path, default={"reviews": []})
        reviews = payload.get("reviews")
        if not isinstance(reviews, list):
            reviews = []
        reviews.append(review)
        payload["reviews"] = reviews[-200:]
        _utils.write_json(state_path, payload)
        self.audit.append(
            "payment_flow_change_approved",
            tier=TIER_HUMAN,
            details={"change_id": change_id, "actor": actor},
        )
        return review

    def docs_status(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Check that the runbook exists and is within the freshness window."""
        current = now or datetime.now(UTC)
        path = self.runbook_path
        if not path.exists():
            return {"exists": False, "current": False, "reason": "runbook missing"}
        frontmatter = _parse_frontmatter(path.read_text(encoding="utf-8"))
        last_verified_raw = str(frontmatter.get("last_verified") or "")
        try:
            last_verified = datetime.fromisoformat(last_verified_raw)
            if last_verified.tzinfo is None:
                last_verified = last_verified.replace(tzinfo=UTC)
        except ValueError:
            return {
                "exists": True,
                "current": False,
                "reason": "runbook frontmatter missing/invalid 'last_verified'",
            }
        age_days = (current - last_verified).days
        return {
            "exists": True,
            "last_verified": last_verified_raw,
            "age_days": age_days,
            "max_age_days": self.max_doc_age_days,
            "current": age_days <= self.max_doc_age_days,
            "components": frontmatter.get("components") or [],
        }

    def verify_all(self, *, inventory: Any = None, wallet_manager: Any = None) -> dict[str, Any]:
        """Aggregate every enforcement check into one vetting report."""
        report: dict[str, Any] = {
            "generated_at": _utils.utc_now_iso(),
            "checks": {},
            "ok": True,
        }

        docs = self.docs_status()
        report["checks"]["documentation"] = docs
        if not docs.get("current"):
            report["ok"] = False

        if inventory is not None:
            checksums = inventory.validate_checksums()
            report["checks"]["catalog_integrity"] = checksums
            if not checksums.get("ok"):
                report["ok"] = False

        backup_status = _utils.load_json(
            self.root / "state" / "crypto" / "backup-status.json", default={}
        )
        backup_ok = bool(backup_status.get("verified"))
        report["checks"]["backup_verified"] = {
            "verified": backup_ok,
            "at": backup_status.get("backup_at"),
        }
        if wallet_manager is not None and wallet_manager.list_wallets() and not backup_ok:
            report["ok"] = False

        audit_report = self.audit.verify()
        report["checks"]["audit_chain"] = audit_report
        if not audit_report.get("ok"):
            report["ok"] = False

        self.audit.append(
            "payment_flow_vetting_report",
            tier=0,
            details={"ok": report["ok"], "checks": sorted(report["checks"].keys())},
        )
        return report
