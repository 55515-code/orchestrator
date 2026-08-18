"""Maintenance agent — substrate health, automation hygiene, and integration wiring.

Tier 1 autonomy: performs safe verification/reporting tasks automatically.
Repairs and mutations require green validation or an explicit human directive,
depending on the action tier. Child issues are used for long or parallel
delegated work instead of polling other agents/sessions/processes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import _utils
from ..research import source_facts_ready
from .core import (
    TIER_AUTO,
    TIER_AUTO_IF_GREEN,
    TIER_HUMAN,
    agent_branch_name,
    bounded_validation_limits,
    check_action_permission,
    ensure_python_env,
    prepare_agent_worktree,
    run_command_bounded,
)


def _git(
    workdir: Path, *args: str, timeout: float = 60.0
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _run_plain(
    command: list[str], workdir: Path, *, timeout: float = 300.0
) -> dict[str, Any]:
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
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def _find_test_command(repo: Any) -> tuple[list[str] | None, str | None]:
    candidates = sorted(repo.tasks.values(), key=lambda task: task.id)
    for keyword in ("test", "check", "validate"):
        for task in candidates:
            if keyword in task.id.lower():
                try:
                    from ..environment import platform_key

                    return task.command_for_platform(platform_key()), task.id
                except Exception:  # noqa: BLE001
                    continue
    return None, None


def _check_services() -> dict[str, Any]:
    result: dict[str, Any] = {
        "checked": [],
        "active": [],
        "inactive_or_missing": [],
        "notes": [],
    }
    units = [
        "protonmail-bridge.service",
        "proton-bridge-hook.service",
        "substrate-panel.service",
        "substrate-agent-timer.service",
        "substrate-chatbot.service",
        "substrate-lister.service",
    ]
    for unit in units:
        try:
            completed = subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit],
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed is None:
            result["checked"].append(unit)
            result["inactive_or_missing"].append(unit)
            result["notes"].append(f"{unit}: command unavailable")
            continue
        state = "active" if completed.returncode == 0 else "inactive"
        result["checked"].append(unit)
        if state == "active":
            result["active"].append(unit)
        else:
            result["inactive_or_missing"].append(unit)
            result["notes"].append(f"{unit}: {state}")
    return result


def _check_agents(runtime: Any) -> dict[str, Any]:
    try:
        payload = runtime.agent_status()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    agents = payload.get("agents") or []
    failed = [
        {
            "agent_id": item.get("agent_id"),
            "last_status": item.get("last_status"),
            "last_run_at": item.get("last_run_at"),
            "note": item.get("recent_outputs", [])[-1] if item.get("recent_outputs") else None,
        }
        for item in agents
        if item.get("last_status") == "failed"
    ]
    return {
        "ok": True,
        "agents_total": len(agents),
        "failed_count": len(failed),
        "failed": failed[-10:],
    }


def _write_report(
    runtime: Any,
    repo_slug: str,
    *,
    date_str: str,
    actions: list[dict[str, Any]],
    service_check: dict[str, Any],
    agent_check: dict[str, Any],
    health_check: dict[str, Any],
) -> str:
    report_dir = runtime.paths["research"] / repo_slug
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{date_str}-maintenance.md"
    lines = [
        f"# Maintenance agent report — {repo_slug} ({date_str})",
        "",
        "## Service checks",
        "",
        f"- active: {', '.join(service_check.get('active') or ['none'])}",
        f"- inactive/missing: {', '.join(service_check.get('inactive_or_missing') or ['none'])}",
    ]
    if service_check.get("notes"):
        lines.extend(["", "### Notes", ""])
        lines.extend(f"- {note}" for note in service_check["notes"])
    lines.extend(
        [
            "",
            "## Agent automation health",
            "",
            f"- agents_total: {agent_check.get('agents_total', 0)}",
            f"- failed_count: {agent_check.get('failed_count', 0)}",
        ]
    )
    if agent_check.get("failed"):
        lines.extend(["", "### Failed agents", ""])
        for item in agent_check["failed"]:
            lines.append(
                f"- {item.get('agent_id')}: {item.get('last_status')} at {item.get('last_run_at')}"
            )
            if item.get("note"):
                lines.append(f"  - note: {item['note']}")
    lines.extend(
        [
            "",
            "## Health check",
            "",
            f"- result: {health_check.get('result')}",
        ]
    )
    if health_check.get("failures"):
        lines.extend(["", "### Failures", ""])
        for failure in health_check["failures"]:
            lines.append(f"- {failure}")
    lines.extend(["", "## Actions taken", ""])
    if actions:
        for action in actions:
            lines.append(
                f"- {action.get('action')}: {action.get('status')}"
                + (f" ({action.get('error')})" if action.get("error") else "")
            )
    else:
        lines.append("- none")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path.relative_to(runtime.root))


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    repo = runtime.resolve_repo(agent.repo_slug)
    repo_path = (runtime.root / repo.path).resolve()
    policy = runtime.workspace.policy
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    if policy.require_source_facts_before_mutation and not source_facts_ready(runtime):
        return {
            "status": "failed",
            "note": "blocked: source facts not fresh (run research agent first)",
            "outputs": outputs,
            "actions": [{"action": "source-facts-gate", "tier": 0, "status": "blocked"}],
        }

    branch_name = agent_branch_name(agent.repo_slug, "maintenance", date_str)
    worktrees_root = runtime.paths["state"] / "agent-worktrees"
    worktree_path = prepare_agent_worktree(repo_path, worktrees_root, branch_name)
    work_root = worktree_path or repo_path
    actions.append(
        {
            "action": "prepare-agent-branch",
            "tier": 0,
            "status": "success" if worktree_path else "fallback_in_place",
            "branch": branch_name,
        }
    )

    health_check = {"result": "unknown", "failures": []}
    if shutil.which("bash") and (repo_path / "scripts" / "health_check.sh").exists():
        health_result = _run_plain(["bash", "scripts/health_check.sh"], work_root)
        health_check = {
            "result": "ok" if health_result.get("ok") else "failed",
            "failures": [health_result.get("error")] if not health_result.get("ok") else [],
            "returncode": health_result.get("returncode"),
        }
        actions.append(
            {
                "action": "health-check",
                "tier": 0,
                "status": health_check["result"],
                "returncode": health_result.get("returncode"),
            }
        )
    else:
        actions.append({"action": "health-check", "tier": 0, "status": "skipped"})

    service_check = _check_services()
    actions.append(
        {
            "action": "service-check",
            "tier": 0,
            "status": "success" if not service_check.get("inactive_or_missing") else "attention",
            "active": len(service_check.get("active", [])),
            "inactive_or_missing": len(service_check.get("inactive_or_missing", [])),
        }
    )

    agent_check = _check_agents(runtime)
    actions.append(
        {
            "action": "agent-health-check",
            "tier": 0,
            "status": "success" if agent_check.get("failed_count", 0) == 0 else "attention",
            "failed_count": agent_check.get("failed_count", 0),
        }
    )

    report_path = _write_report(
        runtime,
        agent.repo_slug,
        date_str=date_str,
        actions=actions,
        service_check=service_check,
        agent_check=agent_check,
        health_check=health_check,
    )
    outputs.append(report_path)

    changed = False
    if worktree_path is not None:
        status = _git(work_root, "status", "--porcelain")
        changed = bool(status and status.stdout.strip())

    if not changed and not service_check.get("inactive_or_missing") and not agent_check.get("failed"):
        return {
            "status": "success",
            "note": "maintenance check completed; no changes produced",
            "outputs": outputs,
            "actions": actions,
        }

    test_command, test_task_id = _find_test_command(repo)
    limits = bounded_validation_limits(runtime)
    ensure_python_env(work_root)
    if test_command is not None:
        test_detail = run_command_bounded(
            test_command,
            workdir=work_root,
            max_attempts=limits["max_attempts"],
            attempt_timeout_seconds=limits["attempt_timeout_seconds"],
            deadline_seconds=limits["deadline_seconds"],
        )
        tests_green = bool(test_detail.get("ok"))
    else:
        test_detail = {"ok": True, "reason": "no_test_task_configured"}
        tests_green = True
    actions.append(
        {
            "action": "run-tests",
            "tier": 0,
            "status": "green" if tests_green else "red",
            "task": test_task_id,
            "reason": test_detail.get("reason"),
        }
    )

    allowed, reason = check_action_permission(
        agent_tier_cap=agent.autonomy_tier,
        action_tier=TIER_AUTO_IF_GREEN,
        tests_green=tests_green,
        directive=directive,
    )
    if allowed and worktree_path is not None and changed:
        _git(work_root, "add", "-A")
        _git(
            work_root,
            "commit",
            "-m",
            f"agent(maintenance): maintenance report [{agent.id}]",
        )
        actions.append(
            {
                "action": "commit-agent-branch",
                "tier": 1,
                "status": "success",
                "branch": branch_name,
            }
        )
        return {
            "status": "success",
            "note": f"maintenance changes committed to {branch_name}",
            "outputs": outputs,
            "actions": actions,
        }

    if worktree_path is not None:
        _git(work_root, "checkout", "--", ".")
        _git(work_root, "clean", "-fd")
    return {
        "status": "failed" if not tests_green else "success",
        "note": f"maintenance completed without committing changes ({reason})",
        "outputs": outputs,
        "actions": actions,
    }
