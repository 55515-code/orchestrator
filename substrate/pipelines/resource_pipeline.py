"""Resource generation pipeline: demand -> generate -> gate -> publish.

Stages and their tiers:
- Demand check (Tier 0): reads market-research sidecars; below threshold the
  topic is skipped rather than generated.
- Generation (Tier 1): provider-enriched when configured, deterministic
  template otherwise. Output is a draft, never published directly.
- Quality gate (Tier 1): structural + safety validation.
- Publish (Tier 2): requires an explicit human directive.

Drafts land in ``resources/drafts/``; published entries enter
``resources/catalog.json`` via :class:`ResourceInventory`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import _utils
from ..crypto.inventory import ResourceInventory
from ..security.audit_trail import AuditTrail
from .quality_gate import QualityGate

DEMAND_THRESHOLD = 0.7


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "resource"


class ResourcePipeline:
    def __init__(
        self,
        root: Path,
        *,
        provider: str = "mock",
        model: Any = None,
        inventory: ResourceInventory | None = None,
        audit: AuditTrail | None = None,
        gate: QualityGate | None = None,
        demand_threshold: float = DEMAND_THRESHOLD,
    ) -> None:
        self.root = Path(root)
        self.provider = provider
        self.model = model
        self.inventory = inventory or ResourceInventory(self.root, audit=audit)
        self.audit = audit or AuditTrail(self.root / "state" / "crypto" / "audit.jsonl")
        self.gate = gate or QualityGate()
        self.demand_threshold = demand_threshold
        self.drafts_dir = self.root / "resources" / "drafts"

    def demand_score(self, topic: str) -> float:
        """Best demand score for *topic* across market-research sidecars."""
        findings_dir = self.root / ".research" / "market-demand"
        if not findings_dir.exists():
            return 0.0
        best = 0.0
        slug = _slugify(topic)
        for sidecar in sorted(findings_dir.glob("*.json")):
            payload = _utils.load_json(sidecar, default={})
            target_id = str(payload.get("target_id") or "")
            if slug in target_id or target_id in slug or topic.lower() in target_id.lower():
                best = max(best, float(payload.get("demand_score") or 0.0))
        return best

    def generate_content(self, topic: str, resource_type: str = "checklist") -> tuple[str, str]:
        """Return (title, content). Provider-enriched when a model is set."""
        title = f"{topic.title()} {resource_type.title()}"
        if self.model is not None:
            try:
                result = self.model.invoke(
                    f"Write a practical {resource_type} about {topic} for small "
                    "businesses. Markdown, with ## sections and actionable items. "
                    "No invented citations."
                )
                text = str(getattr(result, "content", "") or "").strip()
                if len(text.split()) > 150:
                    return title, text
            except Exception:  # noqa: BLE001 - degrade to template generation
                pass
        return title, _template_content(topic, resource_type)

    def run(
        self,
        topic: str,
        resource_type: str = "checklist",
        *,
        category: str = "compliance",
        price_usdc: float = 0.0,
        directive: str = "",
    ) -> dict[str, Any]:
        demand = self.demand_score(topic)
        if demand and demand < self.demand_threshold:
            return {
                "status": "skipped",
                "reason": f"demand score {demand} below threshold {self.demand_threshold}",
                "topic": topic,
            }

        title, content = self.generate_content(topic, resource_type)
        quality = self.gate.validate(content, resource_type=resource_type, title=title)
        if not quality["passed"]:
            return {
                "status": "rejected",
                "topic": topic,
                "demand_score": demand,
                "issues": quality["issues"],
            }

        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(topic)
        extension = "yaml" if resource_type == "config" else "md"
        draft_path = self.drafts_dir / f"{slug}.{extension}"
        draft_path.write_text(content, encoding="utf-8")

        report: dict[str, Any] = {
            "status": "pending_approval",
            "topic": topic,
            "resource_type": resource_type,
            "demand_score": demand,
            "quality": quality,
            "draft": str(draft_path.relative_to(self.root)),
        }

        if directive:
            entry = {
                "id": slug,
                "title": title,
                "category": category,
                "description": f"Generated {resource_type}: {topic}.",
                "topic": topic,
                "price_usdc": float(price_usdc),
                "free": float(price_usdc) == 0,
                "version": "1.0",
                "file_path": str(draft_path.relative_to(self.root)),
            }
            try:
                published = self.inventory.publish(entry, directive=directive)
                report["status"] = "published"
                report["published"] = published
            except (PermissionError, ValueError, FileNotFoundError) as exc:
                report["status"] = "publish_failed"
                report["error"] = str(exc)
        else:
            self.audit.append(
                "resource_draft_pending",
                tier=1,
                details={"topic": topic, "draft": report["draft"]},
            )
        return report


def _template_content(topic: str, resource_type: str) -> str:
    """Deterministic structured content used when no provider is available."""
    title_topic = topic.title()
    if resource_type == "config":
        return "\n".join(
            [
                f"# {title_topic} configuration template",
                "",
                "version: 1",
                f"name: {topic.lower().replace(' ', '-')}",
                "settings:",
                "  enabled: true",
                "  review_cadence: quarterly",
                "  owner: security-lead",
                "  escalation_contacts:",
                "    - security-lead",
                "    - compliance-officer",
                "controls:",
                "  - id: c1",
                f"    description: Baseline control for {topic}",
                "    evidence_required: true",
                "    review_frequency: quarterly",
                "    owner: security-lead",
                "  - id: c2",
                f"    description: Monitoring control for {topic}",
                "    evidence_required: true",
                "    review_frequency: monthly",
                "    owner: operations",
                "  - id: c3",
                f"    description: Access control for {topic}",
                "    evidence_required: true",
                "    review_frequency: quarterly",
                "    owner: identity-team",
                "monitoring:",
                "  alerts_enabled: true",
                "  log_retention_days: 365",
                "  dashboard_url: https://ops.example/dashboards/{topic}",
                "compliance:",
                "  framework: SOC2",
                "  control_mapping:",
                "    - CC6.1",
                "    - CC7.2",
                "",
            ]
        )

    sections = [
        f"# {title_topic} {resource_type.title()}",
        "",
        f"A practical {resource_type} for small teams implementing {topic}.",
        "Work through each phase in order; every item is verifiable.",
        "This document is designed to be actionable: each checkbox represents",
        "a concrete step that produces evidence an auditor or reviewer can inspect.",
        "",
        "## Phase 1 — Scope and Ownership",
        "",
        f"- [ ] Name a single owner accountable for {topic}",
        "- [ ] Define which systems, teams, and data are in scope",
        "- [ ] Record the regulatory or business driver for this work",
        "- [ ] Set a review date for this document (quarterly recommended)",
        "- [ ] Identify stakeholders who must approve the scope",
        "- [ ] Document any explicit out-of-scope items with rationale",
        "",
        "## Phase 2 — Baseline Implementation",
        "",
        f"- [ ] Inventory current controls covering {topic}",
        "- [ ] Identify gaps between current state and the baseline",
        "- [ ] Assign each gap an owner and a target date",
        "- [ ] Document compensating controls for anything deferred",
        "- [ ] Map each control to the relevant framework requirement",
        "- [ ] Validate that compensating controls are themselves reviewed",
        "",
        "## Phase 3 — Evidence and Verification",
        "",
        "- [ ] Collect evidence for every implemented control",
        "- [ ] Verify controls operate as designed (sample at least two)",
        "- [ ] Record exceptions with remediation plans",
        "- [ ] Store evidence where auditors can retrieve it quickly",
        "- [ ] Confirm evidence includes timestamps and attribution",
        "- [ ] Cross-check evidence against the control inventory",
        "",
        "## Phase 4 — Operate and Improve",
        "",
        "- [ ] Add recurring review to the operations calendar",
        "- [ ] Track metrics (coverage, exceptions, time to remediate)",
        "- [ ] Re-run this checklist after any significant change",
        "- [ ] Capture lessons learned and fold them back into Phase 2",
        "- [ ] Publish a one-page summary for leadership review",
        "- [ ] Schedule the next full review cycle",
        "",
        "## Notes",
        "",
        f"Adapt this {resource_type} to your environment. Items marked in scope",
        "must have evidence; out-of-scope items need a written rationale.",
        "Every control should have a named owner and a review cadence.",
        "Evidence should be stored in a location accessible to auditors",
        "and retained for at least the observation period plus one year.",
        "",
        "---",
        "*Educational material; not legal advice.*",
        "",
    ]
    return "\n".join(sections)
