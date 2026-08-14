"""Dev agent — implements backlog patches on isolated agent branches.

Tier 1 autonomy: commits to agent branches only when validation is green.
Tier 2 actions (merge, PR open, deploy) are never performed without an
explicit human directive; v1 does not open PRs at all.
"""

from __future__ import annotations

import json
import re
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

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    ".direnv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "state",
    "memory",
    "generated",
    "site",
    "dist",
    "downloads",
}
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sh",
    ".bash",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".astro",
    ".c",
    ".h",
    ".rs",
    ".go",
    ".txt",
    ".css",
    ".html",
}
TODO_PATTERN = re.compile(r"\b(TODO|FIXME)\b[: ](.+)", re.IGNORECASE)
MAX_SCAN_FILES = 4000
MAX_TODO_ITEMS = 10


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


def _github_remote_repo(repo_path: Path) -> str | None:
    completed = _git(repo_path, "config", "--get", "remote.origin.url")
    if completed is None or completed.returncode != 0:
        return None
    url = completed.stdout.strip()
    match = re.match(r"(?:https://github\.com/|git@github\.com:)([^/]+)/([^/.]+)", url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2).removesuffix('.git')}"


def _list_github_issues(repo_path: Path, gh_repo: str) -> list[dict[str, Any]]:
    import shutil

    if not shutil.which("gh"):
        return []
    try:
        completed = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                gh_repo,
                "--state",
                "open",
                "--limit",
                "5",
                "--json",
                "number,title,labels",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    try:
        payload = json.loads(completed.stdout or "[]")
    except ValueError:
        return []
    return payload if isinstance(payload, list) else []


