from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

RunMode = Literal["observe", "mutate"]
RunType = Literal["chain", "task"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class EnvironmentProfile:
    os_name: str
    os_release: str
    machine: str
    python_version: str
    user: str
    hostname: str
    cwd: str
    shell: str
    is_ci: bool
    is_codespaces: bool
    is_github_actions: bool
    is_wsl: bool
    git_available: bool
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TaskConfig:
    id: str
    description: str
    command: list[str] | dict[str, list[str]]
    workdir: str = "."
    mode: RunMode = "observe"

    def command_for_platform(self, platform_key: str) -> list[str]:
        if isinstance(self.command, list):
            return self.command
        selected = self.command.get(platform_key) or self.command.get("default")
        if not selected:
            raise ValueError(
                f"Task '{self.id}' has no command for platform '{platform_key}'."
            )
        return selected


@dataclass(slots=True)
class RepositoryConfig:
    slug: str
    path: Path
    allow_mutations: bool = False
    default_mode: RunMode = "observe"
    tasks: dict[str, TaskConfig] = field(default_factory=dict)


@dataclass(slots=True)
class PolicyConfig:
    default_mode: RunMode = "observe"
    require_source_facts_before_mutation: bool = True
    source_freshness_days: int = 30
    enforce_stage_flow: bool = True
    stage_sequence: list[str] = field(
        default_factory=lambda: ["local", "hosted_dev", "production"]
    )
    pass_sequence: list[str] = field(
        default_factory=lambda: ["research", "development", "testing"]
    )
    rc1_openclaw_internal_assist_enabled: bool = False
    rc1_openclaw_manual_trigger_required: bool = True
    rc1_openclaw_revetting_required: bool = True
    rc1_openclaw_allowed_stages: list[str] = field(
        default_factory=lambda: ["local", "hosted_dev"]
    )
    rc1_openclaw_allowed_passes: list[str] = field(
        default_factory=lambda: ["research"]
    )
    rc1_openclaw_allowed_data_classes: list[str] = field(
        default_factory=lambda: ["synthetic", "redacted"]
    )
    rc1_bounded_validation_enabled: bool = True
    rc1_hardware_probe_enabled: bool = False
    rc1_validation_max_attempts: int = 2
    rc1_validation_attempt_timeout_seconds: int = 20
    rc1_validation_deadline_seconds: int = 60
    rc1_watchdog_enabled: bool = False
    rc1_respawn_enabled: bool = False
    rc1_watchdog_max_respawns: int = 1
    rc1_watchdog_heartbeat_timeout_seconds: float = 5.0
    rc1_watchdog_stuck_confirmation_seconds: float = 2.0
    rc1_watchdog_poll_interval_seconds: float = 0.5
    rc1_watchdog_terminate_grace_seconds: float = 1.0


@dataclass(slots=True)
class WorkspaceConfig:
    root: Path
    repositories: dict[str, RepositoryConfig]
    policy: PolicyConfig
    auto_discovery_enabled: bool = True
    auto_discovery_roots: list[Path] = field(default_factory=list)
    auto_discovery_max_depth: int = 2
    ignored_paths: list[str] = field(default_factory=list)
