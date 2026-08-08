"""FastAPI router for pipeline endpoints.

Provides REST API for managing pipelines, triggering runs,
and viewing run status.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .engine import PipelineEngine
from .models import PipelineStatus, TriggerType
from .registry import PipelineRegistry
from .triggers import TriggerHandler


class ManualTriggerRequest(BaseModel):
    """Request body for manual pipeline trigger."""

    branch: str | None = None
    tag: str | None = None
    environment: dict[str, str] | None = None


def create_pipelines_router(
    registry: PipelineRegistry,
    engine: PipelineEngine,
) -> APIRouter:
    """Create the pipelines API router.

    Args:
        registry: Pipeline registry.
        engine: Pipeline execution engine.

    Returns:
        Configured FastAPI router.
    """
    router = APIRouter(prefix="/pipelines", tags=["pipelines"])
    trigger_handler = TriggerHandler(registry, engine)

    @router.get("/")
    async def list_pipelines(enabled_only: bool = False) -> dict[str, Any]:
        """List all registered pipelines.

        Args:
            enabled_only: If True, only return enabled pipelines.

        Returns:
            Dictionary of pipelines.
        """
        pipelines = registry.list(enabled_only=enabled_only)
        return {
            "pipelines": [p.to_dict() for p in pipelines],
            "count": len(pipelines),
        }

    @router.get("/{pipeline_name}")
    async def get_pipeline(pipeline_name: str) -> dict[str, Any]:
        """Get a pipeline by name.

        Args:
            pipeline_name: Pipeline name.

        Returns:
            Pipeline definition.
        """
        pipeline = registry.get(pipeline_name)
        if pipeline is None:
            raise HTTPException(status_code=404, detail="Pipeline not found")
        return pipeline.to_dict()

    @router.post("/{pipeline_name}/trigger")
    async def trigger_pipeline(
        pipeline_name: str,
        request: ManualTriggerRequest | None = None,
    ) -> dict[str, Any]:
        """Manually trigger a pipeline.

        Args:
            pipeline_name: Pipeline name.
            request: Optional trigger parameters.

        Returns:
            Triggered run information.
        """
        request = request or ManualTriggerRequest()

        try:
            run = await engine.execute(
                pipeline_name=pipeline_name,
                trigger=TriggerType.MANUAL,
                branch=request.branch,
                tag=request.tag,
                triggered_by="manual",
                environment=request.environment,
            )
            return {
                "status": "ok",
                "run_id": run.id,
                "pipeline": pipeline_name,
                "status_url": f"/pipelines/runs/{run.id}",
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        """Get a pipeline run by ID.

        Args:
            run_id: Run identifier.

        Returns:
            Run information.
        """
        run = engine.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run.to_dict()

    @router.get("/runs")
    async def list_runs(
        pipeline_name: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List pipeline runs.

        Args:
            pipeline_name: Filter by pipeline name.
            status: Filter by status.
            limit: Maximum number of runs to return.

        Returns:
            List of runs.
        """
        status_enum = None
        if status:
            try:
                status_enum = PipelineStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        runs = engine.list_runs(
            pipeline_name=pipeline_name,
            status=status_enum,
            limit=min(limit, 500),
        )
        return {
            "runs": [r.to_dict() for r in runs],
            "count": len(runs),
        }

    @router.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: str) -> dict[str, Any]:
        """Cancel a running pipeline.

        Args:
            run_id: Run identifier.

        Returns:
            Cancellation status.
        """
        if engine.cancel_run(run_id):
            return {"status": "ok", "run_id": run_id}
        raise HTTPException(status_code=400, detail="Run cannot be cancelled")

    @router.post("/webhook/github")
    async def github_webhook(request: Request) -> dict[str, Any]:
        """Handle GitHub webhook events.

        Args:
            request: Incoming webhook request.

        Returns:
            Triggered run IDs.
        """
        event_type = request.headers.get("X-GitHub-Event")
        if not event_type:
            raise HTTPException(status_code=400, detail="Missing X-GitHub-Event header")

        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        run_ids = await trigger_handler.handle_github_webhook(event_type, payload)

        return {
            "status": "ok",
            "triggered_runs": run_ids,
            "count": len(run_ids),
        }

    @router.get("/runs/{run_id}/logs/{stage_name}")
    async def get_stage_logs(run_id: str, stage_name: str) -> dict[str, Any]:
        """Get logs for a specific stage.

        Args:
            run_id: Run identifier.
            stage_name: Stage name.

        Returns:
            Stage logs.
        """
        run = engine.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")

        log_path = run.logs.get(stage_name)
        if not log_path:
            raise HTTPException(status_code=404, detail="Stage logs not found")

        try:
            from pathlib import Path

            log_file = Path(log_path)
            if not log_file.exists():
                raise HTTPException(status_code=404, detail="Log file not found")

            content = log_file.read_text(encoding="utf-8")
            return {
                "run_id": run_id,
                "stage": stage_name,
                "logs": content,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
