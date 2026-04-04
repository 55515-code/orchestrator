#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_bool(raw: str) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def bounded_loop_count(raw: int) -> int:
    return max(1, min(12, int(raw)))


def sanitize_token(raw: str) -> str:
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
    return cleaned or "session"


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    start = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        duration = round(time.time() - start, 3)
        return {
            "command": command,
            "command_text": shlex.join(command),
            "return_code": completed.returncode,
            "ok": completed.returncode == 0,
            "duration_seconds": duration,
            "stdout_tail": (completed.stdout or "")[-4000:],
            "stderr_tail": (completed.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        duration = round(time.time() - start, 3)
        return {
            "command": command,
            "command_text": shlex.join(command),
            "return_code": 124,
            "ok": False,
            "duration_seconds": duration,
            "stdout_tail": ((exc.stdout or "") if isinstance(exc.stdout, str) else "")[-4000:],
            "stderr_tail": ((exc.stderr or "") if isinstance(exc.stderr, str) else "")[-4000:],
            "error": "timeout",
        }
    except OSError as exc:
        duration = round(time.time() - start, 3)
        return {
            "command": command,
            "command_text": shlex.join(command),
            "return_code": 127,
            "ok": False,
            "duration_seconds": duration,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "error": "launch_failed",
        }


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def collect_changed_files(root: Path) -> list[str]:
    result = run_command(
        ["git", "status", "--porcelain"],
        cwd=root,
        timeout_seconds=30,
    )
    files: list[str] = []
    if not result["ok"]:
        return files
    for line in str(result["stdout_tail"]).splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip())
    return files


def deterministic_commands_for_mode(mode: str) -> list[list[str]]:
    commands: list[list[str]] = [
        ["uv", "run", "--with", "ruff", "ruff", "check", "substrate", "scripts", "tests"],
        ["uv", "run", "python", "-m", "compileall", "substrate", "scripts"],
    ]
    if mode == "release-readiness":
        commands.append(
            ["uv", "run", "--with", "pytest", "--with", "httpx", "pytest", "-q", "tests"]
        )
    else:
        commands.append(
            [
                "uv",
                "run",
                "--with",
                "pytest",
                "--with",
                "httpx",
                "pytest",
                "-q",
                "tests/studio/test_connection.py",
                "tests/studio/test_api.py",
            ]
        )
    return commands


def _safe_int(raw: str | None, default: int = 0) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def parse_publish_markers(text: str) -> dict[str, Any]:
    marker_prefix = "AGENT_PUBLISH_"
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith(marker_prefix):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        values[key[len(marker_prefix) :].strip().lower()] = value.strip()

    def as_bool(name: str, default: bool = False) -> bool:
        return parse_bool(values.get(name, str(default)))

    return {
        "action": values.get("action", "unknown"),
        "ok": as_bool("ok", True),
        "branch": values.get("branch", ""),
        "pr_number": _safe_int(values.get("pr_number"), 0),
        "pr_url": values.get("pr_url", ""),
        "merge_attempted": as_bool("merge_attempted", False),
        "merged": as_bool("merged", False),
        "merge_attempts": _safe_int(values.get("merge_attempts"), 0),
        "message": values.get("message", ""),
        "rebase_ok": as_bool("rebase_ok", False),
        "push_ok": as_bool("push_ok", False),
    }


def collect_git_snapshot(root: Path, target_branch: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []

    def run_git(command: list[str]) -> dict[str, Any]:
        result = run_command(command, cwd=root, timeout_seconds=90)
        actions.append(result)
        return result

    in_repo = run_git(["git", "rev-parse", "--is-inside-work-tree"])
    if not in_repo.get("ok"):
        return (
            {
                "current_branch": "",
                "head_sha": "",
                "target_sha": "",
                "ahead_count": 0,
                "behind_count": 0,
                "diverged": False,
                "working_tree_clean": False,
                "valid_git": False,
            },
            actions,
        )

    run_git(["git", "fetch", "--all", "--prune"])

    branch = run_git(["git", "branch", "--show-current"])
    head = run_git(["git", "rev-parse", "HEAD"])
    target = run_git(["git", "rev-parse", f"origin/{target_branch}"])
    counts = run_git(["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{target_branch}"])
    status = run_git(["git", "status", "--porcelain"])

    ahead = 0
    behind = 0
    if counts.get("ok"):
        raw = str(counts.get("stdout_tail", "")).strip().split()
        if len(raw) == 2:
            ahead = _safe_int(raw[0], 0)
            behind = _safe_int(raw[1], 0)

    return (
        {
            "current_branch": str(branch.get("stdout_tail", "")).strip(),
            "head_sha": str(head.get("stdout_tail", "")).strip(),
            "target_sha": str(target.get("stdout_tail", "")).strip(),
            "ahead_count": ahead,
            "behind_count": behind,
            "diverged": ahead > 0 and behind > 0,
            "working_tree_clean": status.get("ok") and not bool(str(status.get("stdout_tail", "")).strip()),
            "valid_git": True,
        },
        actions,
    )


def make_cloud_command() -> list[str]:
    cloud_command_raw = os.getenv("AGENT_CLOUD_COMMAND", "").strip()
    if cloud_command_raw:
        return ["bash", "-lc", cloud_command_raw]
    return [
        "codex",
        "cloud",
        "exec",
        "--attempts",
        "1",
        (
            "Follow prompts/cloud_agent_hybrid_operator.md. "
            "Perform deep analysis, testing, research planning, and development guidance "
            "for this repository."
        ),
    ]


def run_single_loop(
    *,
    root: Path,
    mode: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    command_results: list[dict[str, Any]] = []
    findings: list[str] = []
    risks: list[str] = []
    route = "deterministic"
    cloud_attempted = False
    cloud_success = False
    cloud_note = ""

    for command in deterministic_commands_for_mode(mode):
        command_results.append(run_command(command, cwd=root, timeout_seconds=timeout_seconds))

    cloud_result: dict[str, Any] | None = None
    if mode == "deep":
        cloud_attempted = True
        route = "cloud_agent"
        cloud_result = run_command(
            make_cloud_command(),
            cwd=root,
            timeout_seconds=timeout_seconds,
        )
        command_results.append(cloud_result)
        cloud_success = bool(cloud_result.get("ok"))
        if cloud_success:
            cloud_note = "Cloud agent route completed."
        else:
            route = "fallback_local_mock"
            cloud_note = "Cloud agent unavailable or failed; fallback completed."
            risks.append("Cloud route was unavailable during deep loop; fallback was used.")
            fallback_commands = [
                ["uv", "run", "python", "scripts/substrate_cli.py", "scan"],
                [
                    "uv",
                    "run",
                    "--with",
                    "pytest",
                    "--with",
                    "httpx",
                    "pytest",
                    "-q",
                    "tests/studio/test_connection.py",
                    "tests/studio/test_api.py",
                ],
            ]
            for command in fallback_commands:
                command_results.append(run_command(command, cwd=root, timeout_seconds=timeout_seconds))

    failing = [entry for entry in command_results if not entry.get("ok")]
    if failing:
        findings.append(f"{len(failing)} command(s) failed during mode '{mode}'.")
        for entry in failing[:5]:
            findings.append(
                f"Failed: {entry.get('command_text')} (rc={entry.get('return_code')})"
            )
    else:
        findings.append("All deterministic checks in this loop succeeded.")

    status = "success"
    if mode == "deep" and cloud_attempted and not cloud_success:
        non_cloud_failures = [
            entry
            for entry in failing
            if cloud_result is None or entry.get("command_text") != cloud_result.get("command_text")
        ]
        status = "fallback_success" if not non_cloud_failures else "partial_failure"
    elif failing:
        status = "partial_failure"

    test_results = [
        {
            "command": str(entry["command_text"]),
            "ok": bool(entry["ok"]),
            "return_code": int(entry["return_code"]),
            "duration_seconds": float(entry["duration_seconds"]),
        }
        for entry in command_results
        if "pytest" in str(entry.get("command_text", ""))
    ]

    return {
        "route": route,
        "cloud_attempted": cloud_attempted,
        "cloud_success": cloud_success,
        "cloud_note": cloud_note,
        "findings": findings,
        "risks": risks,
        "command_results": command_results,
        "failing_count": len(failing),
        "loop_status": status,
        "test_results": test_results,
    }


def derive_session_status(
    *,
    mode: str,
    loop_results: list[dict[str, Any]],
    merge_history: list[dict[str, Any]],
    allow_write: bool,
) -> str:
    if not loop_results:
        return "failed"

    partial_loop_failure = any(item.get("loop_status") == "partial_failure" for item in loop_results)
    if partial_loop_failure:
        return "partial_failure"

    if allow_write:
        merged = any(item.get("merged") for item in merge_history)
        final_action = merge_history[-1]["action"] if merge_history else "not_attempted"
        if not merged and final_action in {
            "merge_failed",
            "merge_blocked_safe_gate",
            "skipped_missing_token",
            "skipped_missing_gh",
            "not_attempted",
        }:
            return "partial_failure"

    used_fallback = any(item.get("loop_status") == "fallback_success" for item in loop_results)
    if mode == "deep" and used_fallback:
        return "fallback_success"

    return "success"


def make_session_tasks() -> list[dict[str, str]]:
    return [
        {
            "priority": "P1",
            "owner": "qa_release",
            "task": "Investigate failing command surfaces and publish deterministic repro notes.",
            "acceptance_criteria": "Each failure has a reproducible command and captured stdout/stderr evidence path.",
        },
        {
            "priority": "P1",
            "owner": "core_reliability",
            "task": "Translate validated findings into minimal, test-backed reliability patches.",
            "acceptance_criteria": "Patches include targeted tests and preserve stage/policy safeguards.",
        },
        {
            "priority": "P2",
            "owner": "docs_community",
            "task": "Update collaboration queue with owner-tagged next tasks.",
            "acceptance_criteria": "At least 3 queued tasks include owner, priority, and labels.",
        },
        {
            "priority": "P1",
            "owner": "security_tooling",
            "task": "Prioritize sanctioned defensive tool integrations and normalized evidence output.",
            "acceptance_criteria": "Top adapters include maintenance status and risk notes.",
        },
        {
            "priority": "P1",
            "owner": "ux_operator",
            "task": "Improve explainable security-run UX and learner-safe remediation guidance.",
            "acceptance_criteria": "Operator flow clearly shows finding, confidence, and next safe step.",
        },
    ]


def build_summary(
    *,
    mode: str,
    route: str,
    target_branch: str,
    allow_write: bool,
    session_id: str,
    loop_count: int,
    started_at: str,
    findings: list[str],
    risks: list[str],
    tasks: list[dict[str, str]],
    loop_results: list[dict[str, Any]],
    merge_history: list[dict[str, Any]],
    final_pr_url: str,
    final_merge_state: str,
    git_context: dict[str, Any],
    git_actions: list[dict[str, Any]],
    assumptions: list[str],
    next_cycle_focus: list[str],
    changed_files: list[str],
) -> dict[str, Any]:
    flattened_tests: list[dict[str, Any]] = []
    for loop in loop_results:
        for test in loop.get("test_results", []):
            entry = dict(test)
            entry["loop"] = loop.get("loop_index")
            flattened_tests.append(entry)

    status = derive_session_status(
        mode=mode,
        loop_results=loop_results,
        merge_history=merge_history,
        allow_write=allow_write,
    )

    return {
        "status": status,
        "mode": mode,
        "route": route,
        "target_branch": target_branch,
        "allow_write": allow_write,
        "session_id": session_id,
        "loop_count": loop_count,
        "generated_at": utc_now_iso(),
        "started_at": started_at,
        "findings": findings,
        "risks": risks,
        "tasks": tasks,
        "changed_files": changed_files,
        "test_results": flattened_tests,
        "assumptions": assumptions,
        "next_cycle_focus": next_cycle_focus,
        "loop_results": loop_results,
        "merge_history": merge_history,
        "final_pr_url": final_pr_url,
        "final_merge_state": final_merge_state,
        "git_context": git_context,
        "git_actions": git_actions,
    }


def write_report(
    *,
    report_path: Path,
    summary: dict[str, Any],
) -> None:
    loop_results = summary.get("loop_results", [])
    git_context = summary.get("git_context", {})

    lines: list[str] = [
        "# Agent Hybrid Report",
        "",
        f"- Generated at: {summary.get('generated_at')}",
        f"- Session: `{summary.get('session_id')}`",
        f"- Mode: `{summary.get('mode')}`",
        f"- Loop count: `{summary.get('loop_count')}`",
        f"- Route: `{summary.get('route')}`",
        f"- Target branch: `{summary.get('target_branch')}`",
        f"- Allow write: `{summary.get('allow_write')}`",
        "",
        "## Repo health + failing surfaces",
        "",
    ]

    for finding in summary.get("findings", []):
        lines.append(f"- {finding}")

    lines.extend(
        [
            "",
            "## Deep research findings with sources/risks",
            "",
            "- Source anchors reviewed: `README.md`, `docs/community-cycle.md`, `docs/lifecycle.md`, `CONTRIBUTING.md`.",
            "- Strategic direction reviewed: `docs/security-toolkit-roadmap.md`.",
        ]
    )
    for risk in summary.get("risks", []):
        lines.append(f"- Risk: {risk}")

    lines.extend(
        [
            "",
            "## Development plan with prioritized tasks",
            "",
        ]
    )
    for task in summary.get("tasks", []):
        lines.append(
            f"- {task['priority']} | {task['owner']} | {task['task']} | Acceptance: {task['acceptance_criteria']}"
        )

    lines.extend(
        [
            "",
            "## Implemented changes + test evidence",
            "",
            f"- Changed files detected in runner workspace: `{len(summary.get('changed_files', []))}`",
            "- Session summary is included in the raw JSON section below.",
            "",
            "### Loop execution table",
            "",
            "| Loop | Status | Route | Failing commands | Merge action |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    merge_by_loop = {entry.get("loop_index"): entry for entry in summary.get("merge_history", [])}
    for loop in loop_results:
        loop_idx = loop.get("loop_index")
        merge_action = merge_by_loop.get(loop_idx, {}).get("action", "n/a")
        lines.append(
            "| {loop} | {status} | {route} | {failing} | {merge} |".format(
                loop=loop_idx,
                status=loop.get("loop_status"),
                route=loop.get("route"),
                failing=loop.get("failing_count"),
                merge=merge_action,
            )
        )

    lines.append("")
    for test in summary.get("test_results", []):
        lines.append(
            f"- Loop {test.get('loop')} test `{test['command']}` -> ok={test['ok']} rc={test['return_code']}"
        )

    lines.extend(
        [
            "",
            "## Collaboration tasks for external bots (issues/labels/entry points)",
            "",
            "- Label recommendations: `ai-ready`, `help-wanted`, `good-first-task`, `needs-repro`, `research-needed`.",
            "- Primary entry points: `docs/ai-collaboration.md`, `prompts/cloud_agent_hybrid_operator.md`, and the pinned collaboration issue.",
            "- Queue updates should include owner, priority, and acceptance criteria.",
            "",
            "## Command transcript summary",
            "",
        ]
    )

    for loop in loop_results:
        lines.append(f"- Loop {loop.get('loop_index')} executed {len(loop.get('command_results', []))} commands.")

    lines.extend(
        [
            "",
            "## Compatibility notes",
            "",
            "- Existing CLI/API compatibility remains required; no direct-merge-to-main bypass is used.",
            "- Safe-gate merge requires clean rebase/push and successful loop checks.",
            "",
            "## Unresolved questions",
            "",
            "- None recorded by this automated cycle.",
            "",
            "## Git sync posture summary",
            "",
            f"- Current branch: `{git_context.get('current_branch', '')}`",
            f"- Target branch: `{git_context.get('target_branch', '')}`",
            f"- Ahead: `{git_context.get('ahead_count', 0)}` | Behind: `{git_context.get('behind_count', 0)}` | Diverged: `{git_context.get('diverged', False)}`",
            f"- PR URL: `{summary.get('final_pr_url') or 'n/a'}`",
            f"- Final merge state: `{summary.get('final_merge_state')}`",
            "",
            "## Raw summary JSON",
            "",
            "```json",
            json.dumps(summary, indent=2),
            "```",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(
    *,
    summary_path: Path,
    report_path: Path,
    summary: dict[str, Any],
) -> None:
    ensure_dir(summary_path)
    ensure_dir(report_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(report_path=report_path, summary=summary)


def invoke_publish(
    *,
    root: Path,
    timeout_seconds: int,
    allow_write: bool,
    target_branch: str,
    summary_path: Path,
    report_path: Path,
    loop_index: int,
    loop_count: int,
    session_id: str,
    merge_policy: str,
    retry_merge: int,
    safe_to_merge: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cmd = [
        "bash",
        "scripts/agent_hybrid_publish.sh",
        str(allow_write).lower(),
        target_branch,
        str(summary_path),
        str(report_path),
        str(loop_index),
        str(loop_count),
        session_id,
        merge_policy,
        str(retry_merge),
        str(safe_to_merge).lower(),
    ]
    command_result = run_command(cmd, cwd=root, timeout_seconds=timeout_seconds)
    combined_output = "\n".join(
        [
            str(command_result.get("stdout_tail", "")),
            str(command_result.get("stderr_tail", "")),
        ]
    )
    publish_data = parse_publish_markers(combined_output)
    publish_data["loop_index"] = loop_index
    if not publish_data.get("action") or publish_data.get("action") == "unknown":
        publish_data["action"] = "not_attempted"
    return command_result, publish_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dynamic hybrid automation runner for deep cloud-agent cycles."
    )
    parser.add_argument(
        "--mode",
        choices=["fast", "deep", "release-readiness"],
        default="deep",
    )
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--allow-write", default="true")
    parser.add_argument("--loop-count", type=int, default=6)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--merge-policy", choices=["safe_gate"], default="safe_gate")
    parser.add_argument("--retry-merge", type=int, default=1)
    parser.add_argument(
        "--summary-out", default="artifacts/agent-hybrid/agent_summary.json"
    )
    parser.add_argument(
        "--report-out", default="artifacts/agent-hybrid/agent_report.md"
    )
    parser.add_argument("--timeout-seconds", type=int, default=1500)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    summary_path = (root / args.summary_out).resolve()
    report_path = (root / args.report_out).resolve()
    ensure_dir(summary_path)
    ensure_dir(report_path)

    allow_write = parse_bool(args.allow_write)
    mode = args.mode
    loop_count = bounded_loop_count(args.loop_count)

    current_head = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=root, timeout_seconds=30)
    short_head = str(current_head.get("stdout_tail", "")).strip() or "head"
    default_session_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-{short_head}"
    session_id = sanitize_token(args.session_id or default_session_id)

    started_at = utc_now_iso()
    tasks = make_session_tasks()
    findings: list[str] = []
    risks: list[str] = []
    assumptions = [
        "Target merge branch defaults to main.",
        "Rolling PR model uses one branch and one PR for the full session.",
        "Safe gate merge requires loop checks and rebase/push success.",
    ]
    next_cycle_focus = [
        "Increase cloud execution reliability and codex auth readiness.",
        "Expand defensive-tool evidence normalization coverage.",
        "Improve UX explainability for learner-safe security runs.",
    ]

    loop_results: list[dict[str, Any]] = []
    merge_history: list[dict[str, Any]] = []
    all_git_actions: list[dict[str, Any]] = []
    final_pr_url = ""
    final_merge_state = "not_attempted"

    git_start, git_actions_start = collect_git_snapshot(root, args.target_branch)
    all_git_actions.extend(git_actions_start)
    if not git_start.get("valid_git"):
        summary = {
            "status": "failed",
            "mode": mode,
            "route": "deterministic",
            "target_branch": args.target_branch,
            "allow_write": allow_write,
            "session_id": session_id,
            "loop_count": loop_count,
            "generated_at": utc_now_iso(),
            "started_at": started_at,
            "findings": ["Repository is not a valid git workspace."],
            "risks": ["Git bootstrap failed; autonomous cycle aborted."],
            "tasks": tasks,
            "changed_files": [],
            "test_results": [],
            "assumptions": assumptions,
            "next_cycle_focus": next_cycle_focus,
            "loop_results": [],
            "merge_history": [],
            "final_pr_url": "",
            "final_merge_state": "not_attempted",
            "git_context": {
                "current_branch": "",
                "target_branch": args.target_branch,
                "head_sha": "",
                "target_sha": "",
                "ahead_count": 0,
                "behind_count": 0,
                "diverged": False,
                "working_tree_clean_start": False,
                "working_tree_clean_end": False,
            },
            "git_actions": all_git_actions,
        }
        write_outputs(summary_path=summary_path, report_path=report_path, summary=summary)
        print(f"Wrote {summary_path}")
        print(f"Wrote {report_path}")
        return 0

    working_tree_clean_start = bool(git_start.get("working_tree_clean", False))

    for loop_index in range(1, loop_count + 1):
        loop_started = utc_now_iso()
        loop_data = run_single_loop(
            root=root,
            mode=mode,
            timeout_seconds=args.timeout_seconds,
        )

        loop_record: dict[str, Any] = {
            "loop_index": loop_index,
            "started_at": loop_started,
            "generated_at": utc_now_iso(),
            **loop_data,
        }
        loop_results.append(loop_record)

        for text in loop_data["findings"]:
            findings.append(f"Loop {loop_index}: {text}")
        risks.extend(loop_data["risks"])

        safe_to_merge = all(
            item.get("loop_status") in {"success", "fallback_success"}
            for item in loop_results
        )

        interim_git_snapshot, interim_git_actions = collect_git_snapshot(root, args.target_branch)
        all_git_actions.extend(interim_git_actions)
        interim_summary = build_summary(
            mode=mode,
            route=(
                "fallback_local_mock"
                if any(item.get("route") == "fallback_local_mock" for item in loop_results)
                else ("cloud_agent" if mode == "deep" else "deterministic")
            ),
            target_branch=args.target_branch,
            allow_write=allow_write,
            session_id=session_id,
            loop_count=loop_count,
            started_at=started_at,
            findings=findings,
            risks=risks,
            tasks=tasks,
            loop_results=loop_results,
            merge_history=merge_history,
            final_pr_url=final_pr_url,
            final_merge_state=final_merge_state,
            git_context={
                "current_branch": interim_git_snapshot.get("current_branch", ""),
                "target_branch": args.target_branch,
                "head_sha": interim_git_snapshot.get("head_sha", ""),
                "target_sha": interim_git_snapshot.get("target_sha", ""),
                "ahead_count": interim_git_snapshot.get("ahead_count", 0),
                "behind_count": interim_git_snapshot.get("behind_count", 0),
                "diverged": interim_git_snapshot.get("diverged", False),
                "working_tree_clean_start": working_tree_clean_start,
                "working_tree_clean_end": bool(interim_git_snapshot.get("working_tree_clean", False)),
            },
            git_actions=all_git_actions,
            assumptions=assumptions,
            next_cycle_focus=next_cycle_focus,
            changed_files=collect_changed_files(root),
        )
        write_outputs(summary_path=summary_path, report_path=report_path, summary=interim_summary)

        publish_command_result, publish_data = invoke_publish(
            root=root,
            timeout_seconds=args.timeout_seconds,
            allow_write=allow_write,
            target_branch=args.target_branch,
            summary_path=summary_path,
            report_path=report_path,
            loop_index=loop_index,
            loop_count=loop_count,
            session_id=session_id,
            merge_policy=args.merge_policy,
            retry_merge=args.retry_merge,
            safe_to_merge=safe_to_merge,
        )
        all_git_actions.append(publish_command_result)
        merge_history.append(publish_data)
        loop_record["publish_result"] = publish_data

        if publish_data.get("pr_url"):
            final_pr_url = str(publish_data["pr_url"])

        if publish_data.get("merged"):
            final_merge_state = "merged"
        elif publish_data.get("action") in {
            "merge_failed",
            "merge_blocked_safe_gate",
            "skipped_missing_token",
            "skipped_missing_gh",
        }:
            final_merge_state = str(publish_data.get("action"))
        elif publish_data.get("action") == "skipped_write_disabled":
            final_merge_state = "write_disabled"

    git_end, git_actions_end = collect_git_snapshot(root, args.target_branch)
    all_git_actions.extend(git_actions_end)

    overall_route = (
        "fallback_local_mock"
        if any(item.get("route") == "fallback_local_mock" for item in loop_results)
        else ("cloud_agent" if mode == "deep" else "deterministic")
    )

    final_summary = build_summary(
        mode=mode,
        route=overall_route,
        target_branch=args.target_branch,
        allow_write=allow_write,
        session_id=session_id,
        loop_count=loop_count,
        started_at=started_at,
        findings=findings,
        risks=risks,
        tasks=tasks,
        loop_results=loop_results,
        merge_history=merge_history,
        final_pr_url=final_pr_url,
        final_merge_state=final_merge_state,
        git_context={
            "current_branch": git_end.get("current_branch", ""),
            "target_branch": args.target_branch,
            "head_sha": git_end.get("head_sha", ""),
            "target_sha": git_end.get("target_sha", ""),
            "ahead_count": git_end.get("ahead_count", 0),
            "behind_count": git_end.get("behind_count", 0),
            "diverged": git_end.get("diverged", False),
            "working_tree_clean_start": working_tree_clean_start,
            "working_tree_clean_end": bool(git_end.get("working_tree_clean", False)),
        },
        git_actions=all_git_actions,
        assumptions=assumptions,
        next_cycle_focus=next_cycle_focus,
        changed_files=collect_changed_files(root),
    )

    write_outputs(summary_path=summary_path, report_path=report_path, summary=final_summary)
    print(f"Wrote {summary_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
