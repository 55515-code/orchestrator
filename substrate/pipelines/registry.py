"""Pipeline registry for managing pipeline definitions.

Loads and manages pipeline configurations from YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Pipeline, PipelineStage, TriggerType


class PipelineRegistry:
    """Registry for pipeline definitions.

    Loads pipelines from YAML configuration files and provides
    lookup and filtering capabilities.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._pipelines: dict[str, Pipeline] = {}

    def register(self, pipeline: Pipeline) -> None:
        """Register a pipeline definition.

        Args:
            pipeline: Pipeline to register.
        """
        self._pipelines[pipeline.name] = pipeline

    def get(self, name: str) -> Pipeline | None:
        """Get a pipeline by name.

        Args:
            name: Pipeline name.

        Returns:
            Pipeline if found, None otherwise.
        """
        return self._pipelines.get(name)

    def list(self, enabled_only: bool = False) -> list[Pipeline]:
        """List all registered pipelines.

        Args:
            enabled_only: If True, only return enabled pipelines.

        Returns:
            List of pipelines.
        """
        pipelines = list(self._pipelines.values())
        if enabled_only:
            pipelines = [p for p in pipelines if p.enabled]
        return pipelines

    def remove(self, name: str) -> bool:
        """Remove a pipeline from the registry.

        Args:
            name: Pipeline name.

        Returns:
            True if removed, False if not found.
        """
        if name in self._pipelines:
            del self._pipelines[name]
            return True
        return False

    def load_from_file(self, path: Path) -> None:
        """Load pipelines from a YAML file.

        Args:
            path: Path to YAML file.
        """
        if not path.exists():
            raise FileNotFoundError(f"Pipeline file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid pipeline file: {path}")

        pipelines_data = data.get("pipelines", [])
        if not isinstance(pipelines_data, list):
            raise ValueError(f"Invalid pipelines list in: {path}")

        for pipeline_data in pipelines_data:
            pipeline = self._parse_pipeline(pipeline_data)
            self.register(pipeline)

    def load_from_directory(self, directory: Path) -> int:
        """Load all pipeline files from a directory.

        Args:
            directory: Directory containing pipeline YAML files.

        Returns:
            Number of pipelines loaded.
        """
        if not directory.exists() or not directory.is_dir():
            return 0

        count = 0
        for path in directory.glob("*.yaml"):
            self.load_from_file(path)
            count += 1

        for path in directory.glob("*.yml"):
            self.load_from_file(path)
            count += 1

        return count

    def _parse_pipeline(self, data: dict[str, Any]) -> Pipeline:
        """Parse a pipeline from dictionary data.

        Args:
            data: Pipeline data dictionary.

        Returns:
            Parsed Pipeline object.
        """
        name = data.get("name")
        if not name:
            raise ValueError("Pipeline must have a 'name' field")

        description = data.get("description", "")

        # Parse stages
        stages_data = data.get("stages", [])
        stages = [self._parse_stage(s) for s in stages_data]

        # Parse triggers
        triggers_data = data.get("triggers", [])
        triggers = [TriggerType(t) for t in triggers_data if t in TriggerType.__members__.values()]

        # Parse filters
        branch_filter = data.get("branch_filter", [])
        tags_filter = data.get("tags_filter", [])

        # Parse environment
        environment = data.get("environment", {})

        # Parse timeout
        timeout_seconds = data.get("timeout_seconds", 7200)

        # Parse enabled
        enabled = data.get("enabled", True)

        return Pipeline(
            name=name,
            description=description,
            stages=stages,
            triggers=triggers,
            branch_filter=branch_filter,
            tags_filter=tags_filter,
            environment=environment,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
        )

    def _parse_stage(self, data: dict[str, Any]) -> PipelineStage:
        """Parse a pipeline stage from dictionary data.

        Args:
            data: Stage data dictionary.

        Returns:
            Parsed PipelineStage object.
        """
        name = data.get("name")
        if not name:
            raise ValueError("Stage must have a 'name' field")

        commands = data.get("commands", [])
        if not isinstance(commands, list):
            commands = [commands]

        environment = data.get("environment", {})
        artifacts = data.get("artifacts", [])
        timeout_seconds = data.get("timeout_seconds", 3600)
        allow_failure = data.get("allow_failure", False)

        return PipelineStage(
            name=name,
            commands=commands,
            environment=environment,
            artifacts=artifacts,
            timeout_seconds=timeout_seconds,
            allow_failure=allow_failure,
        )
