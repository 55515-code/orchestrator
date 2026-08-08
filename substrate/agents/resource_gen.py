"""Resource-generator agent — turns backlog topics into vetted resources.

Consumes ``state/resource-backlog.json`` (filled by the expansion trigger).
For each queued topic it runs the resource pipeline: demand check, generation,
quality gate, then draft. Publishing into the catalog is Tier 2 and only
happens when an explicit human directive accompanies the run.

Rationale notes land in ``.research/resource-generation/``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..pipelines.resource_pipeline import ResourcePipeline


def _backlog_path(runtime: Any) -> Path:
    return runtime.paths["state"] / "resource-backlog.json"


def _load_backlog(runtime: Any) -> dict[str, Any]:
    payload = _utils.load_json(_backlog_path(runtime), default={"tasks": []})
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        payload["tasks"] = []
    return payload


def _build_model(agent: Any):
    if agent.provider in {"mock", "codex"}:
        return None
    try:
        from ..providers import DEFAULT_PROVIDER_MODELS, build_model

        return build_model(agent.provider, DEFAULT_PROVIDER_MODELS.get(agent.provider, ""))
    except Exception:  # noqa: BLE001 - degrade to template generation
        return None


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator
    runtime.resolve_repo(agent.repo_slug)
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    payload = _load_backlog(runtime)
    queued = [task for task in payload["tasks"] if task.get("status") == "queued"]
    if not queued:
        return {
            "status": "success",
            "note": "no queued backlog tasks",
            "outputs": outputs,
            "actions": actions,
        }

    pipeline = ResourcePipeline(
        runtime.root,
        provider=agent.provider,
        model=_build_model(agent),
    )
    notes_dir = runtime.paths["research"] / "resource-generation"
    notes_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    for task in queued:
        topic = str(task.get("target_id") or "")
        if not topic:
            continue
        report = pipeline.run(
            topic,
            resource_type="checklist",
            category="compliance",
            price_usdc=0.0,
            directive=directive,
        )
        task["status"] = report.get("status") or "processed"
        task["processed_at"] = _utils.utc_now_iso()
        processed += 1

        rationale_path = notes_dir / f"{date_str}-{topic}.md"
        rationale_path.write_text(
            "\n".join(
                [
                    f"# Resource generation — {topic} ({date_str})",
                    "",
                    f"- Pipeline status: **{report.get('status')}**",
                    f"- Demand score: {report.get('demand_score', 'n/a')}",
                    f"- Quality passed: {bool((report.get('quality') or {}).get('passed'))}",
                    f"- Draft: `{report.get('draft', 'n/a')}`",
                    f"- Directive present: {bool(directive)}",
                    f"- Agent: `{agent.id}`",
                    "",
                    "> Publishing is Tier 2 and requires a human directive.",
                ]
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )
        outputs.append(str(rationale_path.relative_to(runtime.root)))
        tier = 2 if report.get("status") == "published" else 1
        actions.append(
            {
                "action": f"generate:{topic}",
                "tier": tier,
                "status": report.get("status"),
            }
        )

    _utils.write_json(_backlog_path(runtime), payload)

    return {
        "status": "success",
        "note": f"processed {processed} backlog task(s)",
        "outputs": outputs,
        "actions": actions,
    }
