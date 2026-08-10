"""Pipeline data models.

Defines the structure for pipelines, stages, and runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PipelineStatus(str, Enum):
    """Pipeline run status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TriggerType(str, Enum):
    """Pipeline trigger types."""

    PUSH = "push"
    PULL_REQUEST = "pull_request"
    TAG = "tag"
    RELEASE = "release"
    MANUAL = "manual"
    SCHEDULE = "schedule"


@dataclass
class PipelineStage:
    """A stage within a pipeline.

    Stages are executed sequentially and can contain multiple steps.
    """

    name: str
    commands: list[str]
    environment: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    timeout_seconds: int = 3600
    allow_failure: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "commands": self.commands,
            "environment": self.environment,
            "artifacts": self.artifacts,
            "timeout_seconds": self.timeout_seconds,
            "allow_failure": self.allow_failure,
        }


@dataclass
class Pipeline:
    """A reusable pipeline definition.

    Pipelines define a sequence of stages that can be triggered
    by various events (push, PR, manual, etc.).
    """

    name: str
    description: str
    stages: list[PipelineStage]
    triggers: list[TriggerType] = field(default_factory=list)
    branch_filter: list[str] = field(default_factory=list)
    tags_filter: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 7200
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "stages": [stage.to_dict() for stage in self.stages],
            "triggers": [t.value for t in self.triggers],
            "branch_filter": self.branch_filter,
            "tags_filter": self.tags_filter,
            "environment": self.environment,
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
        }


@dataclass
class PipelineRun:
    """A single execution of a pipeline.

    Tracks the status, timing, and artifacts for a pipeline run.
    """

    id: str
    pipeline_name: str
    status: PipelineStatus
    trigger: TriggerType
    started_at: datetime
    completed_at: datetime | None = None
    commit_sha: str | None = None
    branch: str | None = None
    tag: str | None = None
    pr_number: int | None = None
    triggered_by: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    logs: dict[str, str] = field(default_factory=dict)  # stage_name -> log_path
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "pipeline_name": self.pipeline_name,
            "status": self.status.value,
            "trigger": self.trigger.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "tag": self.tag,
            "pr_number": self.pr_number,
            "triggered_by": self.triggered_by,
            "environment": self.environment,
            "artifacts": self.artifacts,
            "logs": self.logs,
            "error": self.error,
        }

    @property
    def duration_seconds(self) -> float | None:
        """Calculate run duration in seconds."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()
