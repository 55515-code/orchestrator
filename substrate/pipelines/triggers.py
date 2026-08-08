"""Git event triggers for pipelines.

Handles webhook events from Git platforms (GitHub, GitLab, etc.)
and triggers appropriate pipeline runs.
"""

from __future__ import annotations

import re
from typing import Any

from .engine import PipelineEngine
from .models import Pipeline, TriggerType
from .registry import PipelineRegistry


class TriggerHandler:
    """Handles Git event triggers for pipelines.

    Parses webhook payloads and matches them to appropriate
    pipelines based on trigger configuration.
    """

    def __init__(
        self,
        registry: PipelineRegistry,
        engine: PipelineEngine,
    ) -> None:
        """Initialize the trigger handler.

        Args:
            registry: Pipeline registry.
            engine: Pipeline execution engine.
        """
        self.registry = registry
        self.engine = engine

    async def handle_github_webhook(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> list[str]:
        """Handle a GitHub webhook event.

        Args:
            event_type: GitHub event type (e.g., 'push', 'pull_request').
            payload: Webhook payload.

        Returns:
            List of triggered run IDs.
        """
        triggered_runs = []

        # Map GitHub events to trigger types
        trigger_mapping = {
            "push": TriggerType.PUSH,
            "pull_request": TriggerType.PULL_REQUEST,
            "create": TriggerType.TAG,  # tag creation
            "release": TriggerType.RELEASE,
        }

        trigger_type = trigger_mapping.get(event_type)
        if trigger_type is None:
            return []

        # Extract event details
        commit_sha = None
        branch = None
        tag = None
        pr_number = None

        if event_type == "push":
            ref = payload.get("ref", "")
            if ref.startswith("refs/heads/"):
                branch = ref.replace("refs/heads/", "")
            elif ref.startswith("refs/tags/"):
                tag = ref.replace("refs/tags/", "")
            commit_sha = payload.get("after")

        elif event_type == "pull_request":
            pr = payload.get("pull_request", {})
            pr_number = pr.get("number")
            branch = pr.get("head", {}).get("ref")
            commit_sha = pr.get("head", {}).get("sha")

        elif event_type == "create":
            ref_type = payload.get("ref_type")
            if ref_type == "tag":
                tag = payload.get("ref")
            elif ref_type == "branch":
                branch = payload.get("ref")

        elif event_type == "release":
            release = payload.get("release", {})
            tag = release.get("tag_name")

        # Find matching pipelines
        for pipeline in self.registry.list(enabled_only=True):
            if not self._matches_trigger(pipeline, trigger_type):
                continue

            if not self._matches_filters(pipeline, branch=branch, tag=tag):
                continue

            # Trigger the pipeline
            run = await self.engine.execute(
                pipeline_name=pipeline.name,
                trigger=trigger_type,
                commit_sha=commit_sha,
                branch=branch,
                tag=tag,
                pr_number=pr_number,
                triggered_by="github-webhook",
            )
            triggered_runs.append(run.id)

        return triggered_runs

    def _matches_trigger(self, pipeline: Pipeline, trigger_type: TriggerType) -> bool:
        """Check if a pipeline matches a trigger type.

        Args:
            pipeline: Pipeline to check.
            trigger_type: Trigger type to match.

        Returns:
            True if pipeline matches the trigger.
        """
        if not pipeline.triggers:
            # If no triggers specified, match all
            return True
        return trigger_type in pipeline.triggers

    def _matches_filters(
        self,
        pipeline: Pipeline,
        branch: str | None = None,
        tag: str | None = None,
    ) -> bool:
        """Check if a pipeline matches branch/tag filters.

        Args:
            pipeline: Pipeline to check.
            branch: Branch name (if applicable).
            tag: Tag name (if applicable).

        Returns:
            True if pipeline matches the filters.
        """
        # Check branch filter
        if branch and pipeline.branch_filter:
            if not any(self._matches_pattern(branch, pattern) for pattern in pipeline.branch_filter):
                return False

        # Check tag filter
        if tag and pipeline.tags_filter:
            if not any(self._matches_pattern(tag, pattern) for pattern in pipeline.tags_filter):
                return False

        return True

    def _matches_pattern(self, value: str, pattern: str) -> bool:
        """Check if a value matches a glob pattern.

        Args:
            value: Value to check.
            pattern: Glob pattern (supports * and **).

        Returns:
            True if value matches the pattern.
        """
        # Convert glob pattern to regex
        regex = pattern.replace("*", "[^/]*").replace("**", ".*")
        regex = f"^{regex}$"
        return re.match(regex, value) is not None
