from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .agents import (
    AgentConfigError,
    agent_status_payload,
    load_agents_config,
    run_agent,
    run_agent_cycle,
)
from .cache_store import CacheStore
from .community import run_community_cycle
from .config_sync import (
    CONFIG_SYNC_TARGET_ENVS,
    backup_config_sync,
    deploy_config_sync,
    plan_config_sync,
    scan_config_sync,
)
from .ducky import DuckyPayloadEngine
from .integrations import (
    connect_integration,
    disconnect_integration,
    integrations_payload,
    set_integration_mode,
)
from .learning import learning_payload, record_execution, record_resolution_note
from .models import OPENCLAW_ALLOWED_DATA_CLASSES
from .orchestrator import Orchestrator
from .prefill_proxy import (
    DEFAULT_HOST as DEFAULT_PROXY_HOST,
)
from .prefill_proxy import (
    DEFAULT_PORT as DEFAULT_PROXY_PORT,
)
from .prefill_proxy import (
    serve_forever,
    start_daemon,
    status_daemon,
    stop_daemon,
)
from .providers import SUPPORTED_PROVIDERS
from .registry import SubstrateRuntime
from .render import (
    render_catalog_payload,
    render_dispatch,
    render_telemetry_payload,
)
from .render_engines.base import RenderRequest, RenderUnavailable
from .research import refresh_upstreams
from .standards import standards_payload
from .swarm_control import (
    DEFAULT_BASE_URL,
    deploy_production,
    emit_work_items,
    run_iteration_loop,
    run_triage_from_simulation,
    run_user_simulation,
    smoke_tests,
    swarm_status,
)
from .tooling import ensure_tool_profile, tooling_snapshot