def _scan_local_todos(repo_path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    scanned = 0
    for path in sorted(repo_path.rglob("*")):
        if scanned >= MAX_SCAN_FILES or len(items) >= MAX_TODO_ITEMS:
            break
        if path.is_dir():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.relative_to(repo_path).parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            match = TODO_PATTERN.search(line)
            if match:
                items.append(
                    {
                        "kind": match.group(1).upper(),
                        "text": match.group(2).strip()[:200],
                        "path": str(path.relative_to(repo_path)),
                        "line": line_no,
                    }
                )
                if len(items) >= MAX_TODO_ITEMS:
                    break
    return items


def _pick_backlog_item(
    repo_path: Path,
) -> tuple[dict[str, Any] | None, str]:
    gh_repo = _github_remote_repo(repo_path)
    if gh_repo:
        issues = _list_github_issues(repo_path, gh_repo)
        if issues:
            top = issues[0]
            return (
                {
                    "source": "github",
                    "id": f"gh-{top.get('number')}",
                    "title": str(top.get("title") or ""),
                },
                f"github:{gh_repo}",
            )
    todos = _scan_local_todos(repo_path)
    if todos:
        top = todos[0]
        return (
            {
                "source": "local-todo",
                "id": "todo-1",
                "title": f"{top['kind']}: {top['text']}",
                "path": top["path"],
                "line": top["line"],
                "all_found": todos,
            },
            "local-todo-scan",
        )
    return None, "none"


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


def _write_report(runtime: Any, repo_slug: str, name: str, lines: list[str]) -> Path:
    date_str = datetime.now(UTC).date().isoformat()
    directory = runtime.paths["research"] / repo_slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date_str}-{name}.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def run(runtime: Any, orchestrator: Any, agent: Any, *, directive: str = "") -> dict[str, Any]:
    repo = runtime.resolve_repo(agent.repo_slug)
    repo_path = (runtime.root / repo.path).resolve()
    policy = runtime.workspace.policy
    date_str = datetime.now(UTC).date().isoformat()
    outputs: list[str] = []
    actions: list[dict[str, Any]] = []

    if policy.require_source_facts_before_mutation and not source_facts_ready(runtime):
        report = _write_report(
            runtime,
            agent.repo_slug,
            "dev-blocked",
            [
                f"# Dev agent blocked — {agent.repo_slug} ({date_str})",
                "",
                "Policy `require_source_facts_before_mutation` is active and source",
                "facts are stale or missing. Run the research agent first:",
                "",
                f"    scripts/substrate_cli.py agent-run --role research-agent --repo {agent.repo_slug}",
            ],
        )
        outputs.append(str(report.relative_to(runtime.root)))
        return {
            "status": "failed",
            "note": "blocked: source facts not fresh (run research agent first)",
            "outputs": outputs,
            "actions": [{"action": "source-facts-gate", "tier": 0, "status": "blocked"}],
        }

    item, item_source = _pick_backlog_item(repo_path)
    actions.append(
        {
            "action": "pick-backlog-item",
            "tier": 0,
            "status": "success" if item else "empty",
            "source": item_source,
        }
    )
    if item is None:
        return {
            "status": "success",
            "note": "no backlog items found (github issues or local TODOs)",
            "outputs": outputs,
            "actions": actions,
        }

    issue_suffix = str(item.get("id") or "").replace("/", "-")
    branch_name = agent_branch_name(
        agent.repo_slug, "dev", date_str, suffix=issue_suffix
    )
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

    objective = (
        f"Implement a patch for: {item.get('title') or item.get('id')} "
        f"(source: {item_source}). Keep changes minimal and add tests where possible."
    )
    chain_error: str | None = None
    chain_run_id: str | None = None
    try:
        chain_run_id = orchestrator.run_chain(
            repo_slug=agent.repo_slug,
            objective=objective,
            chain_path="chains/local-agent-chain.yaml",
            provider=agent.provider,
            model=agent.model,
            stage="local",
            requested_mode="observe",
            allow_mutations=False,
        )
    except Exception as exc:  # noqa: BLE001
        chain_error = f"{type(exc).__name__}: {exc}"
    actions.append(
        {
            "action": "generate-patch-chain",
            "tier": 0,
            "status": "failed" if chain_error else "success",
            "run_id": chain_run_id,
            "error": chain_error,
        }
    )

    status_output = _git(work_root, "status", "--porcelain")
    changed = bool(status_output and status_output.stdout.strip())

    if not changed:
        report = _write_report(
            runtime,
            agent.repo_slug,
            f"dev-nopatch-{issue_suffix}",
            [
                f"# Dev agent report — {agent.repo_slug} ({date_str})",
                "",
                f"- Backlog item: `{item.get('title')}` ({item_source})",
                f"- Branch: `{branch_name}`",
                f"- Chain run: `{chain_run_id or 'n/a'}`",
                f"- Chain error: `{chain_error or 'none'}`",
                "",
                "No file changes were produced by the patch-generation chain.",
                "The agent branch contains no new commits.",
            ],
        )
        outputs.append(str(report.relative_to(runtime.root)))
        return {
            "status": "success",
            "note": "chain produced no file changes; nothing committed",
            "outputs": outputs,
            "actions": actions,
        }

    test_command, test_task_id = _find_test_command(repo)
    limits = bounded_validation_limits(runtime)
    ensure_python_env(work_root)
    tests_green = False
    test_detail: dict[str, Any] = {}
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
            "attempts": test_detail.get("attempts"),
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
            f"agent(dev): {item.get('title') or issue_suffix} [{agent.id}]",
        )
        actions.append(
            {"action": "commit-agent-branch", "tier": 1, "status": "success", "branch": branch_name}
        )
        report = _write_report(
            runtime,
            agent.repo_slug,
            f"dev-patch-{issue_suffix}",
            [
                f"# Dev agent patch — {agent.repo_slug} ({date_str})",
                "",
                f"- Backlog item: `{item.get('title')}` ({item_source})",
                f"- Branch: `{branch_name}`",
                f"- Tests: green (task `{test_task_id}`, {test_detail.get('attempts')} attempt(s))",
                "",
                "Tier 2 actions (merge/PR) require an explicit human directive.",
            ],
        )
        outputs.append(str(report.relative_to(runtime.root)))
        return {
            "status": "success",
            "note": f"patch committed to {branch_name} with green tests",
            "outputs": outputs,
            "actions": actions,
        }

    diff_output = _git(work_root, "diff") or None
    diff_text = diff_output.stdout if diff_output else ""
    report = _write_report(
        runtime,
        agent.repo_slug,
        f"dev-failure-{issue_suffix}",
        [
            f"# Dev agent failure report — {agent.repo_slug} ({date_str})",
            "",
            f"- Backlog item: `{item.get('title')}` ({item_source})",
            f"- Branch: `{branch_name}`",
            f"- Commit allowed: `{allowed}` ({reason})",
            (f"- Test detail: `{test_detail.get('reason')}` "
            f"(returncode={test_detail.get('returncode')}, attempts={test_detail.get('attempts')})"),
            "",
            "## stderr tail",
            "",
            "```",
            (test_detail.get("stderr") or "")[-2000:],
            "```",
            "",
            "## Uncommitted diff",
            "",
            "```diff",
            diff_text[-6000:],
            "```",
        ],
    )
    _git(work_root, "checkout", "--", ".")
    _git(work_root, "clean", "-fd")
    outputs.append(str(report.relative_to(runtime.root)))
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
        "note": f"validation not green; patch not committed ({reason})",
        "outputs": outputs,
        "actions": actions,
    }
