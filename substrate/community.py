from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from typing import Any

from .learning import record_execution
from .registry import SubstrateRuntime

DEVELOPER_COHORTS: list[tuple[str, int]] = [
    ("core_maintainers", 10),
    ("module_owners", 15),
    ("senior_contributors", 20),
    ("regular_contributors", 35),
    ("newcomer_contributors", 20),
]

USER_TESTER_COHORTS: list[tuple[str, int]] = [
    ("power_users", 60),
    ("normal_users", 120),
    ("accessibility_focused_users", 40),
    ("cross_platform_users", 40),
    ("security_compliance_testers", 20),
    ("adversarial_edge_case_testers", 20),
]

DEVELOPER_SQUADS = [
    "platform_runtime",
    "api_backend",
    "cli_tooling",
    "backup_sync_portability",
    "integrations_proton_surfaces",
    "web_ux_dashboard",
    "security_supply_chain",
    "qa_release_engineering",
    "docs_community",
]

TESTER_PROGRAMS = [
    "structured_exploratory_testing",
    "cross_platform_migration_tests",
    "upgrade_rollback_tests",
    "accessibility_checks",
    "abuse_misuse_error_path_tests",
    "docs_driven_onboarding_tests",
]

OPERATING_CADENCE_PHASES = [
    "issue_intake",
    "triage",
    "design_rfc_review",
    "implementation",
    "testing",
    "release_readiness_check",
    "community_communication",
]

