"""Community-manager agent — cross-repo triage and draft responses.

Tier 1 autonomy: triage notes and drafts are written automatically.
Tier 2 actions (sending replies, posting) always require a human directive;
this agent never sends outbound messages.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils


def _run(command: list[str], workdir: Path, *, timeout: float = 60.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _whatsapp_triage(runtime: Any) -> dict[str, Any]:
    gateway_cfg = runtime.workspace.gateway or {}
    plugins_cfg = (gateway_cfg.get("plugins") or {}) if isinstance(gateway_cfg, dict) else {}
    whatsapp_cfg = plugins_cfg.get("whatsapp") or {}
    enabled = bool(gateway_cfg.get("enabled")) and bool(whatsapp_cfg.get("enabled"))
    if not enabled:
        return {
            "action": "whatsapp-triage",
            "tier": 1,
            "status": "skipped",
            "error": "gateway or whatsapp plugin disabled",
        }
    try:
        from ..gateway.manager import GatewayManager

        manager = GatewayManager()
        discovered = manager.discover_plugins()
        if "whatsapp" not in discovered:
            return {
                "action": "whatsapp-triage",
                "tier": 1,
                "status": "unavailable",
                "error": "whatsapp plugin not discovered",
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "whatsapp-triage",
            "tier": 1,
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "action": "whatsapp-triage",
        "tier": 1,
        "status": "success",
        "note": (
            "whatsapp plugin available; inbound messages arrive via webhook and "
            "are not persisted for offline triage in v1 — replies queued for human"
        ),
    }


def _github_remote_repo(repo_path: Path) -> str | None:
    import re

    completed = _run(["git", "config", "--get", "remote.origin.url"], repo_path, timeout=15.0)
    if not completed.get("ok"):
        return None
    url = str(completed.get("stdout") or "").strip()
    match = re.match(r"(?:https://github\.com/|git@github\.com:)([^/]+)/([^/.]+)", url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"


def _github_triage(runtime: Any) -> dict[str, Any]:
    if not shutil.which("gh"):
        return {
            "action": "github-triage",
            "tier": 1,
            "status": "skipped",
            "error": "gh CLI not installed",
        }
    rows: list[dict[str, Any]] = []
    for slug in sorted(runtime.repositories().keys()):
        try:
            repo = runtime.resolve_repo(slug)
        except KeyError:
            continue
        repo_path = (runtime.root / repo.path).resolve()
        gh_repo = _github_remote_repo(repo_path)
        if not gh_repo:
            continue
        issues_result = _run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                gh_repo,
                "--state",
                "open",
                "--limit",
                "10",
                "--json",
                "number,title,labels,createdAt",
            ],
            repo_path,
            timeout=30.0,
        )
        issues: list[dict[str, Any]] = []
        if issues_result.get("ok"):
            try:
                parsed = json.loads(issues_result.get("stdout") or "[]")
                if isinstance(parsed, list):
                    issues = parsed
            except ValueError:
                issues = []
        rows.append(
            {
                "repo_slug": slug,
                "gh_repo": gh_repo,
                "open_issues": issues,
                "issue_count": len(issues),
            }
        )
    if not rows:
        return {
            "action": "github-triage",
            "tier": 1,
            "status": "skipped",
            "error": "no github remotes found across repositories",
        }
    return {"action": "github-triage", "tier": 1, "status": "success", "repos": rows}


def _community_sim(runtime: Any, agent: Any) -> dict[str, Any]:
    from ..community import run_community_cycle

    sim_dir = runtime.paths["research"] / "community-sim"
    sim_dir.mkdir(parents=True, exist_ok=True)
    cycle_index = len(list(sim_dir.glob("*.json")))
    date_str = datetime.now(UTC).date().isoformat()
    try:
        result = run_community_cycle(
            runtime,
            cycle=cycle_index,
            stage="local",
            concurrency_limit=8,
            repo_slug=agent.repo_slug,
            agent_provider="mock",
            population_scale=0.1,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "community-sim-cycle",
            "tier": 0,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
    log_path = sim_dir / f"{date_str}-cycle-{cycle_index}.json"
    log_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "action": "community-sim-cycle",
        "tier": 0,
        "status": "success",
        "cycle": cycle_index,
        "log": str(log_path.relative_to(runtime.root)),
    }


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    _ = orchestrator, directive
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    actions.append(_whatsapp_triage(runtime))
    github_triage = _github_triage(runtime)
    actions.append(github_triage)
    sim_result = _community_sim(runtime, agent)
    actions.append(sim_result)
    actions.append(
        {
            "action": "social-presence",
            "tier": 1,
            "status": "skipped",
            "error": "no social/community sites configured for these repos yet",
        }
    )

    triage_dir = runtime.paths["research"] / "community"
    triage_dir.mkdir(parents=True, exist_ok=True)
    triage_path = triage_dir / f"{date_str}-triage.md"
    lines = [
        f"# Community triage — {date_str}",
        "",
        f"- Agent: `{agent.id}`",
        f"- Generated: {_utils.utc_now_iso()}",
        "",
        "> All replies below are drafts. Sending outbound messages is a Tier 2",
        "> action and requires an explicit human directive.",
        "",
        "## GitHub triage",
        "",
    ]
    repos = github_triage.get("repos") or []
    if repos:
        for row in repos:
            lines.append(f"### {row['repo_slug']} ({row['gh_repo']})")
            lines.append("")
            if not row["open_issues"]:
                lines.append("- No open issues found.")
                continue
            seen_titles: set[str] = set()
            for issue in row["open_issues"][:10]:
                title = str(issue.get("title") or "")
                number = issue.get("number")
                labels = ",".join(
                    label.get("name", "") for label in issue.get("labels", [])
                )
                duplicate = title.strip().lower() in seen_titles
                seen_titles.add(title.strip().lower())
                lines.append(
                    f"- #{number}: {title} (labels: {labels or 'none'})"
                    + (" — possible duplicate" if duplicate else "")
                )
                lines.append("  - Draft reply: acknowledge and triage (human review required).")
            lines.append("")
    else:
        lines.append(f"- Skipped: {github_triage.get('error')}")
        lines.append("")

    lines.extend(
        [
            "## WhatsApp gateway",
            "",
            f"- Status: {actions[0].get('status')}",
            f"- Note: {actions[0].get('note') or actions[0].get('error') or 'n/a'}",
            "",
            "## Community simulation",
            "",
            f"- Status: {sim_result.get('status')}",
            f"- Log: `{sim_result.get('log') or 'n/a'}`",
        ]
    )
    triage_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    outputs.append(str(triage_path.relative_to(runtime.root)))

    failed = [
        action
        for action in actions
        if action.get("status") == "failed"
    ]
    return {
        "status": "failed" if failed else "success",
        "note": f"triage complete ({len(actions)} surface(s) checked)",
        "outputs": outputs,
        "actions": actions,
    }
