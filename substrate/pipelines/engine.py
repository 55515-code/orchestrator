"""Pipeline execution engine.

Executes pipeline runs with proper stage sequencing,
environment setup, and artifact collection.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from .models import Pipeline, PipelineRun, PipelineStatus, TriggerType
from .registry import PipelineRegistry


class PipelineEngine:
    """Engine for executing pipeline runs.

    Manages the execution of pipelines, including stage sequencing,
    environment setup, and artifact collection.
    """

    def __init__(
        self,
        registry: PipelineRegistry,
        workdir: Path | None = None,
        artifacts_dir: Path | None = None,
    ) -> None:
        """Initialize the engine.

        Args:
            registry: Pipeline registry containing pipeline definitions.
            workdir: Working directory for pipeline execution.
            artifacts_dir: Directory for storing artifacts.
        """
        self.registry = registry
        self.workdir = workdir or Path.cwd()
        self.artifacts_dir = artifacts_dir or (self.workdir / "artifacts")
        self._runs: dict[str, PipelineRun] = {}

    async def execute(
        self,
        pipeline_name: str,
        trigger: TriggerType,
        commit_sha: str | None = None,
        branch: str | None = None,
        tag: str | None = None,
        pr_number: int | None = None,
        triggered_by: str | None = None,
        environment: dict[str, str] | None = None,
    ) -> PipelineRun:
        """Execute a pipeline.

        Args:
            pipeline_name: Name of the pipeline to execute.
            trigger: Type of trigger that initiated the run.
            commit_sha: Git commit SHA (if applicable).
            branch: Git branch name (if applicable).
            tag: Git tag name (if applicable).
            pr_number: Pull request number (if applicable).
            triggered_by: User or system that triggered the run.
            environment: Additional environment variables.

        Returns:
            PipelineRun object tracking the execution.

        Raises:
            ValueError: If pipeline not found or disabled.
        """
        pipeline = self.registry.get(pipeline_name)
        if pipeline is None:
            raise ValueError(f"Pipeline not found: {pipeline_name}")

        if not pipeline.enabled:
            raise ValueError(f"Pipeline is disabled: {pipeline_name}")

        # Create run
        run_id = str(uuid.uuid4())
        run = PipelineRun(
            id=run_id,
            pipeline_name=pipeline_name,
            status=PipelineStatus.PENDING,
            trigger=trigger,
            started_at=datetime.utcnow(),
            commit_sha=commit_sha,
            branch=branch,
            tag=tag,
            pr_number=pr_number,
            triggered_by=triggered_by,
            environment={**pipeline.environment, **(environment or {})},
        )

        self._runs[run_id] = run

        # Execute asynchronously
        asyncio.create_task(self._execute_pipeline(run, pipeline))

        return run

    async def _execute_pipeline(self, run: PipelineRun, pipeline: Pipeline) -> None:
        """Execute a pipeline run.

        Args:
            run: Pipeline run to execute.
            pipeline: Pipeline definition.
        """
        run.status = PipelineStatus.RUNNING

        try:
            # Execute stages sequentially
            for stage in pipeline.stages:
                stage_success = await self._execute_stage(run, stage)

                if not stage_success and not stage.allow_failure:
                    run.status = PipelineStatus.FAILED
                    run.completed_at = datetime.utcnow()
                    return

            # All stages completed successfully
            run.status = PipelineStatus.SUCCESS
            run.completed_at = datetime.utcnow()

        except Exception as exc:
            run.status = PipelineStatus.FAILED
            run.error = str(exc)
            run.completed_at = datetime.utcnow()

    async def _execute_stage(self, run: PipelineRun, stage) -> bool:
        """Execute a single pipeline stage.

        Args:
            run: Parent pipeline run.
            stage: Stage to execute.

        Returns:
            True if stage succeeded, False otherwise.
        """
        # Create stage log file
        log_dir = self.artifacts_dir / run.id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{stage.name}.log"

        run.logs[stage.name] = str(log_file)

        # Build environment
        env = {**run.environment, **stage.environment}

        try:
            with open(log_file, "w", encoding="utf-8") as log:
                for command in stage.commands:
                    log.write(f"$ {command}\n")
                    log.flush()

                    process = await asyncio.create_subprocess_shell(
                        command,
                        cwd=self.workdir,
                        env=env,
                        stdout=log,
                        stderr=log,
                    )

                    try:
                        return_code = await asyncio.wait_for(
                            process.wait(),
                            timeout=stage.timeout_seconds,
                        )
                    except TimeoutError:
                        process.kill()
                        log.write(f"\n[TIMEOUT] Stage timed out after {stage.timeout_seconds}s\n")
                        return False

                    log.write(f"[EXIT CODE: {return_code}]\n\n")

                    if return_code != 0:
                        return False

            # Collect artifacts
            for artifact_pattern in stage.artifacts:
                for artifact_path in self.workdir.glob(artifact_pattern):
                    artifact_dest = log_dir / artifact_path.name
                    if artifact_path.is_file():
                        artifact_dest.write_bytes(artifact_path.read_bytes())
                        run.artifacts.append(str(artifact_dest))

            return True

        except Exception as exc:
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(f"\n[ERROR] {exc}\n")
            return False

    def get_run(self, run_id: str) -> PipelineRun | None:
        """Get a pipeline run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            PipelineRun if found, None otherwise.
        """
        return self._runs.get(run_id)

    def list_runs(
        self,
        pipeline_name: str | None = None,
        status: PipelineStatus | None = None,
        limit: int = 100,
    ) -> list[PipelineRun]:
        """List pipeline runs.

        Args:
            pipeline_name: Filter by pipeline name.
            status: Filter by status.
            limit: Maximum number of runs to return.

        Returns:
            List of pipeline runs.
        """
        runs = list(self._runs.values())

        if pipeline_name:
            runs = [r for r in runs if r.pipeline_name == pipeline_name]

        if status:
            runs = [r for r in runs if r.status == status]

        # Sort by start time, most recent first
        runs.sort(key=lambda r: r.started_at, reverse=True)

        return runs[:limit]

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running pipeline.

        Args:
            run_id: Run identifier.

        Returns:
            True if cancelled, False if not found or already completed.
        """
        run = self._runs.get(run_id)
        if run is None:
            return False

        if run.status not in (PipelineStatus.PENDING, PipelineStatus.RUNNING):
            return False

        run.status = PipelineStatus.CANCELLED
        run.completed_at = datetime.utcnow()
        return True
