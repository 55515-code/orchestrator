from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .models import PolicyConfig, RepositoryConfig, TaskConfig, WorkspaceConfig

WORKSPACE_FILE = "workspace.yaml"
UPSTREAMS_FILE = "upstreams.yaml"
STANDARDS_FILE = "standards.yaml"
TOOL_PROFILES_FILE = "tool_profiles.yaml"
INTEGRATIONS_FILE = "integrations.yaml"
CONFIG_SYNC_PROFILES_FILE = "config_sync_profiles.yaml"
STATE_DIR = "state"
MEMORY_DIR = "memory"
RESEARCH_DIR = ".research"

DEFAULT_IGNORED_PATHS = [
    ".git",
    ".venv",
    ".direnv",
    "node_modules",
    "aosp-eos-asteroids",
    "work",
    "tmp",
    "downloads",
    "tools",
    "site",
]


def discover_workspace_root(start: Path | None = None) -> Path:
    cursor = (start or Path.cwd()).resolve()
    search_order = [cursor, *cursor.parents]
    for path in search_order:
        if (path / WORKSPACE_FILE).exists():
            return path
    for path in search_order:
        if (path / "pyproject.toml").exists():
            return path
    return cursor


def workspace_paths(root: Path) -> dict[str, Path]:
    return {
        "workspace": root / WORKSPACE_FILE,
        "upstreams": root / UPSTREAMS_FILE,
        "standards": root / STANDARDS_FILE,
        "tool_profiles": root / TOOL_PROFILES_FILE,
        "integrations": root / INTEGRATIONS_FILE,
        "config_sync_profiles": root / CONFIG_SYNC_PROFILES_FILE,
        "memory": root / MEMORY_DIR,
        "state": root / STATE_DIR,
        "research": root / RESEARCH_DIR,
        "db": root / STATE_DIR / "orchestrator.db",
        "integrations_state": root / STATE_DIR / "integrations-state.json",
        "learning_index": root / STATE_DIR / "learning-index.json",
        "learning_log": root / MEMORY_DIR / "dev-history.jsonl",
        "config_sync_index": root / STATE_DIR / "config-sync-index.json",
        "config_sync_backups": root / MEMORY_DIR / "config-sync" / "backups",
        "config_sync_deployments": root / MEMORY_DIR / "config-sync" / "deployments",
        # Legacy path keys retained for backward compatibility.
        "dotfiles_index": root / STATE_DIR / "dotfiles-index.json",
        "dotfiles_backups": root / MEMORY_DIR / "dotfiles" / "backups",
        "dotfiles_deployments": root / MEMORY_DIR / "dotfiles" / "deployments",
    }


def ensure_runtime_dirs(root: Path) -> None:
    paths = workspace_paths(root)
    paths["memory"].mkdir(parents=True, exist_ok=True)
    paths["state"].mkdir(parents=True, exist_ok=True)
    paths["research"].mkdir(parents=True, exist_ok=True)


def _default_slug(path: Path) -> str:
    raw = path.name or "workspace"
    return re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-") or "workspace"


def _as_command(raw: Any, task_id: str) -> list[str] | dict[str, list[str]]:
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    if isinstance(raw, dict):
        result: dict[str, list[str]] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ValueError(f"Task '{task_id}' has non-string command key.")
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ValueError(
                    f"Task '{task_id}' command for '{key}' must be a list of strings."
                )
            result[key] = list(value)
        return result
    raise ValueError(
        f"Task '{task_id}' command must be a list[str] or mapping[str, list[str]]."
    )


def _as_string_list(
    raw: Any,
    *,
    field: str,
    default: list[str],
    normalize_lower: bool = False,
) -> list[str]:
    if raw is None:
        values = list(default)
    else:
        if not isinstance(raw, list):
            raise ValueError(f"{field} must be a list of strings.")
        values = []
        for item in raw:
            if not isinstance(item, str):
                raise ValueError(f"{field} must be a list of strings.")
            token = item.strip()
            if not token:
                continue
            values.append(token.lower() if normalize_lower else token)
    if not values:
        raise ValueError(f"{field} must include at least one value.")
    return values


