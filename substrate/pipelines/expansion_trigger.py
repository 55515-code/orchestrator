"""Expansion trigger — converts research findings into queued work.

Reads market-research sidecars (``.research/market-demand/*.json``) and
selects targets whose demand is high and competition manageable. Selected
targets become generation backlog entries in ``state/resource-backlog.json``.

Queueing new sellable content is a Tier 2 action (requires a human directive)
because it commits the always-selling pipeline to new inventory; individual
publication remains separately gated in the resource pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import _utils
from ..agents.core import TIER_HUMAN, check_action_permission
from ..security.audit_trail import AuditTrail

BACKLOG_RELATIVE = Path("state") / "resource-backlog.json"


class ExpansionTrigger:
    def __init__(
        self,
        root: Path,
        *,
        min_demand: float = 0.8,
        max_competition: float = 0.5,
        audit: AuditTrail | None = None,
    ) -> None:
        self.root = Path(root)
        self.min_demand = min_demand
        self.max_competition = max_competition
        self.backlog_path = self.root / BACKLOG_RELATIVE
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")

    def candidates(self) -> list[dict[str, Any]]:
        """Find research sidecars that qualify for expansion."""
        findings_dir = self.root / ".research" / "market-demand"
        if not findings_dir.exists():
            return []
        qualified: list[dict[str, Any]] = []
        seen: set[str] = set()
        for sidecar in sorted(findings_dir.glob("*.json"), reverse=True):
            payload = _utils.load_json(sidecar, default={})
            target_id = str(payload.get("target_id") or "")
            if not target_id or target_id in seen:
                continue
            demand = float(payload.get("demand_score") or 0.0)
            competition = float(payload.get("competition") or 1.0)
            if demand >= self.min_demand and competition <= self.max_competition:
                seen.add(target_id)
                qualified.append(
                    {
                        "target_id": target_id,
                        "kind": payload.get("kind"),
                        "demand_score": demand,
                        "competition": competition,
                        "source": str(sidecar.relative_to(self.root)),
                    }
                )
        return qualified

    def _load_backlog(self) -> dict[str, Any]:
        payload = _utils.load_json(self.backlog_path, default={"tasks": []})
        tasks = payload.get("tasks")
        if not isinstance(tasks, list):
            payload["tasks"] = []
        return payload

    def queue_tasks(self, *, directive: str = "") -> dict[str, Any]:
        """Queue generation tasks for qualified candidates. Tier 2."""
        allowed, reason = check_action_permission(
            agent_tier_cap=TIER_HUMAN, action_tier=TIER_HUMAN, directive=directive
        )
        if not allowed:
            raise PermissionError(f"expansion task queueing is Tier 2 ({reason})")

        qualified = self.candidates()
        payload = self._load_backlog()
        existing_ids = {task.get("target_id") for task in payload["tasks"]}
        added: list[str] = []
        for candidate in qualified:
            if candidate["target_id"] in existing_ids:
                continue
            payload["tasks"].append(
                {
                    "target_id": candidate["target_id"],
                    "kind": candidate["kind"],
                    "demand_score": candidate["demand_score"],
                    "queued_at": _utils.utc_now_iso(),
                    "status": "queued",
                }
            )
            added.append(candidate["target_id"])
        _utils.write_json(self.backlog_path, payload)
        if added:
            self.audit.append(
                "expansion_tasks_queued",
                tier=TIER_HUMAN,
                details={"targets": added},
            )
        return {"queued": added, "total_candidates": len(qualified)}

    def backlog(self) -> list[dict[str, Any]]:
        return list(self._load_backlog()["tasks"])