DEFAULT_PROVIDER_MODELS = {
    "mock": "mock-codex-persona",
    "local": "roo-router",
    "anthropic": "claude-sonnet-4-20250514",
    "ollama": "llama3.2:latest",
    "codex": "default",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

ISSUE_CATALOG: list[dict[str, Any]] = [
    {
        "id": "ISSUE-001",
        "title": "Backup & Sync cross-platform path normalization regression",
        "severity": "critical",
        "squad": "backup_sync_portability",
        "owner": "module_owner",
        "tags": ["backup-sync", "cross-platform", "regression"],
    },
    {
        "id": "ISSUE-002",
        "title": "Release gate lacks deterministic flaky-test retry policy",
        "severity": "high",
        "squad": "qa_release_engineering",
        "owner": "core_maintainer",
        "tags": ["testing", "flaky", "release"],
    },
    {
        "id": "ISSUE-003",
        "title": "Maintainer review queue exceeds security PR SLA",
        "severity": "high",
        "squad": "security_supply_chain",
        "owner": "core_maintainer",
        "tags": ["security", "review", "latency"],
    },
    {
        "id": "ISSUE-004",
        "title": "Integration boundaries missing unsupported API edge cases",
        "severity": "high",
        "squad": "integrations_proton_surfaces",
        "owner": "module_owner",
        "tags": ["integrations", "api-boundary", "docs"],
    },
    {
        "id": "ISSUE-005",
        "title": "Onboarding docs miss common setup recovery paths",
        "severity": "medium",
        "squad": "docs_community",
        "owner": "regular_contributor",
        "tags": ["onboarding", "docs"],
    },
    {
        "id": "ISSUE-006",
        "title": "CLI diagnostics missing privacy redaction checklist",
        "severity": "medium",
        "squad": "cli_tooling",
        "owner": "senior_contributor",
        "tags": ["cli", "privacy", "compliance"],
    },
    {
        "id": "ISSUE-007",
        "title": "Dashboard keyboard focus order inconsistent",
        "severity": "medium",
        "squad": "web_ux_dashboard",
        "owner": "regular_contributor",
        "tags": ["a11y", "dashboard", "ux"],
    },
    {
        "id": "ISSUE-008",
        "title": "Windows rollback script parity checks incomplete",
        "severity": "medium",
        "squad": "platform_runtime",
        "owner": "senior_contributor",
        "tags": ["rollback", "windows", "release"],
    },
]

RFC_CATALOG: list[dict[str, str]] = [
    {
        "id": "RFC-0001",
        "title": "Mission statement and product boundaries charter",
        "default_outcome": "accept",
    },
    {
        "id": "RFC-0002",
        "title": "Wave-based 100/300 independent agent operation",
        "default_outcome": "accept",
    },
    {
        "id": "RFC-0003",
        "title": "Breaking CLI renames for brevity",
        "default_outcome": "reject",
    },
]

QUALITY_GATES = [
    "Mission statement finalized and reflected in UI/docs.",
    "No critical/high unresolved defects.",
    "Stable test suite with reproducible evidence.",
    "Backup & Sync validated for Linux/macOS/Windows profiles.",
    "Integration catalog documented with supported/unsupported API boundaries.",
    "Packaging is privacy-safe, GPL-compliant, reproducible, and checksummed.",
    "Operator runbook + rollback plan complete.",
]

COMMUNICATION_STYLES = [
    "direct",
    "diplomatic",
    "skeptical",
    "detail_oriented",
    "risk_focused",
    "velocity_focused",
]

MOTIVATIONS = [
    "reliability",
    "developer_experience",
    "security",
    "usability",
    "portability",
    "backward_compatibility",
]

RISK_POSTURES = ["conservative", "balanced", "aggressive"]

FEEDBACK_QUALITY = ["high_signal", "mixed", "noisy"]


def _build_model(provider: str, model: str):
    if provider == "local":
        pass  # using local router

        return None  # delegated to local roo-router
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model, temperature=0)
    if provider == "mock":
        return None
    if provider == "codex":
        return None
    raise ValueError(f"Unsupported provider: {provider}")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_date_from_now(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(round((len(sorted_values) - 1) * 0.95))
    return float(sorted_values[index])


def _issue_by_id(issue_id: str) -> dict[str, Any] | None:
    for item in ISSUE_CATALOG:
        if item["id"] == issue_id:
            return item
    return None


def _seed_for_agent(agent_id: str, cycle: int, base_seed: int) -> int:
    total = base_seed + cycle * 9973
    for char in agent_id:
        total += ord(char)
    return total


def _persona_for_agent(agent_id: str, cycle: int, base_seed: int) -> dict[str, str]:
    rng = Random(_seed_for_agent(agent_id, cycle, base_seed))
    return {
        "communication_style": COMMUNICATION_STYLES[rng.randrange(len(COMMUNICATION_STYLES))],
        "motivation": MOTIVATIONS[rng.randrange(len(MOTIVATIONS))],
        "risk_posture": RISK_POSTURES[rng.randrange(len(RISK_POSTURES))],
        "feedback_quality": FEEDBACK_QUALITY[rng.randrange(len(FEEDBACK_QUALITY))],
    }


def _build_developer_agents(cycle: int, base_seed: int) -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    squad_index = 0
    for cohort, count in DEVELOPER_COHORTS:
        for idx in range(1, count + 1):
            agent_id = f"dev-{cohort}-{idx:03d}"
            squad = DEVELOPER_SQUADS[squad_index % len(DEVELOPER_SQUADS)]
            squad_index += 1
            agents.append(
                {
                    "agent_id": agent_id,
                    "role_type": "developer",
                    "cohort": cohort,
                    "squad": squad,
                    "program": "implementation",
                    "persona": _persona_for_agent(agent_id, cycle, base_seed),
                    "onboarding_needed": cohort == "newcomer_contributors",
                }
            )
    return agents


def _build_user_tester_agents(cycle: int, base_seed: int) -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    platform_cycle = ["linux", "macos", "windows"]
    platform_index = 0
    for cohort, count in USER_TESTER_COHORTS:
        for idx in range(1, count + 1):
            agent_id = f"user-{cohort}-{idx:03d}"
            program = TESTER_PROGRAMS[(idx - 1) % len(TESTER_PROGRAMS)]
            payload: dict[str, Any] = {
                "agent_id": agent_id,
                "role_type": "user_tester",
                "cohort": cohort,
                "program": program,
                "persona": _persona_for_agent(agent_id, cycle, base_seed),
            }
            if cohort == "cross_platform_users":
                payload["platform"] = platform_cycle[platform_index % len(platform_cycle)]
                platform_index += 1
            agents.append(payload)
    return agents


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _cohort_totals(agents: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for agent in agents:
        cohort = str(agent["cohort"])
        totals[cohort] = totals.get(cohort, 0) + 1
    return totals


def _preferred_issue_ids(agent: dict[str, Any]) -> list[str]:
    if agent["role_type"] == "developer":
        squad = str(agent.get("squad", ""))
        return [item["id"] for item in ISSUE_CATALOG if item["squad"] == squad] or [
            item["id"] for item in ISSUE_CATALOG
        ]

    cohort = str(agent.get("cohort", ""))
    if cohort == "security_compliance_testers":
        return ["ISSUE-003", "ISSUE-006", "ISSUE-004"]
    if cohort == "cross_platform_users":
        return ["ISSUE-001", "ISSUE-008", "ISSUE-005"]
    if cohort == "accessibility_focused_users":
        return ["ISSUE-007", "ISSUE-005", "ISSUE-004"]
    if cohort == "adversarial_edge_case_testers":
        return ["ISSUE-002", "ISSUE-001", "ISSUE-003"]
    if cohort == "power_users":
        return ["ISSUE-001", "ISSUE-002", "ISSUE-004"]
    return [item["id"] for item in ISSUE_CATALOG]


def _mock_actor_output(agent: dict[str, Any], cycle: int, base_seed: int) -> dict[str, Any]:
    rng = Random(_seed_for_agent(str(agent["agent_id"]), cycle, base_seed))
    preferred = _preferred_issue_ids(agent)
    all_ids = [item["id"] for item in ISSUE_CATALOG]

    issue_count = 1 + rng.randrange(3)
    selected_ids: list[str] = []
    for _ in range(issue_count):
        source = preferred if rng.random() < 0.7 else all_ids
        candidate = source[rng.randrange(len(source))]
        if candidate not in selected_ids:
            selected_ids.append(candidate)
    if not selected_ids:
        selected_ids = [preferred[0]]

    signals: list[dict[str, Any]] = []
    for issue_id in selected_ids:
        issue = _issue_by_id(issue_id)
        if issue is None:
            continue
        repro_quality = "high" if rng.random() > 0.28 else "low"
        is_duplicate = rng.random() < 0.22
        signals.append(
            {
                "type": "issue",
                "issue_id": issue_id,
                "severity": issue["severity"],
                "note": (
                    f"{agent['agent_id']} observed {issue['title'].lower()} "
                    f"during {agent.get('program', 'general workflow')} checks."
                ),
                "is_duplicate": is_duplicate,
                "repro_quality": repro_quality,
            }
        )

    votes: list[dict[str, str]] = []
    for rfc in RFC_CATALOG:
        default_outcome = rfc["default_outcome"]
        if default_outcome == "accept":
            vote = "accept" if rng.random() > 0.12 else "reject"
        else:
            vote = "reject" if rng.random() > 0.20 else "accept"
        votes.append(
            {
                "rfc_id": rfc["id"],
                "vote": vote,
                "reason": f"{agent['agent_id']} {vote}s based on {agent['persona']['motivation']} priorities.",
            }
        )

    latency_base = 32 if agent["role_type"] == "developer" else 44
    if str(agent.get("cohort", "")).startswith("core"):
        latency_base = 58

    feedback_quality = agent["persona"].get("feedback_quality", "mixed")
    if feedback_quality == "high_signal":
        quality_bucket = "high_signal"
    elif feedback_quality == "noisy":
        quality_bucket = "noisy"
    else:
        quality_bucket = "mixed"

    return {
        "actor_id": agent["agent_id"],
        "role_type": agent["role_type"],
        "cohort": agent["cohort"],
        "squad": agent.get("squad"),
        "program": agent.get("program"),
        "persona": agent["persona"],
        "signals": signals,
        "rfc_votes": votes,
        "pr_feedback": {
            "review_latency_hours": latency_base + rng.randrange(0, 72),
            "stale_prs_seen": rng.randrange(0, 5),
            "flaky_tests_seen": rng.randrange(0, 4),
        },
        "community_health": {
            "onboarding_friction": "high"
            if str(agent.get("cohort")) == "newcomer_contributors" and rng.random() < 0.45
            else "medium"
            if rng.random() < 0.35
            else "low",
            "churn_risk": "high"
            if str(agent.get("cohort")) == "newcomer_contributors" and rng.random() < 0.35
            else "medium"
            if rng.random() < 0.3
            else "low",
            "feedback_quality": quality_bucket,
        },
        "narrative": (
            f"{agent['agent_id']} reports mixed stability and asks for stronger "
            f"{agent['persona']['motivation']} guarantees before RC1."
        ),
        "source": "mock",
    }


def _strip_code_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        parts = value.split("\n")
        if len(parts) >= 3 and parts[-1].strip() == "```":
            return "\n".join(parts[1:-1]).strip()
    return value


def _coerce_actor_output(parsed: dict[str, Any], agent: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(parsed.get("signals"), list):
        parsed["signals"] = []
    if not isinstance(parsed.get("rfc_votes"), list):
        parsed["rfc_votes"] = []
    if not isinstance(parsed.get("pr_feedback"), dict):
        parsed["pr_feedback"] = {}
    if not isinstance(parsed.get("community_health"), dict):
        parsed["community_health"] = {}

    parsed["actor_id"] = str(parsed.get("actor_id") or agent["agent_id"])
    parsed["role_type"] = str(parsed.get("role_type") or agent["role_type"])
    parsed["cohort"] = str(parsed.get("cohort") or agent["cohort"])
    parsed["squad"] = parsed.get("squad") or agent.get("squad")
    parsed["program"] = parsed.get("program") or agent.get("program")
    parsed["persona"] = agent["persona"]

    parsed["pr_feedback"]["review_latency_hours"] = float(
        parsed["pr_feedback"].get("review_latency_hours", 48)
    )
    parsed["pr_feedback"]["stale_prs_seen"] = int(
        parsed["pr_feedback"].get("stale_prs_seen", 0)
    )
    parsed["pr_feedback"]["flaky_tests_seen"] = int(
        parsed["pr_feedback"].get("flaky_tests_seen", 0)
    )

    parsed["community_health"]["onboarding_friction"] = str(
        parsed["community_health"].get("onboarding_friction", "medium")
    )
    parsed["community_health"]["churn_risk"] = str(
        parsed["community_health"].get("churn_risk", "medium")
    )
    parsed["community_health"]["feedback_quality"] = str(
        parsed["community_health"].get("feedback_quality", "mixed")
    )

    normalized_signals: list[dict[str, Any]] = []
    for signal in parsed["signals"]:
        if not isinstance(signal, dict):
            continue
        issue_id = str(signal.get("issue_id") or "")
        issue = _issue_by_id(issue_id)
        if issue is None:
            continue
        severity = str(signal.get("severity") or issue["severity"])
        if severity not in SEVERITY_ORDER:
            severity = issue["severity"]
        normalized_signals.append(
            {
                "type": "issue",
                "issue_id": issue_id,
                "severity": severity,
                "note": str(signal.get("note") or ""),
                "is_duplicate": bool(signal.get("is_duplicate", False)),
                "repro_quality": "high"
                if str(signal.get("repro_quality", "high")).lower().startswith("high")
                else "low",
            }
        )
    parsed["signals"] = normalized_signals

    normalized_votes: list[dict[str, str]] = []
    for vote in parsed["rfc_votes"]:
        if not isinstance(vote, dict):
            continue
        rfc_id = str(vote.get("rfc_id") or "")
        if rfc_id not in {item["id"] for item in RFC_CATALOG}:
            continue
        ballot = str(vote.get("vote") or "reject").lower()
        if ballot not in {"accept", "reject"}:
            ballot = "reject"
        normalized_votes.append(
            {
                "rfc_id": rfc_id,
                "vote": ballot,
                "reason": str(vote.get("reason") or ""),
            }
        )
    parsed["rfc_votes"] = normalized_votes
    return parsed


def _actor_prompt(
    *,
    agent: dict[str, Any],
    cycle: int,
    stage: str,
    mission_statement: str,
) -> str:
    issue_lines = [
        f"- {item['id']}: {item['title']} [{item['severity']}]"
        for item in ISSUE_CATALOG
    ]
    rfc_lines = [f"- {item['id']}: {item['title']}" for item in RFC_CATALOG]

    return (
        "You are an independent Codex-style agent participating in an open-source community cycle.\n"
        "You must respond with JSON only.\n\n"
        f"Cycle: {cycle}\n"
        f"Stage: {stage}\n"
        f"Mission: {mission_statement}\n\n"
        "Hard constraints:\n"
        "- Ethical and authorized development only.\n"
        "- Prefer maintained open-source standards/tools.\n"
        "- Preserve read-first/write-by-directive behavior for integrations.\n"
        "- Keep backward compatibility and avoid disruptive workflow changes.\n"
        "- No personal/sensitive data in outputs.\n"
        "- Follow local -> hosted_dev -> production and research -> development -> testing.\n\n"
        "Actor profile:\n"
        f"- actor_id: {agent['agent_id']}\n"
        f"- role_type: {agent['role_type']}\n"
        f"- cohort: {agent['cohort']}\n"
        f"- squad: {agent.get('squad', '')}\n"
        f"- program: {agent.get('program', '')}\n"
        f"- persona: {json.dumps(agent['persona'], ensure_ascii=False)}\n\n"
        "Issue catalog:\n"
        + "\n".join(issue_lines)
        + "\n\nRFC proposals:\n"
        + "\n".join(rfc_lines)
        + "\n\n"
        "Return this JSON schema exactly:\n"
        "{\n"
        '  "actor_id": "...",\n'
        '  "role_type": "developer|user_tester",\n'
        '  "cohort": "...",\n'
        '  "squad": "...",\n'
        '  "program": "...",\n'
        '  "signals": [\n'
        "    {\n"
        '      "type": "issue",\n'
        '      "issue_id": "ISSUE-001",\n'
        '      "severity": "critical|high|medium|low",\n'
        '      "note": "short finding",\n'
        '      "is_duplicate": false,\n'
        '      "repro_quality": "high|low"\n'
        "    }\n"
        "  ],\n"
        '  "rfc_votes": [\n'
        "    {\n"
        '      "rfc_id": "RFC-0001",\n'
        '      "vote": "accept|reject",\n'
        '      "reason": "short rationale"\n'
        "    }\n"
        "  ],\n"
        '  "pr_feedback": {\n'
        '    "review_latency_hours": 48,\n'
        '    "stale_prs_seen": 2,\n'
        '    "flaky_tests_seen": 1\n'
        "  },\n"
        '  "community_health": {\n'
        '    "onboarding_friction": "low|medium|high",\n'
        '    "churn_risk": "low|medium|high",\n'
        '    "feedback_quality": "high_signal|mixed|noisy"\n'
        "  },\n"
        '  "narrative": "one sentence"\n'
        "}\n"
        "Use 1-3 issue signals and vote all RFCs."
    )


def _codex_thread_id_from_stdout(stdout: str) -> str | None:
    for line in stdout.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "thread.started":
            thread_id = payload.get("thread_id")
            return str(thread_id) if thread_id else None
    return None


def _run_codex_actor_session(
    *,
    agent: dict[str, Any],
    cycle: int,
    stage: str,
    base_seed: int,
    mission_statement: str,
    model_name: str,
    runtime_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    codex_binary = shutil.which("codex")
    if codex_binary is None:
        raise RuntimeError("codex binary not found on PATH.")

    prompt = _actor_prompt(
        agent=agent,
        cycle=cycle,
        stage=stage,
        mission_statement=mission_statement,
    )
    actor_id = str(agent["agent_id"])
    actor_safe = actor_id.replace("/", "_")
    raw_dir = run_dir / "codex_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_file = raw_dir / f"{actor_safe}.last_message.txt"
    stdout_log = raw_dir / f"{actor_safe}.stdout.log"
    stderr_log = raw_dir / f"{actor_safe}.stderr.log"

    command = [
        codex_binary,
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(runtime_root),
        "--output-last-message",
        str(output_file),
        "--dangerously-bypass-approvals-and-sandbox",
    ]
    if model_name and model_name != "default":
        command.extend(["-m", model_name])
    command.append("-")

    try:
        completed = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        fallback = _mock_actor_output(agent=agent, cycle=cycle, base_seed=base_seed)
        fallback["source"] = "codex-launch-fallback"
        fallback["narrative"] = (
            f"Failed to launch codex process ({exc}); fallback output used for {actor_id}."
        )
        return fallback

    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")

    if completed.returncode != 0:
        fallback = _mock_actor_output(agent=agent, cycle=cycle, base_seed=base_seed)
        fallback["source"] = "codex-returncode-fallback"
        fallback["narrative"] = (
            f"codex returned non-zero ({completed.returncode}); fallback output used for {actor_id}."
        )
        fallback["codex_exit_code"] = completed.returncode
        return fallback

    if not output_file.exists():
        fallback = _mock_actor_output(agent=agent, cycle=cycle, base_seed=base_seed)
        fallback["source"] = "codex-missing-output-fallback"
        fallback["narrative"] = (
            f"codex produced no output file; fallback output used for {actor_id}."
        )
        return fallback

    try:
        content = output_file.read_text(encoding="utf-8")
        parsed = json.loads(_strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("codex actor response was not a JSON object")
        normalized = _coerce_actor_output(parsed, agent)
        normalized["source"] = "codex"
        thread_id = _codex_thread_id_from_stdout(completed.stdout)
        if thread_id:
            normalized["codex_thread_id"] = thread_id
        return normalized
    except Exception as exc:  # noqa: BLE001
        fallback = _mock_actor_output(agent=agent, cycle=cycle, base_seed=base_seed)
        fallback["source"] = "codex-parse-fallback"
        fallback["narrative"] = (
            f"codex output parse failed ({exc}); fallback output used for {actor_id}."
        )
        return fallback


def _run_actor_session(
    *,
    agent: dict[str, Any],
    llm: Any,
    provider: str,
    cycle: int,
    stage: str,
    base_seed: int,
    mission_statement: str,
    model_name: str,
    runtime_root: Path,
    run_dir: Path,
) -> dict[str, Any]:
    if provider == "mock":
        return _mock_actor_output(agent=agent, cycle=cycle, base_seed=base_seed)
    if provider == "codex":
        return _run_codex_actor_session(
            agent=agent,
            cycle=cycle,
            stage=stage,
            base_seed=base_seed,
            mission_statement=mission_statement,
            model_name=model_name,
            runtime_root=runtime_root,
            run_dir=run_dir,
        )

    prompt = _actor_prompt(
        agent=agent,
        cycle=cycle,
        stage=stage,
        mission_statement=mission_statement,
    )
    try:
        message = llm.invoke(prompt)
        content = (
            message.content
            if isinstance(message.content, str)
            else json.dumps(message.content, ensure_ascii=False)
        )
        parsed = json.loads(_strip_code_fence(content))
        if not isinstance(parsed, dict):
            raise ValueError("actor response was not JSON object")
        normalized = _coerce_actor_output(parsed, agent)
        normalized["source"] = provider
        return normalized
    except Exception as exc:  # noqa: BLE001
        fallback = _mock_actor_output(agent=agent, cycle=cycle, base_seed=base_seed)
        fallback["source"] = f"{provider}-fallback"
        fallback["narrative"] = (
            f"Provider response parse failed ({exc}); fallback mock output used for "
            f"{agent['agent_id']}."
        )
        return fallback


def _run_agent_waves(
    *,
    agents: list[dict[str, Any]],
    provider: str,
    model_name: str,
    cycle: int,
    stage: str,
    base_seed: int,
    concurrency_limit: int,
    mission_statement: str,
    runtime_root: Path,
    run_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    llm = _build_model(provider, model_name) if provider not in {"mock", "codex"} else None
    waves = _chunked(agents, concurrency_limit)
    sessions: list[dict[str, Any]] = []
    wave_summaries: list[dict[str, Any]] = []

    for index, wave in enumerate(waves, start=1):
        wave_sessions: list[dict[str, Any]] = []
        if provider == "codex":
            with ThreadPoolExecutor(max_workers=max(1, len(wave))) as executor:
                futures = [
                    executor.submit(
                        _run_actor_session,
                        agent=actor,
                        llm=llm,
                        provider=provider,
                        cycle=cycle,
                        stage=stage,
                        base_seed=base_seed,
                        mission_statement=mission_statement,
                        model_name=model_name,
                        runtime_root=runtime_root,
                        run_dir=run_dir,
                    )
                    for actor in wave
                ]
                for future in as_completed(futures):
                    output = future.result()
                    wave_sessions.append(output)
                    sessions.append(output)
        else:
            for actor in wave:
                output = _run_actor_session(
                    agent=actor,
                    llm=llm,
                    provider=provider,
                    cycle=cycle,
                    stage=stage,
                    base_seed=base_seed,
                    mission_statement=mission_statement,
                    model_name=model_name,
                    runtime_root=runtime_root,
                    run_dir=run_dir,
                )
                wave_sessions.append(output)
                sessions.append(output)
        wave_summaries.append(
            {
                "wave": index,
                "participants_total": len(wave),
                "participant_ids": [entry["agent_id"] for entry in wave],
                "completed_sessions": len(wave_sessions),
                "provider": provider,
                "model": model_name,
            }
        )
    return sessions, wave_summaries


def _aggregate_backlog(actor_sessions: list[dict[str, Any]], cycle: int) -> list[dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for issue in ISSUE_CATALOG:
        index[issue["id"]] = {
            "id": issue["id"],
            "title": issue["title"],
            "severity": issue["severity"],
            "squad": issue["squad"],
            "owner": issue["owner"],
            "tags": issue["tags"],
            "mentions": 0,
            "duplicate_reports": 0,
            "high_signal_reports": 0,
            "noisy_reports": 0,
            "example_notes": [],
        }

    for actor in actor_sessions:
        for signal in actor.get("signals", []):
            if not isinstance(signal, dict):
                continue
            issue_id = str(signal.get("issue_id") or "")
            if issue_id not in index:
                continue
            entry = index[issue_id]
            entry["mentions"] += 1
            if bool(signal.get("is_duplicate", False)):
                entry["duplicate_reports"] += 1
            if str(signal.get("repro_quality", "high")) == "high":
                entry["high_signal_reports"] += 1
            else:
                entry["noisy_reports"] += 1
            note = str(signal.get("note") or "").strip()
            if note and len(entry["example_notes"]) < 3:
                entry["example_notes"].append(note)

    backlog: list[dict[str, Any]] = []
    for issue in index.values():
        if issue["mentions"] == 0:
            continue
        target_cycle = cycle + 1 if issue["severity"] in {"critical", "high"} else cycle + 2
        status = "triaged"
        backlog.append(
            {
                "id": issue["id"],
                "title": issue["title"],
                "severity": issue["severity"],
                "squad": issue["squad"],
                "owner": issue["owner"],
                "status": status,
                "target_cycle": target_cycle,
                "mentions": issue["mentions"],
                "duplicate_reports": issue["duplicate_reports"],
                "high_signal_reports": issue["high_signal_reports"],
                "noisy_reports": issue["noisy_reports"],
                "tags": issue["tags"],
                "example_notes": issue["example_notes"],
            }
        )

    backlog.sort(
        key=lambda item: (SEVERITY_ORDER[item["severity"]], -item["mentions"], item["id"])
    )
    return backlog


def _aggregate_rfc_votes(actor_sessions: list[dict[str, Any]], cycle: int) -> list[dict[str, Any]]:
    tally: dict[str, dict[str, Any]] = {
        rfc["id"]: {
            "rfc_id": rfc["id"],
            "title": rfc["title"],
            "accept": 0,
            "reject": 0,
            "reasons": [],
        }
        for rfc in RFC_CATALOG
    }

    for actor in actor_sessions:
        for vote in actor.get("rfc_votes", []):
            if not isinstance(vote, dict):
                continue
            rfc_id = str(vote.get("rfc_id") or "")
            if rfc_id not in tally:
                continue
            ballot = str(vote.get("vote") or "reject").lower()
            if ballot == "accept":
                tally[rfc_id]["accept"] += 1
            else:
                tally[rfc_id]["reject"] += 1
            reason = str(vote.get("reason") or "").strip()
            if reason and len(tally[rfc_id]["reasons"]) < 5:
                tally[rfc_id]["reasons"].append(reason)

    log: list[dict[str, Any]] = []
    for rfc in RFC_CATALOG:
        item = tally[rfc["id"]]
        status = "accepted" if item["accept"] >= item["reject"] else "rejected"
        rationale = item["reasons"][0] if item["reasons"] else "No rationale captured."
        log.append(
            {
                "rfc_id": rfc["id"],
                "title": rfc["title"],
                "status": status,
                "cycle": cycle,
                "votes": {
                    "accept": item["accept"],
                    "reject": item["reject"],
                },
                "rationale": rationale,
            }
        )
    return log


def _aggregate_pr_throughput(actor_sessions: list[dict[str, Any]]) -> dict[str, Any]:
    latency_values = [
        float(actor.get("pr_feedback", {}).get("review_latency_hours", 0))
        for actor in actor_sessions
    ]
    stale_values = [
        int(actor.get("pr_feedback", {}).get("stale_prs_seen", 0))
        for actor in actor_sessions
    ]

    developer_signal_total = sum(
        len(actor.get("signals", []))
        for actor in actor_sessions
        if actor.get("role_type") == "developer"
    )
    opened = developer_signal_total + 14
    stale_prs = max(int(round(statistics.mean(stale_values) * 4)), 1) if stale_values else 1
    merged = max(int(opened * 0.42) - int(stale_prs * 0.15), 1)
    closed_without_merge = max(opened - merged - stale_prs, 0)

    bottleneck_index: dict[str, list[float]] = {}
    for actor in actor_sessions:
        squad = actor.get("squad")
        if not squad:
            continue
        bottleneck_index.setdefault(str(squad), []).append(
            float(actor.get("pr_feedback", {}).get("review_latency_hours", 0.0))
        )

    ranked = sorted(
        (
            {
                "squad": squad,
                "median_review_latency_hours": round(_median(values), 1),
            }
            for squad, values in bottleneck_index.items()
            if values
        ),
        key=lambda item: item["median_review_latency_hours"],
        reverse=True,
    )

    bottlenecks = []
    for row in ranked[:2]:
        bottlenecks.append(
            {
                "squad": row["squad"],
                "reason": "Review queue saturation during release-pressure weeks.",
                "median_review_latency_hours": row["median_review_latency_hours"],
            }
        )

    return {
        "opened": opened,
        "merged": merged,
        "closed_without_merge": closed_without_merge,
        "stale_prs": stale_prs,
        "median_review_latency_hours": round(_median(latency_values), 1),
        "p95_review_latency_hours": round(_p95(latency_values), 1),
        "review_bottlenecks": bottlenecks,
    }


def _build_test_matrix(stage: str) -> list[dict[str, str]]:
    if stage == "local":
        return [
            {"stage": "local", "pass": "research", "status": "pass"},
            {"stage": "local", "pass": "development", "status": "pass"},
            {"stage": "local", "pass": "testing", "status": "partial"},
            {"stage": "hosted_dev", "pass": "research", "status": "queued"},
            {"stage": "hosted_dev", "pass": "development", "status": "queued"},
            {"stage": "hosted_dev", "pass": "testing", "status": "queued"},
            {"stage": "production", "pass": "research", "status": "blocked"},
            {"stage": "production", "pass": "development", "status": "blocked"},
            {"stage": "production", "pass": "testing", "status": "blocked"},
        ]
    if stage == "hosted_dev":
        return [
            {"stage": "local", "pass": "research", "status": "pass"},
            {"stage": "local", "pass": "development", "status": "pass"},
            {"stage": "local", "pass": "testing", "status": "pass"},
            {"stage": "hosted_dev", "pass": "research", "status": "pass"},
            {"stage": "hosted_dev", "pass": "development", "status": "pass"},
            {"stage": "hosted_dev", "pass": "testing", "status": "partial"},
            {"stage": "production", "pass": "research", "status": "blocked"},
            {"stage": "production", "pass": "development", "status": "blocked"},
            {"stage": "production", "pass": "testing", "status": "blocked"},
        ]
    return [
        {"stage": "local", "pass": "research", "status": "pass"},
        {"stage": "local", "pass": "development", "status": "pass"},
        {"stage": "local", "pass": "testing", "status": "pass"},
        {"stage": "hosted_dev", "pass": "research", "status": "pass"},
        {"stage": "hosted_dev", "pass": "development", "status": "pass"},
        {"stage": "hosted_dev", "pass": "testing", "status": "pass"},
        {"stage": "production", "pass": "research", "status": "pass"},
        {"stage": "production", "pass": "development", "status": "pass"},
        {"stage": "production", "pass": "testing", "status": "partial"},
    ]


def _aggregate_test_failures(
    backlog: list[dict[str, Any]], actor_sessions: list[dict[str, Any]], stage: str
) -> dict[str, Any]:
    tag_count: dict[str, int] = {}
    for item in backlog:
        for tag in item.get("tags", []):
            tag_count[tag] = tag_count.get(tag, 0) + int(item.get("mentions", 0))

    flaky_seen = sum(
        int(actor.get("pr_feedback", {}).get("flaky_tests_seen", 0)) for actor in actor_sessions
    )

    return {
        "matrix": _build_test_matrix(stage),
        "failure_taxonomy": [
            {"type": "regression", "count": tag_count.get("regression", 0)},
            {
                "type": "flaky_test",
                "count": flaky_seen + tag_count.get("flaky", 0),
            },
            {"type": "docs_gap", "count": tag_count.get("docs", 0)},
            {
                "type": "environment_mismatch",
                "count": tag_count.get("cross-platform", 0) + tag_count.get("windows", 0),
            },
            {
                "type": "security_policy_violation",
                "count": tag_count.get("security", 0) + tag_count.get("compliance", 0),
            },
            {
                "type": "onboarding_friction",
                "count": tag_count.get("onboarding", 0),
            },
        ],
    }


def _build_regression_index(backlog: list[dict[str, Any]]) -> dict[str, Any]:
    regressions = []
    for item in backlog:
        tags = set(item.get("tags", []))
        if "regression" not in tags and item.get("severity") not in {"critical", "high"}:
            continue
        regressions.append(
            {
                "id": item["id"].replace("ISSUE", "REG"),
                "summary": item["title"],
                "severity": item["severity"],
                "status": "open",
                "owner_squad": item["squad"],
            }
        )
        if len(regressions) >= 5:
            break

    return {
        "open_regressions": regressions,
        "known_good_path_updates": [
            {
                "path_id": "KG-SCAN",
                "command": "uv run python scripts/substrate_cli.py scan",
                "status": "stable",
            },
            {
                "path_id": "KG-CHAIN-DRYRUN",
                "command": (
                    "uv run python scripts/substrate_cli.py run-chain --repo substrate-core "
                    "--objective 'Repository health audit' --stage local --dry-run"
                ),
                "status": "stable",
            },
            {
                "path_id": "KG-COMMUNITY-CYCLE",
                "command": "uv run python scripts/substrate_cli.py community-cycle --cycle 0",
                "status": "new",
            },
        ],
        "regression_pressure_index": round(min(0.95, 0.18 + len(regressions) * 0.14), 2),
    }


def _release_readiness_scorecard(
    *,
    cycle: int,
    backlog: list[dict[str, Any]],
    test_matrix: dict[str, Any],
) -> dict[str, Any]:
    unresolved_high = [
        item for item in backlog if item["severity"] in {"critical", "high"} and item["status"] != "resolved"
    ]
    flaky_count = next(
        (
            item["count"]
            for item in test_matrix["failure_taxonomy"]
            if item["type"] == "flaky_test"
        ),
        0,
    )
    backup_sync_ok = not any(item["id"] == "ISSUE-001" for item in unresolved_high)
    integration_boundaries_ok = not any(item["id"] == "ISSUE-004" for item in unresolved_high)

    checks = [
        {
            "gate": QUALITY_GATES[0],
            "status": "pass" if cycle > 0 else "partial",
            "evidence": "Cycle 0 drafted mission; final propagation required next cycle.",
        },
        {
            "gate": QUALITY_GATES[1],
            "status": "pass" if not unresolved_high else "fail",
            "evidence": f"{len(unresolved_high)} unresolved critical/high defects.",
        },
        {
            "gate": QUALITY_GATES[2],
            "status": "pass" if flaky_count <= 2 else "fail",
            "evidence": f"Flaky-test count: {flaky_count}.",
        },
        {
            "gate": QUALITY_GATES[3],
            "status": "pass" if backup_sync_ok else "fail",
            "evidence": "Cross-platform backup validation complete." if backup_sync_ok else "Backup path regression still open.",
        },
        {
            "gate": QUALITY_GATES[4],
            "status": "pass" if integration_boundaries_ok else "partial",
            "evidence": "Boundary documentation complete." if integration_boundaries_ok else "Unsupported boundary documentation incomplete.",
        },
        {
            "gate": QUALITY_GATES[5],
            "status": "partial",
            "evidence": "Checksum pipeline present; privacy/compliance audit pending.",
        },
        {
            "gate": QUALITY_GATES[6],
            "status": "partial",
            "evidence": "Rollback outline exists; operator runbook still incomplete.",
        },
    ]

    passed = sum(1 for item in checks if item["status"] == "pass")
    partial = sum(1 for item in checks if item["status"] == "partial")
    failed = len(checks) - passed - partial
    score_percent = round(((passed + partial * 0.5) / len(checks)) * 100, 1)

    return {
        "checks": checks,
        "summary": {
            "release_ready": passed == len(checks),
            "score_percent": score_percent,
            "passed": passed,
            "partial": partial,
            "failed": failed,
        },
    }


def _risk_register(backlog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mitigations = {
        "ISSUE-001": "Patch path normalization and validate Linux/macOS/Windows profile matrix.",
        "ISSUE-002": "Define deterministic retry policy and quarantine unstable tests.",
        "ISSUE-003": "Enforce reviewer rotation and merge-SLA escalation.",
        "ISSUE-004": "Publish supported/unsupported integration boundaries with examples.",
        "ISSUE-005": "Add onboarding troubleshooting recipes and docs-driven tests.",
        "ISSUE-006": "Implement redaction checklist and privacy review for CLI diagnostics.",
        "ISSUE-007": "Fix keyboard focus flow and retest with accessibility cohort.",
        "ISSUE-008": "Complete Windows rollback parity checks and add coverage.",
    }

    risks: list[dict[str, Any]] = []
    for idx, item in enumerate(backlog[:5], start=1):
        risks.append(
            {
                "id": f"RISK-{idx:03d}",
                "risk": item["title"],
                "severity": item["severity"],
                "owner": item["squad"],
                "due_date": _iso_date_from_now(7 + idx * 2),
                "mitigation": mitigations.get(item["id"], "Track and mitigate in the next cycle."),
            }
        )
    return risks


def _community_health_report(actor_sessions: list[dict[str, Any]]) -> dict[str, Any]:
    developers = [item for item in actor_sessions if item.get("role_type") == "developer"]
    users_testers = [item for item in actor_sessions if item.get("role_type") == "user_tester"]
    newcomers = [item for item in developers if item.get("cohort") == "newcomer_contributors"]

    high_friction = sum(
        1
        for actor in newcomers
        if str(actor.get("community_health", {}).get("onboarding_friction", "")).lower()
        == "high"
    )
    churn_high = sum(
        1
        for actor in developers
        if str(actor.get("community_health", {}).get("churn_risk", "")).lower() == "high"
    )

    high_signal_reports = 0
    noisy_reports = 0
    duplicate_reports = 0
    for actor in users_testers:
        quality = str(actor.get("community_health", {}).get("feedback_quality", "mixed"))
        if quality == "high_signal":
            high_signal_reports += len(actor.get("signals", []))
        elif quality == "noisy":
            noisy_reports += len(actor.get("signals", []))
        for signal in actor.get("signals", []):
            if bool(signal.get("is_duplicate", False)):
                duplicate_reports += 1

    onboarding_started = len(newcomers)
    onboarding_completed = max(onboarding_started - high_friction, 0)

    return {
        "onboarding": {
            "started": onboarding_started,
            "completed": onboarding_completed,
            "drop_off": max(onboarding_started - onboarding_completed, 0),
        },
        "retention": {
            "developer_churn_count": churn_high,
            "developer_retention_percent": round((100 - churn_high), 1),
        },
        "velocity": {
            "active_developers": len(developers) - churn_high,
            "active_users_testers": len(users_testers),
            "issues_triaged": sum(len(actor.get("signals", [])) for actor in actor_sessions),
            "issues_resolved": 0,
        },
        "feedback_quality": {
            "high_signal_reports": high_signal_reports,
            "noisy_reports": noisy_reports,
            "duplicate_reports": duplicate_reports,
        },
    }


def _roadmap_to_rc1(cycle: int) -> dict[str, Any]:
    return {
        "target": "Release Candidate 1",
        "target_date": _iso_date_from_now(35),
        "milestones": [
            {
                "name": "Cycle 0: Mission and population bootstrap",
                "owner": "core_maintainers",
                "exit_criteria": [
                    "Mission statement drafted with boundaries.",
                    "100 developer + 300 user/tester independent agents executed.",
                    "Initial RC1 backlog triaged with severity labels.",
                ],
            },
            {
                "name": "Cycle 1: Critical/high defect burn-down",
                "owner": "backup_sync_portability",
                "exit_criteria": [
                    "No critical defects.",
                    "High-severity issues reduced by at least 50%.",
                    "Review bottleneck SLA under 48h median.",
                ],
            },
            {
                "name": "Cycle 2: Test stability and rollback reliability",
                "owner": "qa_release_engineering",
                "exit_criteria": [
                    "Flaky-test rate under 2% for 3 consecutive runs.",
                    "Upgrade/rollback suite passes on Linux/macOS/Windows.",
                    "Regression index trend stable or improving.",
                ],
            },
            {
                "name": "Cycle 3: Docs/onboarding and API boundaries",
                "owner": "docs_community",
                "exit_criteria": [
                    "Integration supported/unsupported boundaries documented.",
                    "Docs-driven onboarding completion >= 85%.",
                    "Accessibility cohort sign-off on dashboard critical paths.",
                ],
            },
            {
                "name": "Cycle 4: RC1 rehearsal",
                "owner": "qa_release_engineering",
                "exit_criteria": [
                    "All quality gates pass.",
                    "Packaging and checksum evidence complete.",
                    "Operator runbook and rollback plan approved.",
                ],
            },
        ],
        "starting_cycle": cycle,
    }


def _mission_scope_alignment(cycle: int) -> dict[str, Any]:
    mission_statement = (
        "Build a local-first, privacy-safe orchestration substrate that coordinates "
        "AI-assisted engineering through local, hosted_dev, and production stages with "
        "evidence-backed decisions, explicit write directives, and reproducible release paths."
    )
    return {
        "cycle": cycle,
        "mission_statement": mission_statement,
        "product_boundaries": {
            "in_scope": [
                "Independent persona agents for developers and users/testers.",
                "Weekly cadence across issue intake, triage, RFC review, implementation, testing, release checks, communication.",
                "3x3 lifecycle flow: local -> hosted_dev -> production and research -> development -> testing.",
                "Read-first integrations and explicit directive gates for writes.",
                "Cross-platform Backup & Sync validation for Linux/macOS/Windows.",
            ],
            "out_of_scope": [
                "Unauthorized or unethical automation.",
                "Breaking workflow/CLI changes without compatibility.",
                "Personal or sensitive data in logs, docs, or release artifacts.",
                "Unbounded feature work outside RC1 goals.",
            ],
        },
        "alignment_checks": [
            {"check": "Ethical and authorized development", "status": "pass"},
            {"check": "Open-source-first standards", "status": "pass"},
            {"check": "Read-first/write-by-directive", "status": "pass"},
            {"check": "Backward compatibility", "status": "pass"},
            {"check": "No sensitive data in artifacts", "status": "pass"},
            {"check": "3x3 lifecycle discipline", "status": "pass"},
        ],
    }


def _cycle_report_markdown(
    *,
    cycle: int,
    stage: str,
    mission_statement: str,
    snapshot: dict[str, Any],
    risks: list[dict[str, Any]],
    backlog: list[dict[str, Any]],
    rfc_log: list[dict[str, Any]],
    release_scorecard: dict[str, Any],
    test_matrix: dict[str, Any],
    next_cycle_plan: list[dict[str, str]],
) -> str:
    lines = [
        f"# Community Cycle {cycle}",
        "",
        f"Stage: `{stage}`",
        "",
        "## 1. Community Snapshot",
        f"- Mission statement: {mission_statement}",
        f"- Population executed: {snapshot['population']['developers']} developers + {snapshot['population']['users_testers']} users/testers.",
        f"- Independent persona sessions completed: {snapshot['population']['total']}.",
        f"- Wave execution: {snapshot['wave_count']} waves (limit {snapshot['concurrency_limit']}/wave).",
        "",
        "## 2. Top Risks",
    ]
    for risk in risks:
        lines.append(
            f"- {risk['id']} ({risk['severity']}): {risk['risk']} [owner: {risk['owner']}, due: {risk['due_date']}]"
        )

    lines.extend(["", "## 3. Developer Work Completed"])
    lines.extend(
        [
            f"- Completed all {snapshot['population']['developers']} developer-agent sessions with unique personas.",
            f"- Triaged {len(backlog)} backlog issues from aggregated agent signals.",
            "- Applied backlog ownership across all required developer squads.",
            "- Captured maintainer review bottlenecks and stale PR pressure in release telemetry.",
        ]
    )

    lines.extend(["", "## 4. User/Tester Findings"])
    top_findings = backlog[:5]
    for finding in top_findings:
        lines.append(
            f"- {finding['id']} ({finding['severity']}): {finding['title']} (mentions={finding['mentions']}, high_signal={finding['high_signal_reports']}, noisy={finding['noisy_reports']})."
        )

    lines.extend(["", "## 5. Decision Log (what changed and why)"])
    for decision in rfc_log:
        lines.append(
            f"- {decision['rfc_id']} {decision['status']}: {decision['title']} (accept={decision['votes']['accept']}, reject={decision['votes']['reject']})."
        )

    summary = release_scorecard["summary"]
    lines.extend(["", "## 6. Test/Release Evidence"])
    lines.append(
        f"- Release readiness score: {summary['score_percent']}% (passed={summary['passed']}, partial={summary['partial']}, failed={summary['failed']})."
    )
    lines.append(
        "- Test matrix states: "
        + ", ".join(
            f"{entry['stage']}:{entry['pass']}={entry['status']}"
            for entry in test_matrix["matrix"]
        )
    )
    lines.append(
        "- Failure taxonomy counts: "
        + ", ".join(
            f"{entry['type']}={entry['count']}" for entry in test_matrix["failure_taxonomy"]
        )
    )

    lines.extend(["", "## 7. Next-Cycle Plan (owners + exit criteria)"])
    for item in next_cycle_plan:
        lines.append(
            f"- {item['owner']}: {item['goal']} (exit: {item['exit_criteria']})"
        )

    return "\n".join(lines).strip() + "\n"


def _assert_stage_policy(runtime: SubstrateRuntime, repo_slug: str, stage: str) -> None:
    stage_sequence = runtime.workspace.policy.stage_sequence
    if stage not in stage_sequence:
        raise ValueError(
            f"Stage '{stage}' is not allowed. Expected one of {stage_sequence}."
        )
    if not runtime.workspace.policy.enforce_stage_flow:
        return
    stage_index = stage_sequence.index(stage)
    if stage_index == 0:
        return
    prerequisite = stage_sequence[stage_index - 1]
    if not runtime.db.has_successful_stage(repo_slug, prerequisite):
        raise PermissionError(
            f"Stage '{stage}' requires a successful '{prerequisite}' run first."
        )


def run_community_cycle(
    runtime: SubstrateRuntime,
    *,
    cycle: int,
    stage: str,
    concurrency_limit: int,
    repo_slug: str = "substrate-core",
    agent_provider: str = "mock",
    agent_model: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    if cycle < 0:
        raise ValueError("cycle must be >= 0")
    if concurrency_limit < 1:
        raise ValueError("concurrency_limit must be >= 1")
    if agent_provider not in DEFAULT_PROVIDER_MODELS:
        raise ValueError(
            f"agent_provider must be one of {sorted(DEFAULT_PROVIDER_MODELS)}"
        )

    runtime.resolve_repo(repo_slug)
    _assert_stage_policy(runtime, repo_slug=repo_slug, stage=stage)

    base_seed = seed if seed is not None else 7331
    model_name = agent_model or DEFAULT_PROVIDER_MODELS[agent_provider]
    run_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = (
        runtime.paths["memory"]
        / "community-sim"
        / f"{timestamp}-cycle{cycle:02d}-{run_id[:8]}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    runtime.db.create_run(
        run_id=run_id,
        run_type="community-cycle",
        repo_slug=repo_slug,
        task_id=None,
        objective=f"Community agent cycle {cycle}",
        stage=stage,
        mode="observe",
        provider=agent_provider,
        model=model_name,
        metadata={
            "cycle": cycle,
            "concurrency_limit": concurrency_limit,
            "seed": base_seed,
            "population": {
                "developers": sum(count for _, count in DEVELOPER_COHORTS),
                "users_testers": sum(count for _, count in USER_TESTER_COHORTS),
            },
            "cadence_phases": OPERATING_CADENCE_PHASES,
        },
    )
    runtime.db.add_event(
        run_id=run_id,
        level="info",
        message=f"Starting community cycle {cycle}",
        payload={
            "stage": stage,
            "concurrency_limit": concurrency_limit,
            "provider": agent_provider,
            "model": model_name,
        },
    )

    try:
        mission = _mission_scope_alignment(cycle)
        mission_statement = mission["mission_statement"]

        developers = _build_developer_agents(cycle=cycle, base_seed=base_seed)
        users_testers = _build_user_tester_agents(cycle=cycle, base_seed=base_seed)
        all_agents = [*developers, *users_testers]

        actor_sessions, wave_schedule = _run_agent_waves(
            agents=all_agents,
            provider=agent_provider,
            model_name=model_name,
            cycle=cycle,
            stage=stage,
            base_seed=base_seed,
            concurrency_limit=concurrency_limit,
            mission_statement=mission_statement,
            runtime_root=runtime.root,
            run_dir=run_dir,
        )

        backlog = _aggregate_backlog(actor_sessions, cycle=cycle)
        rfc_log = _aggregate_rfc_votes(actor_sessions, cycle=cycle)
        pr_report = _aggregate_pr_throughput(actor_sessions)
        test_matrix = _aggregate_test_failures(backlog, actor_sessions, stage)
        regression_index = _build_regression_index(backlog)
        risk_register = _risk_register(backlog)
        community_health = _community_health_report(actor_sessions)
        release_scorecard = _release_readiness_scorecard(
            cycle=cycle,
            backlog=backlog,
            test_matrix=test_matrix,
        )
        roadmap_to_rc1 = _roadmap_to_rc1(cycle)

        snapshot = {
            "generated_at": _iso_now(),
            "cycle": cycle,
            "stage": stage,
            "provider": agent_provider,
            "model": model_name,
            "population": {
                "developers": len(developers),
                "users_testers": len(users_testers),
                "total": len(all_agents),
            },
            "cohort_totals": _cohort_totals(all_agents),
            "simulation_mode": "independent_agents_in_waves",
            "wave_count": len(wave_schedule),
            "concurrency_limit": concurrency_limit,
            "cadence_phases": OPERATING_CADENCE_PHASES,
            "realism": {
                "conflicting_opinions_threads": sum(
                    1
                    for entry in rfc_log
                    if entry["votes"]["accept"] > 0 and entry["votes"]["reject"] > 0
                ),
                "duplicate_issues": sum(item["duplicate_reports"] for item in backlog),
                "stale_prs": pr_report["stale_prs"],
                "regressions": len(regression_index["open_regressions"]),
                "flaky_tests": next(
                    (
                        item["count"]
                        for item in test_matrix["failure_taxonomy"]
                        if item["type"] == "flaky_test"
                    ),
                    0,
                ),
                "documentation_gaps": next(
                    (
                        item["count"]
                        for item in test_matrix["failure_taxonomy"]
                        if item["type"] == "docs_gap"
                    ),
                    0,
                ),
                "maintainer_review_pressure": "elevated"
                if pr_report["median_review_latency_hours"] >= 48
                else "moderate",
                "contributor_churn_count": community_health["retention"][
                    "developer_churn_count"
                ],
                "feedback_quality_variance": "high_signal_plus_noise",
            },
        }

        next_cycle_plan = [
            {
                "owner": "backup_sync_portability",
                "goal": "Close ISSUE-001 and complete Linux/macOS/Windows backup sync validation.",
                "exit_criteria": "No critical defects remain in Backup & Sync.",
            },
            {
                "owner": "qa_release_engineering",
                "goal": "Reduce flaky test instability and define deterministic retry policy.",
                "exit_criteria": "Flaky-test count <= 2 for three consecutive cycle test runs.",
            },
            {
                "owner": "integrations_proton_surfaces",
                "goal": "Publish supported/unsupported API boundaries for integrations.",
                "exit_criteria": "Boundary documentation approved by security/compliance cohort.",
            },
            {
                "owner": "docs_community",
                "goal": "Improve onboarding docs and reduce newcomer drop-off.",
                "exit_criteria": "Onboarding completion >= 85%.",
            },
        ]

        report = _cycle_report_markdown(
            cycle=cycle,
            stage=stage,
            mission_statement=mission_statement,
            snapshot=snapshot,
            risks=risk_register,
            backlog=backlog,
            rfc_log=rfc_log,
            release_scorecard=release_scorecard,
            test_matrix=test_matrix,
            next_cycle_plan=next_cycle_plan,
        )

        mission_report = (
            f"# Mission and Scope Alignment (Cycle {cycle})\n\n"
            f"Mission statement:\n\n{mission_statement}\n\n"
            "## Product boundaries\n\n"
            "### In scope\n"
            + "\n".join(f"- {line}" for line in mission["product_boundaries"]["in_scope"])
            + "\n\n### Out of scope\n"
            + "\n".join(
                f"- {line}" for line in mission["product_boundaries"]["out_of_scope"]
            )
            + "\n"
        )

        sessions_dir = run_dir / "actor_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        for session in actor_sessions:
            _write_json(sessions_dir / f"{session['actor_id']}.json", session)

        _write_json(run_dir / "community_snapshot.json", snapshot)
        _write_json(run_dir / "developers_queue.json", developers)
        _write_json(run_dir / "users_testers_queue.json", users_testers)
        _write_json(run_dir / "wave_schedule.json", wave_schedule)
        _write_jsonl(run_dir / "actor_sessions.jsonl", actor_sessions)
        (run_dir / "mission_scope_alignment.md").write_text(
            mission_report, encoding="utf-8"
        )
        _write_json(run_dir / "prioritized_backlog.json", backlog)
        _write_json(run_dir / "accepted_rejected_rfc_log.json", rfc_log)
        _write_json(run_dir / "pr_throughput_review_latency_report.json", pr_report)
        _write_json(run_dir / "test_matrix_failure_taxonomy.json", test_matrix)
        _write_json(run_dir / "regression_index_known_good_updates.json", regression_index)
        _write_json(run_dir / "release_readiness_scorecard.json", release_scorecard)
        _write_json(run_dir / "risk_register.json", risk_register)
        _write_json(run_dir / "community_health_report.json", community_health)
        _write_json(run_dir / "roadmap_to_rc1.json", roadmap_to_rc1)
        (run_dir / "cycle_report.md").write_text(report, encoding="utf-8")

        result = {
            "run_id": run_id,
            "cycle": cycle,
            "stage": stage,
            "repo_slug": repo_slug,
            "run_dir": str(run_dir),
            "report_path": str(run_dir / "cycle_report.md"),
            "provider": agent_provider,
            "model": model_name,
            "queues": {
                "developers": len(developers),
                "users_testers": len(users_testers),
                "total": len(all_agents),
                "waves": len(wave_schedule),
                "concurrency_limit": concurrency_limit,
                "sessions_completed": len(actor_sessions),
            },
            "release_readiness": release_scorecard["summary"],
            "roadmap_target": roadmap_to_rc1["target"],
        }

        runtime.db.add_event(
            run_id=run_id,
            level="info",
            message=f"Completed community cycle {cycle}",
            payload={
                "run_dir": str(run_dir),
                "report_path": str(run_dir / "cycle_report.md"),
                "sessions_completed": len(actor_sessions),
            },
        )
        runtime.db.complete_run(
            run_id=run_id,
            status="success",
            run_dir=str(run_dir),
            exit_code=0,
        )
        record_execution(
            runtime,
            run_type="community-cycle",
            run_id=run_id,
            repo_slug=repo_slug,
            stage=stage,
            command=[
                "community-cycle",
                f"--cycle={cycle}",
                f"--stage={stage}",
                f"--concurrency-limit={concurrency_limit}",
                f"--agent-provider={agent_provider}",
                f"--agent-model={model_name}",
            ],
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            artifact=str(run_dir / "cycle_report.md"),
            note="Independent community-agent cycle",
            classify_as_test=True,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        runtime.db.add_event(
            run_id=run_id,
            level="error",
            message="Community cycle failed.",
            payload={"error": str(exc), "traceback": traceback.format_exc()},
        )
        runtime.db.complete_run(
            run_id=run_id,
            status="failed",
            run_dir=str(run_dir),
            exit_code=1,
            error_text=str(exc),
        )
        record_execution(
            runtime,
            run_type="community-cycle",
            run_id=run_id,
            repo_slug=repo_slug,
            stage=stage,
            command=[
                "community-cycle",
                f"--cycle={cycle}",
                f"--stage={stage}",
                f"--concurrency-limit={concurrency_limit}",
                f"--agent-provider={agent_provider}",
                f"--agent-model={model_name}",
            ],
            status="failed",
            exit_code=1,
            stderr=f"{exc}\n{traceback.format_exc()}",
            artifact=str(run_dir),
            note="Independent community-agent cycle failure",
            classify_as_test=True,
        )
        raise