def _parse_tasks(raw_tasks: Any) -> dict[str, TaskConfig]:
    if raw_tasks is None:
        return {}
    if not isinstance(raw_tasks, dict):
        raise ValueError("Repository 'tasks' must be a mapping.")
    tasks: dict[str, TaskConfig] = {}
    for task_id, payload in raw_tasks.items():
        if not isinstance(task_id, str):
            raise ValueError("Task id must be a string.")
        if not isinstance(payload, dict):
            raise ValueError(f"Task '{task_id}' must be a mapping.")
        description = str(payload.get("description", task_id))
        mode = str(payload.get("mode", "observe"))
        if mode not in {"observe", "mutate"}:
            raise ValueError(f"Task '{task_id}' mode must be observe|mutate.")
        command = _as_command(payload.get("command"), task_id)
        workdir = str(payload.get("workdir", "."))
        tasks[task_id] = TaskConfig(
            id=task_id,
            description=description,
            command=command,
            workdir=workdir,
            mode=mode,  # type: ignore[arg-type]
        )
    return tasks


def _default_repository(root: Path) -> RepositoryConfig:
    return RepositoryConfig(
        slug=_default_slug(root),
        path=Path("."),
        allow_mutations=False,
        default_mode="observe",
        tasks={
            "probe_system": TaskConfig(
                id="probe_system",
                description="Generate a cross-platform system profile.",
                mode="observe",
                command=["python", "scripts/probe_system.py", "docs/system-probe.md"],
            ),
            "chain_dry_run": TaskConfig(
                id="chain_dry_run",
                description="Run the substrate chain in dry-run mode.",
                mode="observe",
                command=[
                    "python",
                    "scripts/run_chain.py",
                    "--objective",
                    "Repository health audit",
                    "--dry-run",
                ],
            ),
        },
    )


