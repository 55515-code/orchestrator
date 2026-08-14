"""Update agent — dependency bumps and polish workflows on agent branches.

Tier 1 autonomy: commits to agent branches only when validation is green.
Merges back to the mainline are Tier 2 and always require a human directive.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..research import source_facts_ready
from .core import (
    TIER_AUTO_IF_GREEN,
    agent_branch_name,
    bounded_validation_limits,
    check_action_permission,
    ensure_python_env,
    prepare_agent_worktree,
    run_command_bounded,
)


def _git(workdir: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=60.0,
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


def _find_polish_task(repo: Any) -> Any | None:
    for task_id in sorted(repo.tasks.keys()):
        if "polish" in task_id.lower():
            return repo.tasks[task_id]
    return None


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

    branch_name = agent_branch_name(agent.repo_slug, "update", date_str)
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

    if (work_root / "pyproject.toml").exists() and shutil.which("uv"):
        result = _run_plain(["uv", "lock", "--upgrade"], work_root)
        actions.append(
            {
                "action": "uv-lock-upgrade",
                "tier": 0,
                "status": "success" if result.get("ok") else "failed",
                "error": result.get("error"),
            }
        )

    if (work_root / "package.json").exists() and shutil.which("npm"):
        result = _run_plain(
            ["npm", "audit", "fix", "--no-audit", "--no-fund"], work_root
        )
        actions.append(
            {
                "action": "npm-audit-fix",
                "tier": 0,
                "status": "success" if result.get("ok") else "failed",
                "error": result.get("error"),
            }
        )

    polish_task = _find_polish_task(repo)
    if polish_task is not None:
        try:
            from ..environment import platform_key

            polish_command = polish_task.command_for_platform(platform_key())
        except Exception as exc:  # noqa: BLE001
            polish_command = None
            actions.append(
                {
                    "action": f"polish:{polish_task.id}",
                    "tier": 0,
                    "status": "failed",
                    "error": f"command resolution: {exc}",
                }
            )
        if polish_command is not None:
            result = _run_plain(polish_command, work_root)
            actions.append(
                {
                    "action": f"polish:{polish_task.id}",
                    "tier": 0,
                    "status": "success" if result.get("ok") else "failed",
                    "error": result.get("error") or result.get("stderr"),
                }
            )
    else:
        actions.append(
            {
                "action": "polish-workflow",
                "tier": 0,
                "status": "skipped",
                "error": "no polish task configured for this repository",
            }
        )

    docs_dir = work_root / "docs"
    docs_fresh = True
    if docs_dir.exists():
        newest = max(
            (path.stat().st_mtime for path in docs_dir.rglob("*.md")),
            default=0.0,
        )
        docs_fresh = (datetime.now(UTC).timestamp() - newest) < 90 * 86400
    actions.append(
        {
            "action": "docs-refresh",
            "tier": 2,
            "status": "queued_for_human" if not docs_fresh else "fresh",
            "note": "docs older than 90 days; refresh requires human review",
        }
    )

    status_output = _git(work_root, "status", "--porcelain")
    changed = bool(status_output and status_output.stdout.strip())
    if not changed:
        return {
            "status": "success",
            "note": "no changes produced by update workflows",
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
    if allowed and worktree_path is not None:
        _git(work_root, "add", "-A")
        _git(
            work_root,
            "commit",
            "-m",
            f"agent(update): dependency and polish updates [{agent.id}]",
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
            "note": f"updates committed to {branch_name} with green tests",
            "outputs": outputs,
            "actions": actions,
        }

    diff_output = _git(work_root, "diff") or None
    diff_text = diff_output.stdout if diff_output else ""
    report_dir = runtime.paths["research"] / agent.repo_slug
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{date_str}-update-failure.md"
    report_path.write_text(
        "\n".join(
            [
                f"# Update agent failure report — {agent.repo_slug} ({date_str})",
                "",
                f"- Branch: `{branch_name}`",
                f"- Commit allowed: `{allowed}` ({reason})",
                (f"- Test detail: `{test_detail.get('reason')}` "
                f"(returncode={test_detail.get('returncode')}, attempts={test_detail.get('attempts')})"),
                "",
                "## stderr tail",
                "",
                "```",
                str(test_detail.get("stderr") or "")[-2000:],
                "```",
                "",
                "## Uncommitted diff",
                "",
                "```diff",
                diff_text[-6000:],
                "```",
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    outputs.append(str(report_path.relative_to(runtime.root)))
    _git(work_root, "checkout", "--", ".")
    _git(work_root, "clean", "-fd")
    actions.append(
        {
            "action": "commit-agent-branch",
            "tier": 1,
            "status": "blocked",
            "reason": reason,
        }
    )
    return {
        "status": "failed",
        "note": f"validation not green; updates not committed ({reason})",
        "outputs": outputs,
        "actions": actions,
    }
