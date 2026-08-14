"""Research agent — refreshes upstream evidence and writes research notes.

Tier 0 autonomy: writes notes only, never mutates code. Satisfies the
``require_source_facts_before_mutation`` policy for the dev/update agents.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..research import (
    refresh_upstreams,
    run_openclaw_research_assist,
)


def _research_dir(runtime: Any, repo_slug: str) -> Path:
    directory = runtime.paths["research"] / repo_slug
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_note(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator, directive
    repo = runtime.resolve_repo(agent.repo_slug)
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    refreshed: list[dict[str, Any]] = []
    refresh_error: str | None = None
    try:
        refreshed = refresh_upstreams(runtime)
    except Exception as exc:  # noqa: BLE001
        refresh_error = f"{type(exc).__name__}: {exc}"
    actions.append(
        {
            "action": "refresh-upstreams",
            "tier": 0,
            "status": "failed" if refresh_error else "success",
            "count": len(refreshed),
            "error": refresh_error,
        }
    )

    snapshot = runtime.inspect_repository(repo)
    sources = runtime.db.list_source_projects()

    openclaw_result: dict[str, Any] | None = None
    try:
        openclaw_result = run_openclaw_research_assist(
            runtime,
            run_id=f"agent-{agent.id}-{date_str}",
            stage="local",
            pass_name=agent.pass_name,
            objective=(
                f"Refresh upstream research evidence for repository "
                f"'{agent.repo_slug}' (dependency advisories, security CVEs, "
                "upstream project changes, Hak5 device ecosystem and comparable "
                "open-source security, penetration-testing, wireless-auditing, "
                "SDR, RFID, and HID tooling changes)."
            ),
            context=json.dumps(
                {"repo_slug": agent.repo_slug, "sources": len(sources)},
                ensure_ascii=False,
            ),
            manual_trigger=True,
            data_class="synthetic",
        )
    except Exception as exc:  # noqa: BLE001
        openclaw_result = {"status": "degraded_unavailable", "reason": str(exc)}
    actions.append(
        {
            "action": "openclaw-research-assist",
            "tier": 0,
            "status": str(openclaw_result.get("status")),
            "reason": openclaw_result.get("reason"),
        }
    )

    note_path = _research_dir(runtime, agent.repo_slug) / f"{date_str}-upstream-research.md"
    lines = [
        f"# Research note — {agent.repo_slug} ({date_str})",
        "",
        f"- Agent: `{agent.id}` (role `{agent.role}`, pass `{agent.pass_name}`)",
        f"- Generated: {_utils.utc_now_iso()}",
        f"- Repository path: `{repo.path}`",
        f"- Git branch: `{snapshot.get('branch')}`",
        f"- Dirty: `{snapshot.get('dirty')}`",
        "",
        "## Source facts",
        "",
    ]
    if sources:
        for source in sources[:50]:
            metadata = source.get("metadata") or {}
            error = metadata.get("error")
            lines.append(
                f"- `{source.get('slug')}` — {source.get('name')} "
                f"(license: {source.get('license')}, stars: {source.get('stars')}, "
                f"pushed_at: {source.get('pushed_at')}, archived: {source.get('archived')})"
                + (f" — error: {error}" if error else "")
            )
    else:
        lines.append("- No upstream source projects registered in upstreams.yaml.")
    if refresh_error:
        lines.extend(["", f"Upstream refresh degraded: {refresh_error}"])

    lines.extend(
        [
            "",
            "## OpenClaw research assist",
            "",
            f"- Status: `{openclaw_result.get('status')}`",
            f"- Reason: `{openclaw_result.get('reason')}`",
        ]
    )
    insights = openclaw_result.get("imported_insights") or []
    if insights:
        lines.append("- Vetted insights:")
        lines.extend(f"  - {insight}" for insight in insights[:20])

    _write_note(note_path, lines)
    outputs.append(str(note_path.relative_to(runtime.root)))

    return {
        "status": "success",
        "note": (
            f"research refreshed ({len(refreshed)} sources"
            + (f"; refresh degraded: {refresh_error}" if refresh_error else "")
            + ")"
        ),
        "outputs": outputs,
        "actions": actions,
    }