def load_workspace_config(root: Path) -> WorkspaceConfig:
    workspace_path = root / WORKSPACE_FILE
    if workspace_path.exists():
        payload = yaml.safe_load(workspace_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"{workspace_path} must be a YAML mapping.")
    else:
        payload = {}

    raw_policy = payload.get("policy", {})
    if raw_policy and not isinstance(raw_policy, dict):
        raise ValueError("workspace.yaml policy must be a mapping.")
    rc1_openclaw_allowed_stages = _as_string_list(
        raw_policy.get("rc1_openclaw_allowed_stages"),
        field="policy.rc1_openclaw_allowed_stages",
        default=["local", "hosted_dev"],
        normalize_lower=True,
    )
    rc1_openclaw_allowed_passes = _as_string_list(
        raw_policy.get("rc1_openclaw_allowed_passes"),
        field="policy.rc1_openclaw_allowed_passes",
        default=["research"],
        normalize_lower=True,
    )
    rc1_openclaw_allowed_data_classes = _as_string_list(
        raw_policy.get("rc1_openclaw_allowed_data_classes"),
        field="policy.rc1_openclaw_allowed_data_classes",
        default=["synthetic", "redacted"],
        normalize_lower=True,
    )
    rc1_bounded_validation_enabled = bool(
        raw_policy.get("rc1_bounded_validation_enabled", True)
    )
    rc1_hardware_probe_enabled = bool(raw_policy.get("rc1_hardware_probe_enabled", False))
    rc1_validation_max_attempts = int(raw_policy.get("rc1_validation_max_attempts", 2))
    rc1_validation_attempt_timeout_seconds = int(
        raw_policy.get("rc1_validation_attempt_timeout_seconds", 20)
    )
    rc1_validation_deadline_seconds = int(
        raw_policy.get("rc1_validation_deadline_seconds", 60)
    )
    rc1_watchdog_enabled = bool(raw_policy.get("rc1_watchdog_enabled", False))
    rc1_respawn_enabled = bool(raw_policy.get("rc1_respawn_enabled", False))
    rc1_watchdog_max_respawns = int(raw_policy.get("rc1_watchdog_max_respawns", 1))
    rc1_watchdog_heartbeat_timeout_seconds = float(
        raw_policy.get("rc1_watchdog_heartbeat_timeout_seconds", 5.0)
    )
    rc1_watchdog_stuck_confirmation_seconds = float(
        raw_policy.get("rc1_watchdog_stuck_confirmation_seconds", 2.0)
    )
    rc1_watchdog_poll_interval_seconds = float(
        raw_policy.get("rc1_watchdog_poll_interval_seconds", 0.5)
    )
    rc1_watchdog_terminate_grace_seconds = float(
        raw_policy.get("rc1_watchdog_terminate_grace_seconds", 1.0)
    )

    policy = PolicyConfig(
        default_mode=str(raw_policy.get("default_mode", "observe")),  # type: ignore[arg-type]
        require_source_facts_before_mutation=bool(
            raw_policy.get("require_source_facts_before_mutation", True)
        ),
        source_freshness_days=int(raw_policy.get("source_freshness_days", 30)),
        enforce_stage_flow=bool(raw_policy.get("enforce_stage_flow", True)),
        stage_sequence=list(
            raw_policy.get("stage_sequence", ["local", "hosted_dev", "production"])
        ),
        pass_sequence=list(
            raw_policy.get("pass_sequence", ["research", "development", "testing"])
        ),
        rc1_openclaw_internal_assist_enabled=bool(
            raw_policy.get("rc1_openclaw_internal_assist_enabled", False)
        ),
        rc1_openclaw_manual_trigger_required=bool(
            raw_policy.get("rc1_openclaw_manual_trigger_required", True)
        ),
        rc1_openclaw_revetting_required=bool(
            raw_policy.get("rc1_openclaw_revetting_required", True)
        ),
        rc1_openclaw_allowed_stages=rc1_openclaw_allowed_stages,
        rc1_openclaw_allowed_passes=rc1_openclaw_allowed_passes,
        rc1_openclaw_allowed_data_classes=rc1_openclaw_allowed_data_classes,
        rc1_bounded_validation_enabled=rc1_bounded_validation_enabled,
        rc1_hardware_probe_enabled=rc1_hardware_probe_enabled,
        rc1_validation_max_attempts=rc1_validation_max_attempts,
        rc1_validation_attempt_timeout_seconds=rc1_validation_attempt_timeout_seconds,
        rc1_validation_deadline_seconds=rc1_validation_deadline_seconds,
        rc1_watchdog_enabled=rc1_watchdog_enabled,
        rc1_respawn_enabled=rc1_respawn_enabled,
        rc1_watchdog_max_respawns=rc1_watchdog_max_respawns,
        rc1_watchdog_heartbeat_timeout_seconds=rc1_watchdog_heartbeat_timeout_seconds,
        rc1_watchdog_stuck_confirmation_seconds=rc1_watchdog_stuck_confirmation_seconds,
        rc1_watchdog_poll_interval_seconds=rc1_watchdog_poll_interval_seconds,
        rc1_watchdog_terminate_grace_seconds=rc1_watchdog_terminate_grace_seconds,
    )
    if policy.default_mode not in {"observe", "mutate"}:
        raise ValueError("policy.default_mode must be observe|mutate.")
    if not policy.stage_sequence:
        raise ValueError("policy.stage_sequence must include at least one stage.")
    if not policy.pass_sequence:
        raise ValueError("policy.pass_sequence must include at least one pass.")
    if policy.rc1_validation_max_attempts < 1:
        raise ValueError("policy.rc1_validation_max_attempts must be >= 1.")
    if policy.rc1_validation_attempt_timeout_seconds < 1:
        raise ValueError(
            "policy.rc1_validation_attempt_timeout_seconds must be >= 1."
        )
    if policy.rc1_validation_deadline_seconds < 1:
        raise ValueError("policy.rc1_validation_deadline_seconds must be >= 1.")
    if policy.rc1_watchdog_max_respawns < 0:
        raise ValueError("policy.rc1_watchdog_max_respawns must be >= 0.")
    if policy.rc1_watchdog_heartbeat_timeout_seconds <= 0:
        raise ValueError(
            "policy.rc1_watchdog_heartbeat_timeout_seconds must be > 0."
        )
    if policy.rc1_watchdog_stuck_confirmation_seconds <= 0:
        raise ValueError(
            "policy.rc1_watchdog_stuck_confirmation_seconds must be > 0."
        )
    if policy.rc1_watchdog_poll_interval_seconds <= 0:
        raise ValueError("policy.rc1_watchdog_poll_interval_seconds must be > 0.")
    if policy.rc1_watchdog_terminate_grace_seconds <= 0:
        raise ValueError(
            "policy.rc1_watchdog_terminate_grace_seconds must be > 0."
        )
    openclaw_allowed_stages = set(policy.rc1_openclaw_allowed_stages)
    openclaw_allowed_passes = set(policy.rc1_openclaw_allowed_passes)
    openclaw_allowed_data_classes = set(policy.rc1_openclaw_allowed_data_classes)
    approved_openclaw_stages = {"local", "hosted_dev"}
    approved_openclaw_passes = {"research"}
    approved_openclaw_data_classes = {"synthetic", "redacted"}

    if "production" in openclaw_allowed_stages:
        raise ValueError(
            "policy.rc1_openclaw_allowed_stages cannot include 'production'."
        )
    if not openclaw_allowed_stages.issubset(approved_openclaw_stages):
        raise ValueError(
            "policy.rc1_openclaw_allowed_stages must stay within local|hosted_dev."
        )
    if not openclaw_allowed_passes.issubset(approved_openclaw_passes):
        raise ValueError(
            "policy.rc1_openclaw_allowed_passes must stay within research."
        )
    if not openclaw_allowed_data_classes.issubset(approved_openclaw_data_classes):
        raise ValueError(
            "policy.rc1_openclaw_allowed_data_classes must stay within synthetic|redacted."
        )

    repositories: dict[str, RepositoryConfig] = {}
    raw_repositories = payload.get("repositories")
    if raw_repositories is None:
        repo = _default_repository(root)
        repositories[repo.slug] = repo
    elif not isinstance(raw_repositories, list):
        raise ValueError("workspace.yaml repositories must be a list.")
    else:
        for index, raw_repo in enumerate(raw_repositories, start=1):
            if not isinstance(raw_repo, dict):
                raise ValueError(f"repositories[{index}] must be a mapping.")
            slug = str(raw_repo.get("slug") or "")
            if not slug:
                path_for_slug = Path(str(raw_repo.get("path", ".")))
                slug = _default_slug(path_for_slug)
            if slug in repositories:
                raise ValueError(f"Duplicate repository slug: {slug}")
            repo_path = Path(str(raw_repo.get("path", ".")))
            default_mode = str(raw_repo.get("default_mode", policy.default_mode))
            if default_mode not in {"observe", "mutate"}:
                raise ValueError(
                    f"Repository '{slug}' default_mode must be observe|mutate."
                )
            repositories[slug] = RepositoryConfig(
                slug=slug,
                path=repo_path,
                allow_mutations=bool(raw_repo.get("allow_mutations", False)),
                default_mode=default_mode,  # type: ignore[arg-type]
                tasks=_parse_tasks(raw_repo.get("tasks")),
            )

    raw_discovery = payload.get("discovery", {})
    if raw_discovery and not isinstance(raw_discovery, dict):
        raise ValueError("workspace.yaml discovery must be a mapping.")
    auto_discovery_enabled = bool(raw_discovery.get("enabled", True))
    auto_discovery_roots_raw = raw_discovery.get("roots", ["."])
    if not isinstance(auto_discovery_roots_raw, list):
        raise ValueError("discovery.roots must be a list.")
    auto_discovery_roots = [Path(str(item)) for item in auto_discovery_roots_raw]
    auto_discovery_max_depth = int(raw_discovery.get("max_depth", 2))
    ignored_paths = list(payload.get("ignored_paths", DEFAULT_IGNORED_PATHS))
    if not all(isinstance(item, str) for item in ignored_paths):
        raise ValueError("ignored_paths must be a list of strings.")

    return WorkspaceConfig(
        root=root,
        repositories=repositories,
        policy=policy,
        auto_discovery_enabled=auto_discovery_enabled,
        auto_discovery_roots=auto_discovery_roots,
        auto_discovery_max_depth=auto_discovery_max_depth,
        ignored_paths=ignored_paths,
    )