ALLOWED_CHAIN_PROVIDERS = set(SUPPORTED_PROVIDERS)
ALLOWED_AGENT_PROVIDERS = set(SUPPORTED_PROVIDERS)
ALLOWED_STAGES = {"local", "hosted_dev", "production"}
ALLOWED_MODES = {"observe", "mutate"}
ALLOWED_OPENCLAW_DATA_CLASSES = set(OPENCLAW_ALLOWED_DATA_CLASSES)
def _port_value(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= value <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return value


def _existing_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.exists():
        raise argparse.ArgumentTypeError(f"workspace root does not exist: {root}")
    if not root.is_dir():
        raise argparse.ArgumentTypeError(f"workspace root is not a directory: {root}")
    return root


def _validate_relative_yaml(root: Path, raw_path: str) -> str:
    candidate = Path(raw_path.strip())
    if candidate.is_absolute():
        raise argparse.ArgumentTypeError("path must be workspace-relative")
    if any(part == ".." for part in candidate.parts):
        raise argparse.ArgumentTypeError("path may not traverse parent directories")
    if candidate.suffix.lower() not in {".yaml", ".yml"}:
        raise argparse.ArgumentTypeError("path must point to a YAML file")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise argparse.ArgumentTypeError("path must stay within the workspace")
    if not resolved.exists():
        raise argparse.ArgumentTypeError(f"path does not exist: {candidate.as_posix()}")
    return candidate.as_posix()


def _validate_context_files(root: Path, raw_values: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_value in raw_values:
        candidate = Path(raw_value.strip())
        if candidate.is_absolute():
            raise argparse.ArgumentTypeError("context files must be workspace-relative")
        if any(part == ".." for part in candidate.parts):
            raise argparse.ArgumentTypeError(
                "context files may not traverse parent directories"
            )
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            raise argparse.ArgumentTypeError(
                "context files must stay within the workspace"
            )
        if not resolved.exists():
            raise argparse.ArgumentTypeError(
                f"context file does not exist: {raw_value}"
            )
        normalized.append(candidate.as_posix())
    return normalized


def _detect_access_tools() -> dict[str, str | None]:
    return {
        "cloudflared": shutil.which("cloudflared"),
        "tailscale": shutil.which("tailscale"),
        "ssh": shutil.which("ssh"),
    }


def _default_utc_date() -> str:
    return datetime.now(UTC).date().isoformat()


def _build_discount_swarm_plan(
    *,
    repo_slug: str,
    merchant: str,
    as_of_date: str,
    lookback_days: int,
    provider: str,
    model: str,
    stage: str,
) -> dict[str, object]:
    quoted_repo = shlex.quote(repo_slug)
    quoted_provider = shlex.quote(provider)
    quoted_model = shlex.quote(model)
    quoted_stage = shlex.quote(stage)
    date_window_hint = (
        f"Prioritize evidence dated between {as_of_date} and "
        f"{lookback_days} days before {as_of_date}."
    )
    objective_templates = [
        (
            "official-sources",
            (
                f"Find active {merchant} discounts from official sources. "
                "Capture code, terms, expiration date, and restrictions. "
                f"{date_window_hint}"
            ),
        ),
        (
            "forum-hunt",
            (
                f"Search public forums (Reddit, Slickdeals, deal communities) for {merchant} "
                "discount codes with user confirmation. Extract only codes with at least "
                "one explicit 'worked' confirmation and include evidence links plus timestamps. "
                f"{date_window_hint}"
            ),
        ),
        (
            "aggregator-cross-check",
            (
                f"Collect {merchant} discount claims from public coupon aggregators and "
                "cross-check overlap with forum evidence. Mark confidence high/medium/low based "
                "on evidence recency and duplicate confirmations. "
                f"{date_window_hint}"
            ),
        ),
        (
            "random-file-discovery",
            (
                f"Search public paste/file snippets mentioning {merchant} promo or coupon codes. "
                "Treat snippets as untrusted until corroborated by forum or official evidence. "
                f"{date_window_hint}"
            ),
        ),
        (
            "verification-pass",
            (
                f"Merge evidence from previous agents and output a verified list of likely-working "
                f"{merchant} codes as-of {as_of_date}. Require at least two independent public "
                "sources for 'verified' classification; otherwise classify as 'unverified'."
            ),
        ),
    ]

    commands: list[dict[str, str]] = []
    shell_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Generated discount research swarm commands.",
        "# Run in separate terminals or with GNU parallel.",
        "",
    ]
    for label, objective in objective_templates:
        quoted_objective = shlex.quote(objective)
        cmd = (
            "uv run python scripts/substrate_cli.py run-chain "
            f"--repo {quoted_repo} "
            f"--objective {quoted_objective} "
            "--chain chains/local-agent-chain.yaml "
            f"--provider {quoted_provider} "
            f"--model {quoted_model} "
            f"--stage {quoted_stage} "
            "--dry-run"
        )
        commands.append({"agent": label, "command": cmd, "objective": objective})
        shell_lines.append(f"# Agent: {label}")
        shell_lines.append(cmd)
        shell_lines.append("")

    shell_lines.extend(
        [
            "# Recommended follow-up:",
            "# 1) Remove --dry-run after reviewing planned prompts.",
            "# 2) Re-run the verification-pass objective once evidence files are collected.",
        ]
    )
    return {
        "merchant": merchant,
        "as_of_date": as_of_date,
        "lookback_days": lookback_days,
        "provider": provider,
        "model": model,
        "stage": stage,
        "commands": commands,
        "swarm_script": "\n".join(shell_lines),
    }


def _pinch_report(port: int, repo_slug: str | None = None) -> dict[str, object]:
    base_url = f"http://127.0.0.1:{port}"
    tools = _detect_access_tools()
    access = [
        {
            "tool": "cloudflared",
            "available": bool(tools["cloudflared"]),
            "command": f"cloudflared tunnel --url {base_url}",
            "notes": "Quick tunnel for local testing.",
        },
        {
            "tool": "tailscale",
            "available": bool(tools["tailscale"]),
            "command": f"tailscale serve localhost:{port}",
            "alternate": "tailscale funnel (if enabled in your tailnet policy)",
            "notes": "Tailnet access first, public funnel only if you need it.",
        },
        {
            "tool": "ssh",
            "available": bool(tools["ssh"]),
            "command": f"ssh -N -R {port}:127.0.0.1:{port} user@remote-host",
            "notes": "Reverse tunnel when you have a reachable bastion host.",
        },
    ]
    diagnostics = [
        {"label": "health", "command": f"curl -fsS {base_url}/healthz"},
        {"label": "runs", "command": "uv run python scripts/substrate_cli.py runs"},
        {"label": "scan", "command": "uv run python scripts/substrate_cli.py scan"},
    ]
    if repo_slug:
        diagnostics.append(
            {
                "label": "repo dry run",
                "command": (
                    "uv run python scripts/substrate_cli.py run-chain "
                    f'--repo {repo_slug} --objective "Recovery check" --stage local --dry-run'
                ),
            }
        )
    return {
        "base_url": base_url,
        "tools": tools,
        "access": access,
        "diagnostics": diagnostics,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="substrate",
        description="Portable orchestration control plane for multi-repo AI workflows.",
    )
    parser.add_argument(
        "--root",
        type=_existing_root,
        help="Workspace root (defaults to auto-discovery from cwd).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("env", help="Print detected environment profile.")
    subparsers.add_parser(
        "scan", help="Scan repositories and persist status snapshots."
    )
    subparsers.add_parser("runs", help="List recent runs.")
    subparsers.add_parser("sources-list", help="List source projects from the DB.")
    subparsers.add_parser(
        "sources-refresh", help="Refresh source project metadata from upstream APIs."
    )
    standards = subparsers.add_parser(
        "standards",
        help="Show trusted community standards catalog with lifecycle guidance.",
    )
    standards.add_argument("--track", help="Optional track id filter.")

    subparsers.add_parser(
        "learning",
        help="Show local known-good paths, test ledger, and recurring error index.",
    )

    config_sync_scan = subparsers.add_parser(
        "config-sync-scan",
        help="Discover current user config files and refresh the local backup/sync index.",
    )
    config_sync_scan.add_argument(
        "--path",
        action="append",
        default=[],
        help="Optional source path filter (repeatable).",
    )

    config_sync_backup = subparsers.add_parser(
        "config-sync-backup",
        help="Back up discovered config files into the workspace.",
    )
    config_sync_backup.add_argument(
        "--path",
        action="append",
        default=[],
        help="Optional source path filter (repeatable).",
    )
    config_sync_backup.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Optional profile id filter (repeatable).",
    )

    config_sync_plan = subparsers.add_parser(
        "config-sync-plan",
        help="Generate a backup/sync deployment plan for a target environment.",
    )
    config_sync_plan.add_argument(
        "--target",
        choices=sorted(CONFIG_SYNC_TARGET_ENVS),
        help="Target environment (defaults to the current platform).",
    )
    config_sync_plan.add_argument(
        "--path",
        action="append",
        default=[],
        help="Optional source path filter (repeatable).",
    )
    config_sync_plan.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Optional profile id filter (repeatable).",
    )

    config_sync_deploy = subparsers.add_parser(
        "config-sync-deploy",
        help="Deploy backup/sync config set to a target environment.",
    )
    config_sync_deploy.add_argument(
        "--target",
        choices=sorted(CONFIG_SYNC_TARGET_ENVS),
        help="Target environment (defaults to the current platform).",
    )
    config_sync_deploy.add_argument(
        "--path",
        action="append",
        default=[],
        help="Optional source path filter (repeatable).",
    )
    config_sync_deploy.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Optional profile id filter (repeatable).",
    )
    config_sync_deploy.add_argument(
        "--destination",
        help="Optional destination root for the deployment bundle or filesystem copy.",
    )
    config_sync_deploy.add_argument(
        "--apply",
        action="store_true",
        help="Apply the deployment plan. Required for any writes.",
    )
    config_sync_deploy.add_argument(
        "--directive",
        default="",
        help="Explicit write directive. Required with --apply.",
    )

    # Legacy aliases retained for backward compatibility.
    dotfiles_scan = subparsers.add_parser(
        "dotfiles-scan",
        help="Alias for config-sync-scan.",
    )
    dotfiles_scan.add_argument("--path", action="append", default=[])
    dotfiles_backup = subparsers.add_parser(
        "dotfiles-backup",
        help="Alias for config-sync-backup.",
    )
    dotfiles_backup.add_argument("--path", action="append", default=[])
    dotfiles_backup.add_argument("--profile", action="append", default=[])
    dotfiles_plan = subparsers.add_parser(
        "dotfiles-plan",
        help="Alias for config-sync-plan.",
    )
    dotfiles_plan.add_argument("--target", choices=sorted(CONFIG_SYNC_TARGET_ENVS))
    dotfiles_plan.add_argument("--path", action="append", default=[])
    dotfiles_plan.add_argument("--profile", action="append", default=[])
    dotfiles_deploy = subparsers.add_parser(
        "dotfiles-deploy",
        help="Alias for config-sync-deploy.",
    )
    dotfiles_deploy.add_argument("--target", choices=sorted(CONFIG_SYNC_TARGET_ENVS))
    dotfiles_deploy.add_argument("--path", action="append", default=[])
    dotfiles_deploy.add_argument("--profile", action="append", default=[])
    dotfiles_deploy.add_argument("--destination")
    dotfiles_deploy.add_argument("--apply", action="store_true")
    dotfiles_deploy.add_argument("--directive", default="")

    subparsers.add_parser(
        "integrations",
        help="Show integration catalog and current connection states.",
    )

    integration_connect = subparsers.add_parser(
        "integration-connect",
        help="Create or update an integration connection (default read mode).",
    )
    integration_connect.add_argument("--service", required=True, help="Service id.")
    integration_connect.add_argument("--auth-method", default="")
    integration_connect.add_argument("--token-ref", default="")
    integration_connect.add_argument("--scopes", default="")
    integration_connect.add_argument(
        "--mode", choices=["read", "write"], default="read"
    )
    integration_connect.add_argument("--write-directive", default="")

    integration_mode = subparsers.add_parser(
        "integration-mode",
        help="Change integration mode (write requires explicit directive).",
    )
    integration_mode.add_argument("--service", required=True, help="Service id.")
    integration_mode.add_argument("--mode", choices=["read", "write"], required=True)
    integration_mode.add_argument("--write-directive", default="")

    integration_disconnect = subparsers.add_parser(
        "integration-disconnect",
        help="Disconnect a service integration.",
    )
    integration_disconnect.add_argument("--service", required=True, help="Service id.")

    learning_resolve = subparsers.add_parser(
        "learning-resolve",
        help="Attach a resolution note to a recurring error signature.",
    )
    learning_resolve.add_argument(
        "--signature", required=True, help="Error signature id."
    )
    learning_resolve.add_argument(
        "--resolution", required=True, help="Resolution summary."
    )
    learning_resolve.add_argument("--path", help="Optional path or command reference.")

    deps_status = subparsers.add_parser(
        "deps-status",
        help="Show optional tool profile status and install plans.",
    )
    deps_status.add_argument("--profile", help="Optional profile id filter.")

    deps_ensure = subparsers.add_parser(
        "deps-ensure",
        help="Assemble optional tooling from internet sources on demand.",
    )
    deps_ensure.add_argument(
        "--profile", required=True, help="Profile id from tool_profiles.yaml."
    )
    deps_ensure.add_argument(
        "--apply",
        action="store_true",
        help="Execute planned install commands. Without this flag, only plans are printed.",
    )

    record_test = subparsers.add_parser(
        "record-test",
        help="Run a local test command and persist result in the learning index.",
    )
    record_test.add_argument("--name", required=True, help="Test name.")
    record_test.add_argument(
        "--cmd",
        dest="test_command",
        required=True,
        help="Shell command to execute.",
    )
    record_test.add_argument("--repo", help="Optional repository slug.")
    record_test.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="local",
    )
    record_test.add_argument(
        "--workdir",
        default=".",
        help="Working directory for command execution (workspace-relative or absolute).",
    )

    payloads = subparsers.add_parser(
        "payloads",
        help="List ducky-style payload workflows.",
    )
    payloads.add_argument(
        "--repo", help="Optional repository slug for availability checks."
    )

    run_payload = subparsers.add_parser(
        "run-payload",
        help="Run a ducky-style payload workflow.",
    )
    run_payload.add_argument("--payload", required=True, help="Payload id.")
    run_payload.add_argument("--repo", help="Optional repository slug.")
    run_payload.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="local",
    )
    run_payload.add_argument("--allow-stage-skip", action="store_true")
    run_payload.add_argument("--port", type=_port_value, default=8090)
    run_payload.add_argument(
        "--wait",
        action="store_true",
        help="Wait until payload job completes and print final state.",
    )
    run_payload.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds when --wait is set.",
    )

    def _register_community_cycle_parser(command_name: str) -> argparse.ArgumentParser:
        parser_ref = subparsers.add_parser(
            command_name,
            help=(
                "Run a weekly open-source community cycle with independent "
                "persona agents (100 developer + 300 user/tester sessions)."
            ),
        )
        parser_ref.add_argument(
            "--cycle",
            type=int,
            default=0,
            help="Cycle number (starts at 0).",
        )
        parser_ref.add_argument(
            "--repo",
            default="substrate-core",
            help="Repository slug used for stage-policy checks.",
        )
        parser_ref.add_argument(
            "--stage",
            choices=sorted(ALLOWED_STAGES),
            default="local",
        )
        parser_ref.add_argument(
            "--concurrency-limit",
            type=int,
            default=40,
            help="Max number of live agents per wave.",
        )
        parser_ref.add_argument(
            "--agent-provider",
            choices=sorted(ALLOWED_AGENT_PROVIDERS),
            default="mock",
            help="Provider used to run independent agent sessions.",
        )
        parser_ref.add_argument(
            "--agent-model",
            default="",
            help="Optional provider model override.",
        )
        parser_ref.add_argument(
            "--seed",
            type=int,
            help="Optional deterministic seed for persona generation.",
        )
        parser_ref.add_argument(
            "--population-scale",
            type=float,
            default=1.0,
            help="Scale agent population size up/down while preserving cohort mix.",
        )
        return parser_ref

    _register_community_cycle_parser("community-cycle")
    _register_community_cycle_parser("spawn-agent-workloads")
    community_cycle = subparsers.add_parser(
        "spawn-agent-workloads-now",
        help="Alias for spawn-agent-workloads for fast operator use.",
    )
    community_cycle.add_argument(
        "--cycle",
        type=int,
        default=0,
        help="Cycle number (starts at 0).",
    )
    community_cycle.add_argument(
        "--repo",
        default="substrate-core",
        help="Repository slug used for stage-policy checks.",
    )
    community_cycle.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="local",
    )
    community_cycle.add_argument(
        "--concurrency-limit",
        type=int,
        default=40,
        help="Max number of live agents per wave.",
    )
    community_cycle.add_argument(
        "--agent-provider",
        choices=sorted(ALLOWED_AGENT_PROVIDERS),
        default="mock",
        help="Provider used to run independent agent sessions.",
    )
    community_cycle.add_argument(
        "--agent-model",
        default="",
        help="Optional provider model override.",
    )
    community_cycle.add_argument(
        "--seed",
        type=int,
        help="Optional deterministic seed for persona generation.",
    )
    community_cycle.add_argument(
        "--population-scale",
        type=float,
        default=1.0,
        help="Scale agent population size up/down while preserving cohort mix.",
    )

    run_chain = subparsers.add_parser("run-chain", help="Run chain orchestration.")
    run_chain.add_argument("--repo", required=True, help="Repository slug.")
    run_chain.add_argument("--objective", required=True, help="Run objective.")
    run_chain.add_argument(
        "--chain",
        default="chains/local-agent-chain.yaml",
        help="Chain config path.",
    )
    run_chain.add_argument(
        "--provider", default="mock", choices=sorted(ALLOWED_CHAIN_PROVIDERS)
    )
    run_chain.add_argument("--model", default="mock-model")
    run_chain.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="local",
    )
    run_chain.add_argument("--mode", choices=sorted(ALLOWED_MODES), default="observe")
    run_chain.add_argument("--dry-run", action="store_true")
    run_chain.add_argument("--allow-mutations", action="store_true")
    run_chain.add_argument("--allow-stage-skip", action="store_true")
    run_chain.add_argument(
        "--context-file",
        action="append",
        default=[],
        help="Additional context files.",
    )
    run_chain.add_argument(
        "--openclaw-manual-trigger",
        action="store_true",
        help=(
            "Manually request optional OpenClaw internal research-assist side-lane. "
            "Default is disabled."
        ),
    )
    run_chain.add_argument(
        "--openclaw-data-class",
        choices=sorted(ALLOWED_OPENCLAW_DATA_CLASSES),
        default="synthetic",
        help=(
            "Declared data classification for OpenClaw side-lane vetting. "
            "Only policy-allowed classes are accepted at runtime."
        ),
    )
    run_chain.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable the local AI-call cache for this run.",
    )

    discount_swarm = subparsers.add_parser(
        "discount-swarm",
        help=(
            "Generate a multi-agent internet research swarm plan for finding and "
            "verifying discount codes."
        ),
    )
    discount_swarm.add_argument("--repo", required=True, help="Repository slug.")
    discount_swarm.add_argument(
        "--merchant",
        required=True,
        help="Merchant or product name to target.",
    )
    discount_swarm.add_argument(
        "--as-of-date",
        default=_default_utc_date(),
        help="Verification anchor date in YYYY-MM-DD format (default: today UTC).",
    )
    discount_swarm.add_argument(
        "--lookback-days",
        type=int,
        default=14,
        help="Recency window for candidate evidence.",
    )
    discount_swarm.add_argument(
        "--provider",
        default="local",
        choices=sorted(ALLOWED_CHAIN_PROVIDERS),
    )
    discount_swarm.add_argument("--model", default="roo-router")
    discount_swarm.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="local",
    )

    run_task = subparsers.add_parser("run-task", help="Run a repo task command.")
    run_task.add_argument("--repo", required=True, help="Repository slug.")
    run_task.add_argument("--task", required=True, help="Task id from workspace.yaml.")
    run_task.add_argument(
        "--stage",
        choices=sorted(ALLOWED_STAGES),
        default="local",
    )
    run_task.add_argument("--mode", choices=sorted(ALLOWED_MODES), default="observe")
    run_task.add_argument("--allow-mutations", action="store_true")
    run_task.add_argument("--allow-stage-skip", action="store_true")

    serve = subparsers.add_parser("serve", help="Run the ops panel web server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=_port_value, default=8090)
    serve.add_argument("--reload", action="store_true")

    pinch = subparsers.add_parser(
        "pinch",
        help="Print remote-access and recovery hints for pinch-mode troubleshooting.",
    )
    pinch.add_argument("--port", type=_port_value, default=8090)
    pinch.add_argument(
        "--repo", help="Optional repository slug for repo-specific recovery hints."
    )

    cache_status = subparsers.add_parser(
        "cache-status", help="Show local AI-call and task-cache statistics."
    )
    cache_status.add_argument(
        "--kind", help="Filter entries by cache kind (e.g., ai_call, subtask, plan)."
    )
    cache_status.add_argument(
        "--limit", type=int, default=50, help="Maximum entries to list."
    )

    cache_clear = subparsers.add_parser(
        "cache-clear", help="Clear local cache entries by kind or tags."
    )
    cache_clear.add_argument(
        "--kind", help="Remove entries of this kind."
    )
    cache_clear.add_argument(
        "--tag", action="append", default=[], help="Remove entries with this tag."
    )
    cache_clear.add_argument(
        "--older-than-days", type=int, help="Remove entries older than N days."
    )

    cache_prune = subparsers.add_parser(
        "cache-prune", help="Prune expired and old cache entries."
    )
    cache_prune.add_argument(
        "--max-age-days", type=int, default=30, help="Remove entries older than N days."
    )
    cache_prune.add_argument(
        "--max-size-mb", type=float, help="Cap total cache size in MiB."
    )

    agent_cycle = subparsers.add_parser(
        "agent-cycle",
        help="Evaluate agents.yaml cadence and run every due agent sequentially.",
    )
    agent_cycle.add_argument(
        "--agent",
        action="append",
        default=[],
        help="Limit the cycle to specific agent id(s) (repeatable).",
    )
    agent_cycle.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which agents are due without executing them.",
    )
    agent_cycle.add_argument(
        "--directive",
        default="",
        help="Optional explicit human directive passed to Tier 2-gated actions.",
    )

    agent_run = subparsers.add_parser(
        "agent-run", help="Run a single agent selected by role and repository."
    )
    agent_run.add_argument("--role", required=True, help="Agent role from agents.yaml.")
    agent_run.add_argument("--repo", required=True, help="Repository slug.")
    agent_run.add_argument(
        "--directive",
        default="",
        help="Optional explicit human directive passed to Tier 2-gated actions.",
    )
    agent_run.add_argument(
        "--force",
        action="store_true",
        help="Bypass the cadence idempotency window for this run.",
    )

    subparsers.add_parser(
        "agent-status",
        help="Show configured agents, last run state, and next due times.",
    )

    prefill_proxy = subparsers.add_parser(
        "prefill-proxy",
        help="Local rewrite proxy that fixes Anthropic 'assistant message "
        "prefill' 400s on the Kilo CLI / Kilo Gateway / OpenRouter path.",
    )
    prefill_proxy_sub = prefill_proxy.add_subparsers(dest="prefill_proxy_command")

    prefill_proxy_start = prefill_proxy_sub.add_parser(
        "start",
        help="Start the proxy (foreground, or detached with --daemon).",
    )
    prefill_proxy_start.add_argument("--host", default=DEFAULT_PROXY_HOST)
    prefill_proxy_start.add_argument("--port", type=_port_value, default=DEFAULT_PROXY_PORT)
    prefill_proxy_start.add_argument(
        "--mode",
        choices=("strip", "append"),
        default="strip",
        help="Fix strategy: strip trailing assistant messages (default) or "
        "append a placeholder user message.",
    )
    prefill_proxy_start.add_argument(
        "--daemon",
        action="store_true",
        help="Run detached in the background; managed via a pid file.",
    )

    prefill_proxy_sub.add_parser("stop", help="Stop a daemonized proxy.")
    prefill_proxy_sub.add_parser("status", help="Show proxy status and stats.")

    subparsers.add_parser(
        "storage-status",
        help="Report filesystem facts, recommended Btrfs plan, and compatibility.",
    )

    subparsers.add_parser(
        "storage-validate",
        help="Validate Btrfs recommendations against the tooling stack.",
    )

    capsule = subparsers.add_parser(
        "capsule",
        help="Probe and plan the portable OpenClaw/Substrate Gateway Capsule.",
    )
    capsule_sub = capsule.add_subparsers(dest="capsule_command", required=True)
    capsule_sub.add_parser(
        "probe",
        help="Inspect prerequisites, ports, state paths, and versions without mutation.",
    )
    capsule_sub.add_parser(
        "plan",
        help="Generate a staged, non-mutating disposable-capsule plan.",
    )
    capsule_manifest = capsule_sub.add_parser(
        "manifest",
        help="Generate a release manifest (stdout unless --output is supplied).",
    )
    capsule_manifest.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Parent directories are created.",
    )

    storage_maintenance = subparsers.add_parser(
        "storage-maintenance",
        help="Run dedup + defrag maintenance (dry-run by default; --apply to run).",
    )
    storage_maintenance.add_argument(
        "--apply",
        action="store_true",
        help="Execute the maintenance commands. Explicit directive required.",
    )
    storage_maintenance.add_argument(
        "--no-dedup",
        action="store_true",
        help="Skip the duperemove dedup step.",
    )
    storage_maintenance.add_argument(
        "--no-defrag",
        action="store_true",
        help="Skip the defrag + compress step.",
    )
    storage_maintenance.add_argument(
        "--compress-level",
        default="zstd:1",
        help="Compression algorithm:level for defrag (default zstd:1).",
    )

    snapshot = subparsers.add_parser(
        "snapshot",
        help="Capture non-blocking working-tree change snapshots (local, quiet).",
    )
    snapshot.add_argument(
        "--repo",
        default="",
        help="Snapshot only this repository slug.",
    )
    snapshot.add_argument(
        "--status",
        action="store_true",
        help="Show the most recent snapshot commit per repository.",
    )
    snapshot.add_argument(
        "--list",
        action="store_true",
        help="List snapshot commits (requires --repo).",
    )
    snapshot.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum commits for --list (default 20).",
    )

    cred_snap = subparsers.add_parser(
        "credential-snapshot",
        help="Snapshot a credential/config file or directory (surgical restore).",
    )
    cred_snap.add_argument("path", help="File or directory to snapshot.")
    cred_snap.add_argument("--reason", default="", help="Why this snapshot is taken.")

    cred_list = subparsers.add_parser(
        "credential-snapshots",
        help="List available credential/config snapshots.",
    )

    cred_restore = subparsers.add_parser(
        "credential-restore",
        help="Atomically restore a credential/config snapshot (reversible).",
    )
    cred_restore.add_argument("snapshot_dir", help="Snapshot directory to restore.")

    cred_prune = subparsers.add_parser(
        "credential-snapshots-prune",
        help="Delete credential snapshots older than N days.",
    )
    cred_prune.add_argument(
        "--days", type=int, default=30, help="Retention in days (default 30)."
    )

    swarm_control = subparsers.add_parser(
        "swarm-control",
        help="Coordinated multi-agent swarm control for the control panel "
        "(user simulation, QA triage, dev delegation, iteration loop, deploy).",
    )
    swarm_control_sub = swarm_control.add_subparsers(dest="swarm_command")

    sim_users = swarm_control_sub.add_parser(
        "simulate-users",
        help="Run the user simulation swarm (all experience levels + edge segments).",
    )
    sim_users.add_argument("--base-url", default=DEFAULT_BASE_URL)

    triage = swarm_control_sub.add_parser(
        "qa-triage",
        help="Validate user-simulation feedback and assign severity/priority.",
    )
    triage.add_argument("--base-url", default=DEFAULT_BASE_URL)
    triage.add_argument("--simulation-file", default=None,
                        help="Path to a prior user-simulation.json (default: latest).")

    work_items = swarm_control_sub.add_parser(
        "work-items",
        help="Emit validated, prioritized dev work items from the QA triage.",
    )
    work_items.add_argument("--triage-file", default=None,
                            help="Path to a prior qa-triage.json (default: latest).")

    loop = swarm_control_sub.add_parser(
        "run-loop",
        help="Run simulation -> triage iterations until critical/high issues converge.",
    )
    loop.add_argument("--base-url", default=DEFAULT_BASE_URL)
    loop.add_argument("--max-iterations", type=int, default=5)

    deploy = swarm_control_sub.add_parser(
        "deploy",
        help="DevOps production deployment: smoke tests, monitoring, rollback protocol.",
    )
    deploy.add_argument("--base-url", default=DEFAULT_BASE_URL)

    smoke = swarm_control_sub.add_parser(
        "smoke",
        help="Run the post-deployment smoke test suite against the live app.",
    )
    smoke.add_argument("--base-url", default=DEFAULT_BASE_URL)

    swarm_control_sub.add_parser(
        "status",
        help="Show swarm-control state (simulations, triage, work items, deployments).",
    )

    render_catalog = subparsers.add_parser(
        "render-catalog",
        help="Show render engine catalog (local + hosted) with capability and health status.",
    )
    render_catalog.add_argument("--engine", help="Optional engine id filter.")

    render_run = subparsers.add_parser(
        "render-run",
        help="Dispatch a render job through the capability router with fallback.",
    )
    render_run.add_argument("--prompt", required=True)
    render_run.add_argument("--negative", default="")
    render_run.add_argument("--width", type=int, default=1024)
    render_run.add_argument("--height", type=int, default=1024)
    render_run.add_argument("--engine", help="Force a specific engine id; otherwise router selects.")
    render_run.add_argument("--optimize-for", choices=["quality", "speed", "cost"], default="quality")
    render_run.add_argument("--output", help="Output path (workspace-relative or absolute).")
    render_run.add_argument("--no-cache", action="store_true")
    render_run.add_argument("--dry-run", action="store_true")

    subparsers.add_parser(
        "render-telemetry",
        help="Show per-engine render telemetry (latency, cost, quality score, success rate).",
    )

    approval_lane = subparsers.add_parser(
        "approval-lane",
        help="Approval lane: verify communication channels and route approval "
        "requests through the operator's verified primary lane.",
    )
    approval_lane_sub = approval_lane.add_subparsers(dest="approval_lane_command")
    approval_lane_sub.add_parser(
        "status",
        help="Show lane state: channels, verification status, pending approvals.",
    )
    approval_lane_send_test = approval_lane_sub.add_parser(
        "send-test",
        help="Issue a verification code and dispatch a test message on a channel.",
    )
    approval_lane_send_test.add_argument(
        "--channel",
        required=True,
        help="Channel key: 'email' or 'sms:<number>' (e.g. sms:7163528536).",
    )
    approval_lane_verify = approval_lane_sub.add_parser(
        "verify",
        help="Verify a channel with its code and promote it to the primary lane.",
    )
    approval_lane_verify.add_argument("--channel", required=True)
    approval_lane_verify.add_argument(
        "--code",
        required=True,
        help="Verification code from the test message.",
    )
    approval_lane_request = approval_lane_sub.add_parser(
        "request",
        help="Dispatch an approval request through the lane (records it pending).",
    )
    approval_lane_request.add_argument("--subject", required=True)
    approval_lane_request.add_argument("--body", default="")
    approval_lane_request.add_argument(
        "--channel",
        help="Channel key; defaults to the verified primary lane.",
    )
    approval_lane_resolve = approval_lane_sub.add_parser(
        "resolve",
        help="Resolve a pending approval request with its code.",
    )
    approval_lane_resolve.add_argument("--id", required=True)
    approval_lane_resolve.add_argument("--code", required=True)
    approval_lane_resolve.add_argument(
        "--decision",
        choices=["approve", "deny"],
        required=True,
    )
    approval_lane_sub.add_parser(
        "poll",
        help="Poll the verified channel's mailbox for coded replies.",
    )
    approval_lane_sub.add_parser(
        "watch",
        help="Run one autonomous watch pass (retry delivery, poll replies, "
        "auto-verify, confirm primary). Used by the background loop/timer.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    runtime = SubstrateRuntime(root=args.root)
    orchestrator = Orchestrator(runtime)
    ducky_engine = DuckyPayloadEngine(runtime, orchestrator)

    if args.command == "env":
        print(json.dumps(asdict(runtime.environment), indent=2, ensure_ascii=False))
        return 0

    if args.command == "approval-lane":
        from .approvals import (
            approval_lane_status,
            poll_for_replies,
            request_approval,
            resolve_approval,
            send_test_message,
            verify_channel,
            watch_once,
        )

        if args.approval_lane_command == "send-test":
            result = send_test_message(runtime, args.channel)
        elif args.approval_lane_command == "verify":
            result = verify_channel(runtime, args.channel, args.code)
        elif args.approval_lane_command == "request":
            result = request_approval(
                runtime,
                subject=args.subject,
                body=args.body,
                channel=args.channel or None,
            )
        elif args.approval_lane_command == "resolve":
            result = resolve_approval(runtime, args.id, args.code, args.decision)
        elif args.approval_lane_command == "poll":
            result = poll_for_replies(runtime)
        elif args.approval_lane_command == "watch":
            result = watch_once(runtime)
        else:  # status
            result = approval_lane_status(runtime)
        record_execution(
            runtime,
            run_type="approval-lane",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=(
                f"approval-lane {args.approval_lane_command or 'status'} "
                f"{getattr(args, 'channel', '') or ''}"
            ).strip(),
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            note="Approval lane operation",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "scan":
        snapshots = runtime.scan_repositories(persist=True)
        print(json.dumps(snapshots, indent=2, ensure_ascii=False))
        return 0

    if args.command == "runs":
        print(
            json.dumps(
                runtime.db.list_recent_runs(limit=50), indent=2, ensure_ascii=False
            )
        )
        return 0

    if args.command == "sources-list":
        print(
            json.dumps(runtime.db.list_source_projects(), indent=2, ensure_ascii=False)
        )
        return 0

    if args.command == "sources-refresh":
        refreshed = refresh_upstreams(runtime)
        print(json.dumps(refreshed, indent=2, ensure_ascii=False))
        return 0

    if args.command == "standards":
        print(
            json.dumps(
                standards_payload(runtime, track_id=args.track),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "learning":
        print(json.dumps(learning_payload(runtime), indent=2, ensure_ascii=False))
        return 0

    if args.command == "cache-status":
        cache_root = runtime.paths.get("state", Path("state")) / "cache"
        store = CacheStore(cache_root)
        stats = store.stats()
        entries = store.list_entries(kind=args.kind, limit=args.limit)
        print(
            json.dumps(
                {"stats": stats, "entries": entries},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "cache-clear":
        cache_root = runtime.paths.get("state", Path("state")) / "cache"
        store = CacheStore(cache_root)
        removed = store.invalidate(
            kind=args.kind,
            tags=set(args.tag) if args.tag else None,
            older_than_days=args.older_than_days,
        )
        print(json.dumps({"removed": removed}, indent=2, ensure_ascii=False))
        return 0

    if args.command == "cache-prune":
        cache_root = runtime.paths.get("state", Path("state")) / "cache"
        store = CacheStore(cache_root)
        result = store.prune(
            max_age_days=args.max_age_days,
            max_size_mb=args.max_size_mb,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command in {"config-sync-scan", "dotfiles-scan"}:
        result = scan_config_sync(runtime)
        record_execution(
            runtime,
            run_type="config-sync-scan",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=args.command,
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            note="Backup and sync scan",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command in {"config-sync-backup", "dotfiles-backup"}:
        result = backup_config_sync(
            runtime,
            selection=args.path or None,
            profile_ids=args.profile or None,
        )
        record_execution(
            runtime,
            run_type="config-sync-backup",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=(
                f"{args.command} --path {','.join(args.path)} --profile {','.join(args.profile)}"
                if args.path or args.profile
                else args.command
            ),
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            note="Backup and sync snapshot",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command in {"config-sync-plan", "dotfiles-plan"}:
        result = plan_config_sync(
            runtime,
            target_env=args.target,
            selection=args.path or None,
            profile_ids=args.profile or None,
        )
        record_execution(
            runtime,
            run_type="config-sync-plan",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=f"{args.command} --target {args.target or 'current'}",
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            note="Backup and sync deployment plan",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command in {"config-sync-deploy", "dotfiles-deploy"}:
        if not args.apply:
            parser.error(f"{args.command} requires --apply.")
        if not args.directive.strip():
            from .approvals import notify_approval_gate

            notice = notify_approval_gate(
                runtime,
                action=f"{args.command} --apply (deployment)",
                detail=(
                    f"Target: {args.target or 'current'}; selection: "
                    f"{', '.join(args.path or []) or 'all'}."
                ),
            )
            if notice.get("dispatched"):
                parser.error(
                    f"{args.command} requires --directive when --apply is set. "
                    f"Approval request {notice.get('approval_id')} dispatched "
                    f"through the approval lane."
                )
            parser.error(f"{args.command} requires --directive when --apply is set.")
        try:
            result = deploy_config_sync(
                runtime,
                target_env=args.target,
                apply=args.apply,
                directive=args.directive,
                destination=args.destination,
                selection=args.path or None,
                profile_ids=args.profile or None,
            )
        except (PermissionError, ValueError) as exc:
            parser.error(str(exc))
        record_execution(
            runtime,
            run_type="config-sync-deploy",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=(
                f"{args.command} --target {args.target or 'current'} "
                f"--apply --directive {args.directive!r}"
            ),
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            note="Backup and sync deployment",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "integrations":
        print(json.dumps(integrations_payload(runtime), indent=2, ensure_ascii=False))
        return 0

    if args.command == "integration-connect":
        try:
            result = connect_integration(
                runtime,
                service_id=args.service,
                auth_method=args.auth_method or None,
                token_ref=args.token_ref or None,
                granted_scopes=args.scopes,
                mode=args.mode,
                write_directive=args.write_directive,
            )
        except (KeyError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "integration-mode":
        try:
            result = set_integration_mode(
                runtime,
                service_id=args.service,
                mode=args.mode,
                write_directive=args.write_directive,
            )
        except (KeyError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "integration-disconnect":
        try:
            result = disconnect_integration(runtime, service_id=args.service)
        except KeyError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "learning-resolve":
        try:
            note = record_resolution_note(
                runtime,
                signature=args.signature,
                resolution=args.resolution,
                path_reference=args.path,
            )
        except KeyError as exc:
            parser.error(str(exc))
        print(json.dumps(note, indent=2, ensure_ascii=False))
        return 0

    if args.command == "deps-status":
        print(
            json.dumps(
                tooling_snapshot(runtime, profile_id=args.profile),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "deps-ensure":
        try:
            result = ensure_tool_profile(
                runtime,
                profile_id=args.profile,
                apply=args.apply,
            )
        except KeyError as exc:
            parser.error(str(exc))
        failed = [
            action for action in result["actions"] if action["status"] == "failed"
        ]
        record_execution(
            runtime,
            run_type="deps-ensure",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=f"deps-ensure --profile {args.profile} --apply={str(args.apply).lower()}",
            status="failed" if failed else "success",
            exit_code=1 if failed else 0,
            stdout=json.dumps(result, ensure_ascii=False),
            stderr=json.dumps(failed, ensure_ascii=False) if failed else "",
            note="Optional dependency assembly plan",
            classify_as_test=True,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "record-test":
        import subprocess

        repo_slug = None
        if args.repo:
            try:
                repo_slug = runtime.resolve_repo(args.repo).slug
            except KeyError as exc:
                parser.error(str(exc))

        workdir_path = Path(args.workdir).expanduser()
        if not workdir_path.is_absolute():
            workdir_path = (runtime.root / workdir_path).resolve()
        completed = subprocess.run(
            args.test_command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            cwd=workdir_path,
        )
        status = "success" if completed.returncode == 0 else "failed"
        event = record_execution(
            runtime,
            run_type="manual-test",
            run_id=None,
            repo_slug=repo_slug,
            stage=args.stage,
            command=args.test_command,
            status=status,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            note=args.name,
            classify_as_test=True,
        )
        print(
            json.dumps(
                {
                    "status": status,
                    "exit_code": completed.returncode,
                    "event": event,
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "payloads":
        repo_slug = None
        if args.repo:
            try:
                repo_slug = runtime.resolve_repo(args.repo).slug
            except KeyError as exc:
                parser.error(str(exc))
        print(
            json.dumps(
                {"payloads": ducky_engine.list_payloads(repo_slug=repo_slug)},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "run-payload":
        repo_slug = None
        if args.repo:
            try:
                repo_slug = runtime.resolve_repo(args.repo).slug
            except KeyError as exc:
                parser.error(str(exc))
        try:
            job_id = ducky_engine.submit(
                payload_id=args.payload,
                repo_slug=repo_slug,
                stage=args.stage,
                allow_stage_skip=args.allow_stage_skip,
                port=args.port,
            )
        except (KeyError, ValueError) as exc:
            parser.error(str(exc))
        if not args.wait:
            print(json.dumps({"job_id": job_id}, indent=2, ensure_ascii=False))
            return 0

        timeout_seconds = max(args.timeout, 1)
        poll_interval_seconds = 0.4
        deadline = time.monotonic() + timeout_seconds
        max_poll_attempts = max(1, int(timeout_seconds / poll_interval_seconds) + 2)
        for _ in range(max_poll_attempts):
            job = ducky_engine.get_job(job_id)
            if job is None:
                parser.error(f"Payload job disappeared: {job_id}")
            if job["status"] in {"success", "failed"}:
                print(json.dumps(job, indent=2, ensure_ascii=False))
                return 0
            if time.monotonic() >= deadline:
                parser.error(
                    f"Timed out waiting for payload job '{job_id}' after {args.timeout}s"
                )
            time.sleep(poll_interval_seconds)
        parser.error(
            f"Timed out waiting for payload job '{job_id}' after {args.timeout}s"
        )

    if args.command in {
        "community-cycle",
        "spawn-agent-workloads",
        "spawn-agent-workloads-now",
    }:
        try:
            result = run_community_cycle(
                runtime,
                cycle=args.cycle,
                stage=args.stage,
                concurrency_limit=args.concurrency_limit,
                repo_slug=args.repo,
                agent_provider=args.agent_provider,
                agent_model=args.agent_model or None,
                seed=args.seed,
                population_scale=args.population_scale,
            )
        except (KeyError, PermissionError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "run-chain":
        try:
            runtime.resolve_repo(args.repo)
        except KeyError as exc:
            parser.error(str(exc))
        chain_path = _validate_relative_yaml(runtime.root, args.chain)
        context_files = _validate_context_files(runtime.root, args.context_file)
        run_id = orchestrator.run_chain(
            repo_slug=args.repo,
            objective=args.objective,
            chain_path=chain_path,
            provider=args.provider,
            model=args.model,
            dry_run=args.dry_run,
            stage=args.stage,
            requested_mode=args.mode,
            allow_mutations=args.allow_mutations,
            allow_stage_skip=args.allow_stage_skip,
            extra_context_files=context_files,
            openclaw_manual_trigger=args.openclaw_manual_trigger,
            openclaw_data_class=args.openclaw_data_class,
            use_cache=not args.no_cache,
        )
        print(json.dumps({"run_id": run_id}, indent=2))
        return 0

    if args.command == "discount-swarm":
        try:
            runtime.resolve_repo(args.repo)
        except KeyError as exc:
            parser.error(str(exc))
        try:
            datetime.strptime(args.as_of_date, "%Y-%m-%d")
        except ValueError:
            parser.error(f"Invalid --as-of-date value: {args.as_of_date}")
        if args.lookback_days < 1:
            parser.error("--lookback-days must be >= 1")
        plan = _build_discount_swarm_plan(
            repo_slug=args.repo,
            merchant=args.merchant.strip(),
            as_of_date=args.as_of_date,
            lookback_days=args.lookback_days,
            provider=args.provider,
            model=args.model,
            stage=args.stage,
        )
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    if args.command == "run-task":
        try:
            repo = runtime.resolve_repo(args.repo)
        except KeyError as exc:
            parser.error(str(exc))
        if args.task not in repo.tasks:
            parser.error(f"Unknown task id for repo '{args.repo}': {args.task}")
        run_id = orchestrator.run_task(
            repo_slug=args.repo,
            task_id=args.task,
            stage=args.stage,
            requested_mode=args.mode,
            allow_mutations=args.allow_mutations,
            allow_stage_skip=args.allow_stage_skip,
        )
        print(json.dumps({"run_id": run_id}, indent=2))
        return 0

    if args.command == "pinch":
        repo_slug = None
        if args.repo:
            try:
                repo_slug = runtime.resolve_repo(args.repo).slug
            except KeyError as exc:
                parser.error(str(exc))
        report = _pinch_report(args.port, repo_slug=repo_slug)
        print(f"Base URL: {report['base_url']}")
        print("Access hints:")
        for item in report["access"]:
            status = "available" if item["available"] else "missing"
            print(f"- {item['tool']} [{status}]: {item['command']}")
            if item.get("alternate"):
                print(f"  alternate: {item['alternate']}")
            print(f"  notes: {item['notes']}")
        print("Diagnostics:")
        for item in report["diagnostics"]:
            print(f"- {item['label']}: {item['command']}")
        return 0

    if args.command == "prefill-proxy":
        subcommand = args.prefill_proxy_command
        if subcommand in (None, "status"):
            payload = status_daemon(root=runtime.root)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if payload.get("running") else 1

        if subcommand == "stop":
            payload = stop_daemon(root=runtime.root)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if subcommand == "start":
            if args.daemon:
                payload = start_daemon(
                    root=runtime.root,
                    host=args.host,
                    port=args.port,
                    mode=args.mode,
                )
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                return 0
            serve_forever(host=args.host, port=args.port, mode=args.mode)
            return 0

        parser.error(f"unknown prefill-proxy subcommand: {subcommand!r}")

    if args.command == "serve":
        import uvicorn

        # Port 8090 is owned by OpenClaw Gateway; warn before binding.
        if args.port == 8090:
            print(
                "WARNING: OpenClaw Gateway owns 127.0.0.1:8090. "
                "Use an alternative port for local dev (e.g. --port 8095).",
                file=__import__("sys").stderr,
            )

        uvicorn.run(
            "substrate.web:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            factory=False,
        )
        return 0

    if args.command == "agent-cycle":
        try:
            result = run_agent_cycle(
                runtime,
                orchestrator,
                only_ids=args.agent or None,
                dry_run=args.dry_run,
                directive=args.directive,
            )
        except AgentConfigError as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "agent-run":
        try:
            agents = load_agents_config(runtime.root)
        except AgentConfigError as exc:
            parser.error(str(exc))
        matches = [
            agent
            for agent in agents
            if agent.role == args.role and agent.repo_slug == args.repo
        ]
        if not matches:
            parser.error(
                f"No agent with role '{args.role}' for repo '{args.repo}' in agents.yaml."
            )
        results = []
        for agent in matches:
            result = run_agent(
                runtime,
                orchestrator,
                agent,
                directive=args.directive,
                force=args.force,
            )
            results.append(result.to_dict())
        print(
            json.dumps(
                results[0] if len(results) == 1 else results,
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "agent-status":
        try:
            payload = agent_status_payload(runtime)
        except AgentConfigError as exc:
            parser.error(str(exc))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.command == "storage-status":
        from .btrfs import status_report

        report = status_report(runtime.root)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.command == "storage-validate":
        from .btrfs import compatibility_report

        report = compatibility_report(runtime.root)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if not report["compatible"] else 0

    if args.command == "capsule":
        from .capsule import plan_capsule, probe_capsule, release_manifest, write_manifest

        if args.capsule_command == "probe":
            result = probe_capsule(runtime.root)
        elif args.capsule_command == "plan":
            result = plan_capsule(runtime.root)
        elif args.output:
            result = write_manifest(runtime.root, args.output)
        else:
            result = release_manifest(runtime.root)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "storage-maintenance":
        from .btrfs import run_maintenance

        result = run_maintenance(
            runtime.root,
            apply=args.apply,
            dedup=not args.no_dedup,
            defrag=not args.no_defrag,
            compress_level=args.compress_level,
        )
        record_execution(
            runtime,
            run_type="storage-maintenance",
            run_id=None,
            repo_slug=None,
            stage="local",
            command=(
                "storage-maintenance --apply"
                if args.apply
                else "storage-maintenance (dry-run)"
            ),
            status="success",
            exit_code=0,
            stdout=json.dumps(result, ensure_ascii=False),
            note="Btrfs dedup/defrag maintenance",
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "snapshot":
        from .snapshots import SnapshotEngine

        engine = SnapshotEngine(runtime.root)

        if args.status:
            print(json.dumps(engine.status(runtime), indent=2, ensure_ascii=False))
            return 0

        if args.list:
            if not args.repo:
                parser.error("snapshot --list requires --repo.")
            try:
                repo_cfg = runtime.resolve_repo(args.repo)
            except KeyError as exc:
                parser.error(str(exc))
            repo_path = (runtime.root / repo_cfg.path).resolve()
            commits = engine.list_snapshots(repo_path, limit=args.limit)
            print(json.dumps(commits, indent=2, ensure_ascii=False))
            return 0

        if args.repo:
            try:
                repo_cfg = runtime.resolve_repo(args.repo)
            except KeyError as exc:
                parser.error(str(exc))
            repo_path = (runtime.root / repo_cfg.path).resolve()
            results = [engine.snapshot_repo(args.repo, repo_path)]
        else:
            results = engine.snapshot_all(runtime)

        failed = any(r["status"] in {"error", "blocked"} for r in results)
        record_execution(
            runtime,
            run_type="snapshot",
            run_id=None,
            repo_slug=args.repo or None,
            stage="local",
            command=f"snapshot --repo {args.repo}" if args.repo else "snapshot",
            status="failure" if failed else "success",
            exit_code=1 if failed else 0,
            stdout=json.dumps(results, ensure_ascii=False),
            note="Working-tree change snapshot",
        )
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 1 if failed else 0

    if args.command in {
        "credential-snapshot",
        "credential-snapshots",
        "credential-restore",
        "credential-snapshots-prune",
    }:
        from scripts.credential_snapshots import (
            list_snapshots,
            prune,
            restore,
            snapshot as cred_snapshot,
        )

        try:
            if args.command == "credential-snapshot":
                result = cred_snapshot(args.path, reason=args.reason, root=runtime.root)
            elif args.command == "credential-snapshots":
                result = list_snapshots(root=runtime.root)
            elif args.command == "credential-restore":
                result = restore(args.snapshot_dir, root=runtime.root)
            else:
                result = {"removed": prune(args.days, root=runtime.root)}
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "swarm-control":
        if args.swarm_command == "simulate-users":
            result = run_user_simulation(args.base_url)
        elif args.swarm_command == "qa-triage":
            sim_path = Path(args.simulation_file) if args.simulation_file else None
            if sim_path is None or not sim_path.exists():
                sim_path = Path("state/swarm-control/user-simulation.json")
            if not sim_path.exists():
                parser.error(
                    "no user simulation found; run 'swarm-control simulate-users' first"
                )
            simulation = json.loads(sim_path.read_text())
            result = run_triage_from_simulation(simulation)
        elif args.swarm_command == "work-items":
            triage_path = Path(args.triage_file) if args.triage_file else None
            if triage_path is None or not triage_path.exists():
                triage_path = Path("state/swarm-control/qa-triage.json")
            if not triage_path.exists():
                parser.error(
                    "no QA triage found; run 'swarm-control qa-triage' first"
                )
            triage = json.loads(triage_path.read_text())
            result = emit_work_items(triage)
        elif args.swarm_command == "run-loop":
            result = run_iteration_loop(args.base_url, max_iterations=args.max_iterations)
        elif args.swarm_command == "deploy":
            result = deploy_production(args.base_url)
        elif args.swarm_command == "smoke":
            result = smoke_tests(args.base_url)
        else:  # status
            result = swarm_status()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "render-catalog":
        print(
            json.dumps(
                render_catalog_payload(runtime, engine_id=args.engine),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "render-run":
        try:
            result = render_dispatch(
                runtime,
                RenderRequest(
                    prompt=args.prompt,
                    negative=args.negative,
                    width=args.width,
                    height=args.height,
                    output=Path(args.output) if args.output else None,
                ),
                optimize_for=args.optimize_for,
                forced_engine=args.engine,
                use_cache=not args.no_cache,
                dry_run=args.dry_run,
            )
        except (ValueError, RenderUnavailable) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.command == "render-telemetry":
        print(
            json.dumps(
                render_telemetry_payload(runtime),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
