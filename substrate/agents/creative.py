"""Creative-agent role — maintains the ARIN creative production substrate.

Ingested from ``ARIN_Kilo_Autonomous_Novel_Package.zip`` (human-provided).
The package's own manifest declares
``external_side_effect_policy: human_approval_required`` and
``autonomous_internal_work: true``; this module enforces exactly that
boundary regardless of what ``agents.yaml`` declares for autonomy tier.

Every scheduled (non-directive) run performs only bounded, reversible,
zero-cost internal work:

- verify the module layout under ``creative/<project>/`` exists
- verify canon/voice/quality-gate reference files are present and unchanged
  (hash-checked against the recorded provenance for binary assets)
- run a lightweight quality-gate self-check against any drafted manuscript
  files
- snapshot cost/telemetry state (no billed provider calls)
- write a dated rationale note under ``.research/creative-<project>/``

Actual prose generation, publishing, spending, or outbound promotion are
gated behind ``check_action_permission`` at Tier 2 (human directive
required), independent of the tier configured in ``agents.yaml``.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from .core import TIER_HUMAN, check_action_permission

PROJECT_SLUG = "ARIN"
MODULES = (
    "canon",
    "voice",
    "planning",
    "generation",
    "critique",
    "assets",
    "publishing",
    "economy",
    "promotion",
    "contracts",
    "telemetry",
    "memory",
    "state",
)
REQUIRED_FILES = (
    "canon/ARIN_CANON.md",
    "voice/VOICE_STYLE_ENGINE.md",
    "planning/NOVEL_PRODUCTION_PLAN.md",
    "economy/AUTONOMOUS_ECONOMY.md",
    "critique/QUALITY_GATES.md",
    "contracts/creative-generation-contract.md",
    "PROJECT_STATE.md",
    "DECISIONS.md",
    "BACKLOG.md",
    "CHANGELOG.md",
)
CANONICAL_ASSET = "assets/ARIN_final_poster.png"
CANONICAL_ASSET_SHA256 = (
    "3d110c5a85ef6884e1438096e2c1a700c4691a27c077f80a2759fb5e1b10c28b"
)


def _project_root(runtime: Any) -> Path:
    return runtime.root / "creative" / PROJECT_SLUG


def _state_path(runtime: Any) -> Path:
    return runtime.paths["state"] / "arin-production.json"


def _load_state(runtime: Any) -> dict[str, Any]:
    return _utils.load_json(
        _state_path(runtime),
        default={
            "phases": {
                "A": "not_started",
                "B": "not_started",
                "C": "not_started",
                "D": "not_started",
                "E": "not_started",
                "F": "not_started",
            },
            "ledger": {"cash_costs_usd": 0.0, "runs": 0},
            "telemetry": {"last_run": None, "runs": 0},
        },
    )


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _scaffold_check(project_root: Path) -> dict[str, Any]:
    missing_modules = [m for m in MODULES if not (project_root / m).is_dir()]
    missing_files = [f for f in REQUIRED_FILES if not (project_root / f).is_file()]
    asset_path = project_root / CANONICAL_ASSET
    asset_hash = _sha256(asset_path)
    asset_ok = asset_hash == CANONICAL_ASSET_SHA256
    return {
        "missing_modules": missing_modules,
        "missing_files": missing_files,
        "canonical_asset_present": asset_path.exists(),
        "canonical_asset_hash_matches": asset_ok,
        "canonical_asset_hash": asset_hash,
    }


def _quality_gate_self_check(project_root: Path) -> dict[str, Any]:
    """Bounded, deterministic self-check — not a substitute for full QA.

    Confirms the governance documents exist and that no manuscript file
    (if any have been drafted yet) contains an obvious secret-looking
    token. This intentionally does not invoke a model.
    """
    findings: list[str] = []
    manuscript_dir = project_root / "manuscript"
    secret_markers = ("BEGIN PRIVATE KEY", "api_key", "ACCESS_TOKEN", "SECRET=")
    checked = 0
    if manuscript_dir.exists():
        for path in manuscript_dir.rglob("*.md"):
            checked += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in secret_markers:
                if marker.lower() in text.lower():
                    findings.append(f"possible secret marker '{marker}' in {path}")
    return {
        "manuscript_files_checked": checked,
        "findings": findings,
        "passed": not findings,
    }


TIER2_ACTION_KEYWORDS = (
    "publish",
    "spend",
    "pay",
    "advertis",
    "promote-outbound",
    "sign",
    "payout",
    "tax-identity",
    "license-change",
    "ownership-change",
    "delete-canon",
    "expose-secret",
)


def _classify_directive(directive: str) -> tuple[str, int]:
    """Classify a human directive into an action tag + required tier."""
    lowered = directive.lower()
    for keyword in TIER2_ACTION_KEYWORDS:
        if keyword in lowered:
            return keyword, TIER_HUMAN
    if directive.strip():
        return "draft-or-plan", 1
    return "scheduled-maintenance", 0


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator
    runtime.resolve_repo(agent.repo_slug)
    project_root = _project_root(runtime)
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    scaffold = _scaffold_check(project_root)
    quality = _quality_gate_self_check(project_root)

    action_tag, action_tier = _classify_directive(directive)
    allowed, reason = check_action_permission(
        agent_tier_cap=agent.autonomy_tier,
        action_tier=action_tier,
        tests_green=quality["passed"],
        directive=directive,
    )

    state = _load_state(runtime)
    state["telemetry"]["last_run"] = _utils.utc_now_iso()
    state["telemetry"]["runs"] = int(state["telemetry"].get("runs", 0)) + 1
    state["ledger"]["runs"] = int(state["ledger"].get("runs", 0)) + 1
    # Scheduled/maintenance runs are zero-cost by contract; no billed calls.
    if action_tag == "scheduled-maintenance":
        state["ledger"]["cash_costs_usd"] = float(state["ledger"].get("cash_costs_usd", 0.0))
    _utils.write_json(_state_path(runtime), state)

    notes_dir = runtime.paths["research"] / "creative-arin"
    notes_dir.mkdir(parents=True, exist_ok=True)
    rationale_path = notes_dir / f"{date_str}-{agent.id}.md"
    lines = [
        f"# ARIN creative-agent run — {date_str}",
        "",
        f"- Agent: `{agent.id}` (autonomy_tier={agent.autonomy_tier})",
        f"- Directive present: {bool(directive)}",
        f"- Directive classification: `{action_tag}` (requires tier {action_tier})",
        f"- Permission result: **{allowed}** ({reason})",
        "",
        "## Scaffold check",
        f"- Missing modules: {scaffold['missing_modules'] or 'none'}",
        f"- Missing files: {scaffold['missing_files'] or 'none'}",
        f"- Canonical poster present: {scaffold['canonical_asset_present']}",
        f"- Canonical poster hash matches provenance: {scaffold['canonical_asset_hash_matches']}",
        "",
        "## Quality-gate self-check",
        f"- Manuscript files checked: {quality['manuscript_files_checked']}",
        f"- Findings: {quality['findings'] or 'none'}",
        f"- Passed: {quality['passed']}",
        "",
    ]

    if action_tier == TIER_HUMAN and not allowed:
        lines.append(
            "> Directive requested a Tier 2 action "
            f"(`{action_tag}`) without an accompanying human directive "
            "context sufficient to authorize it, or none was supplied. "
            "No spending, publishing, contract, or outbound-promotion "
            "action was taken."
        )
    elif directive:
        lines.append(
            f"> Directive received and permitted at tier {action_tier}. "
            "This scheduled run only recorded the directive and validated "
            "the substrate; it does not itself invoke a paid generation "
            "provider. Use the generation pipeline in `generation/` "
            "on-demand, with an explicit cost ceiling recorded in "
            "`contracts/creative-generation-contract.md`, to draft prose."
        )
    else:
        lines.append(
            "> Routine scheduled maintenance only "
            "(bounded, zero-cost, reversible internal work)."
        )

    rationale_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    outputs.append(str(rationale_path.relative_to(runtime.root)))

    actions.append(
        {
            "action": action_tag,
            "tier": action_tier,
            "allowed": allowed,
            "reason": reason,
        }
    )

    status = "success"
    note_parts = []
    if scaffold["missing_modules"] or scaffold["missing_files"]:
        status = "attention"
        note_parts.append("scaffold incomplete")
    if not scaffold["canonical_asset_hash_matches"]:
        status = "attention"
        note_parts.append("canonical asset hash mismatch or missing")
    if not quality["passed"]:
        status = "attention"
        note_parts.append("quality self-check findings present")
    if action_tier == TIER_HUMAN and not allowed:
        note_parts.append("tier2 action blocked pending human directive")

    return {
        "status": status,
        "note": "; ".join(note_parts) or "maintenance run clean",
        "outputs": outputs,
        "actions": actions,
    }
