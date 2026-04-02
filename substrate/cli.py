from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .config_sync import (
    CONFIG_SYNC_TARGET_ENVS,
    backup_config_sync,
    deploy_config_sync,
    plan_config_sync,
    scan_config_sync,
)
from .community import run_community_cycle
from .ducky import DuckyPayloadEngine
from .integrations import (
    connect_integration,
    disconnect_integration,
    integrations_payload,
    set_integration_mode,
)
from .learning import learning_payload, record_execution, record_resolution_note
from .orchestrator import Orchestrator
from .registry import SubstrateRuntime
from .research import refresh_upstreams
from .standards import standards_payload
from .tooling import ensure_tool_profile, tooling_snapshot

ALLOWED_CHAIN_PROVIDERS = {"mock", "local", "anthropic", "ollama"}
ALLOWED_AGENT_PROVIDERS = {"mock", "local", "anthropic", "ollama", "codex"}
ALLOWED_STAGES = {"local", "hosted_dev", "production"}
ALLOWED_MODES = {"observe", "mutate"}
ALLOWED_OPENCLAW_DATA_CLASSES = {"synthetic", "redacted"}


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
    return datetime.now(timezone.utc).date().isoformat()


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

    community_cycle = subparsers.add_parser(
        "community-cycle",
        help=(
            "Run a weekly open-source community cycle with independent "
            "persona agents (100 developer + 300 user/tester sessions)."
        ),
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

    if args.command == "community-cycle":
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

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "substrate.web:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            factory=False,
        )
        return 0

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
