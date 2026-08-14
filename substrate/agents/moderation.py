"""Content-moderator agent — triages the 1pointo site community queue.

Tier 1 autonomy: hold / needs-changes marks are applied automatically.
Tier 2 actions (approve / reject) are recommendations only and require a
human directive before they take effect.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..site_content import _ensure_dirs, _parse_frontmatter, _queue_dirs, queue_list

SPAM_TERMS = (
    "casino",
    "free money",
    "act now",
    "limited time offer",
    "winner",
    "congratulations you have been selected",
    "viagra",
    "crypto guaranteed returns",
)
CLASSIFICATIONS = (
    "approve-recommend",
    "hold",
    "needs-changes",
    "reject-recommend",
)


def _spam_score(body: str) -> int:
    lowered = body.lower()
    score = 0
    score += sum(1 for term in SPAM_TERMS if term in lowered)
    link_count = len(re.findall(r"https?://", lowered))
    if link_count > 8:
        score += 3
    elif link_count > 3:
        score += 1
    return score


def _moderation_state_path(runtime: Any) -> Path:
    return runtime.paths["state"] / "moderation-decisions.json"


def _load_moderation_state(runtime: Any) -> dict[str, Any]:
    path = _moderation_state_path(runtime)
    if not path.exists():
        return {"decisions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {"decisions": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("decisions"), dict):
        return {"decisions": {}}
    return payload


def _apply_queue_mark(
    runtime: Any, site_root: Path, filename: str, classification: str
) -> bool:
    """Persist a hold / needs-changes mark into queue metadata (Tier 1)."""
    queue_state_path = runtime.paths["state"] / "content-queue.json"
    try:
        payload = (
            json.loads(queue_state_path.read_text(encoding="utf-8") or "{}")
            if queue_state_path.exists()
            else {}
        )
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}
    marks = payload.get("moderation_marks")
    if not isinstance(marks, dict):
        marks = {}
    marks[filename] = {
        "classification": classification,
        "marked_at": _utils.utc_now_iso(),
    }
    payload["moderation_marks"] = marks
    queue_state_path.parent.mkdir(parents=True, exist_ok=True)
    queue_state_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _ = site_root
    return True


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator, directive
    repo = runtime.resolve_repo(agent.repo_slug)
    site_root = (runtime.root / repo.path).resolve()
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    _ensure_dirs(site_root)
    dirs = _queue_dirs(site_root)
    listing = queue_list(site_root=site_root, runtime=runtime)
    items = listing.get("items", [])
    actions.append(
        {"action": "fetch-queue", "tier": 0, "status": "success", "count": len(items)}
    )
    if not items:
        return {
            "status": "success",
            "note": "moderation queue empty",
            "outputs": outputs,
            "actions": actions,
        }

    decision_dir = runtime.paths["research"] / "site-moderation"
    decision_dir.mkdir(parents=True, exist_ok=True)
    moderation_state = _load_moderation_state(runtime)

    for item in items:
        filename = str(item.get("file") or "")
        submission_id = Path(filename).stem or filename
        inbox_path = dirs["inbox"] / filename
        body = ""
        frontmatter: dict[str, Any] = {}
        if inbox_path.exists():
            frontmatter, body = _parse_frontmatter(inbox_path)

        validation_errors = list(item.get("errors") or [])
        spam = _spam_score(body)
        title = str(frontmatter.get("title") or item.get("title") or "")

        if spam >= 3:
            classification = "reject-recommend"
        elif validation_errors:
            classification = "needs-changes"
        elif spam >= 1:
            classification = "hold"
        else:
            classification = "approve-recommend"

        rationale_path = decision_dir / f"{date_str}-{submission_id}.md"
        rationale_path.write_text(
            "\n".join(
                [
                    f"# Moderation decision — {submission_id} ({date_str})",
                    "",
                    f"- Submission: `{filename}`",
                    f"- Title: `{title}`",
                    f"- Classification: **{classification}**",
                    f"- Spam score: {spam}",
                    f"- Validation errors: {len(validation_errors)}",
                    f"- Agent: `{agent.id}`",
                    f"- Decided: {_utils.utc_now_iso()}",
                    "",
                    "## Validation errors",
                    "",
                ]
                + [f"- {err}" for err in validation_errors]
                + (["- (none)"] if not validation_errors else [])
                + [
                    "",
                    "## Rationale",
                    "",
                    _rationale_text(classification, spam, len(validation_errors)),
                    "",
                    "> Approve / reject are Tier 2 and require a human directive.",
                ]
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )

        tier = 1 if classification in {"hold", "needs-changes"} else 2
        applied = False
        if tier == 1:
            applied = _apply_queue_mark(runtime, site_root, filename, classification)
        moderation_state["decisions"][f"{date_str}-{submission_id}"] = {
            "file": filename,
            "classification": classification,
            "spam_score": spam,
            "validation_errors": len(validation_errors),
            "applied": applied,
            "tier": tier,
            "rationale": str(rationale_path.relative_to(runtime.root)),
            "decided_at": _utils.utc_now_iso(),
        }
        actions.append(
            {
                "action": f"classify:{submission_id}",
                "tier": tier,
                "status": "applied" if applied else "recommendation",
                "classification": classification,
            }
        )
        outputs.append(str(rationale_path.relative_to(runtime.root)))

    _utils.write_json(_moderation_state_path(runtime), moderation_state)

    return {
        "status": "success",
        "note": f"triaged {len(items)} submission(s)",
        "outputs": outputs,
        "actions": actions,
    }


def _rationale_text(classification: str, spam: int, error_count: int) -> str:
    if classification == "reject-recommend":
        return (
            f"High spam score ({spam}) indicates likely unwanted content. "
            "Recommend rejection pending human confirmation."
        )
    if classification == "needs-changes":
        return (
            f"Frontmatter/content validation failed with {error_count} error(s). "
            "Marked needs-changes so the author can revise."
        )
    if classification == "hold":
        return (
            f"Moderate spam signals (score {spam}) without hard validation failure. "
            "Held for human review before publication."
        )
    return (
        "No validation errors and low spam signals. Recommended for approval, "
        "which still requires a human directive (Tier 2)."
    )
