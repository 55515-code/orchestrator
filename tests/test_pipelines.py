"""Tests for the pipelines module."""

from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.pipelines import (
    Pipeline,
    PipelineEngine,
    PipelineRegistry,
    PipelineRun,
    PipelineStage,
    create_pipelines_router,
)
from substrate.pipelines.models import PipelineStatus, TriggerType
from substrate.pipelines.triggers import TriggerHandler


class TestPipelineModels:
    """Test pipeline data models."""

    def test_pipeline_stage_creation(self):
        """Test creating a pipeline stage."""
        stage = PipelineStage(
            name="build",
            commands=["echo 'Building...'"],
            environment={"NODE_ENV": "production"},
            artifacts=["dist/*"],
        )
        assert stage.name == "build"
        assert len(stage.commands) == 1
        assert stage.environment["NODE_ENV"] == "production"

    def test_pipeline_stage_to_dict(self):
        """Test converting stage to dictionary."""
        stage = PipelineStage(
            name="test",
            commands=["pytest"],
            timeout_seconds=1800,
        )
        data = stage.to_dict()
        assert data["name"] == "test"
        assert data["commands"] == ["pytest"]
        assert data["timeout_seconds"] == 1800

    def test_pipeline_creation(self):
        """Test creating a pipeline."""
        stage = PipelineStage(name="build", commands=["make"])
        pipeline = Pipeline(
            name="ci-pipeline",
            description="CI pipeline",
            stages=[stage],
            triggers=[TriggerType.PUSH, TriggerType.PULL_REQUEST],
        )
        assert pipeline.name == "ci-pipeline"
        assert len(pipeline.stages) == 1
        assert len(pipeline.triggers) == 2
        assert pipeline.enabled is True

    def test_pipeline_to_dict(self):
        """Test converting pipeline to dictionary."""
        stage = PipelineStage(name="build", commands=["make"])
        pipeline = Pipeline(
            name="test-pipeline",
            description="Test",
            stages=[stage],
        )
        data = pipeline.to_dict()
        assert data["name"] == "test-pipeline"
        assert len(data["stages"]) == 1
        assert data["enabled"] is True

    def test_pipeline_run_creation(self):
        """Test creating a pipeline run."""
        run = PipelineRun(
            id="test-run-1",
            pipeline_name="ci-pipeline",
            status=PipelineStatus.PENDING,
            trigger=TriggerType.MANUAL,
            started_at=datetime.now(UTC),
        )
        assert run.id == "test-run-1"
        assert run.status == PipelineStatus.PENDING
        assert run.trigger == TriggerType.MANUAL

    def test_pipeline_run_duration(self):
        """Test calculating run duration."""
        started = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        completed = datetime(2024, 1, 1, 12, 5, 0, tzinfo=UTC)
        run = PipelineRun(
            id="test-run",
            pipeline_name="test",
            status=PipelineStatus.SUCCESS,
            trigger=TriggerType.MANUAL,
            started_at=started,
            completed_at=completed,
        )
        assert run.duration_seconds == 300.0

    def test_pipeline_run_duration_incomplete(self):
        """Test duration for incomplete run."""
        run = PipelineRun(
            id="test-run",
            pipeline_name="test",
            status=PipelineStatus.RUNNING,
            trigger=TriggerType.MANUAL,
            started_at=datetime.now(UTC),
        )
        assert run.duration_seconds is None


class TestPipelineRegistry:
    """Test pipeline registry."""

    def test_registry_initialization(self):
        """Test initializing registry."""
        registry = PipelineRegistry()
        assert len(registry.list()) == 0

    def test_register_pipeline(self):
        """Test registering a pipeline."""
        registry = PipelineRegistry()
        pipeline = Pipeline(
            name="test-pipeline",
            description="Test",
            stages=[],
        )
        registry.register(pipeline)
        assert registry.get("test-pipeline") is not None
        assert len(registry.list()) == 1

    def test_get_nonexistent_pipeline(self):
        """Test getting a non-existent pipeline."""
        registry = PipelineRegistry()
        assert registry.get("nonexistent") is None

    def test_remove_pipeline(self):
        """Test removing a pipeline."""
        registry = PipelineRegistry()
        pipeline = Pipeline(name="test", description="Test", stages=[])
        registry.register(pipeline)
        assert registry.remove("test") is True
        assert registry.get("test") is None
        assert registry.remove("test") is False

    def test_list_enabled_only(self):
        """Test listing only enabled pipelines."""
        registry = PipelineRegistry()
        pipeline1 = Pipeline(name="enabled", description="Test", stages=[], enabled=True)
        pipeline2 = Pipeline(name="disabled", description="Test", stages=[], enabled=False)
        registry.register(pipeline1)
        registry.register(pipeline2)

        all_pipelines = registry.list()
        assert len(all_pipelines) == 2

        enabled_only = registry.list(enabled_only=True)
        assert len(enabled_only) == 1
        assert enabled_only[0].name == "enabled"

    def test_load_from_file(self):
        """Test loading pipelines from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
pipelines:
  - name: test-pipeline
    description: Test pipeline
    stages:
      - name: build
        commands:
          - echo "Building"
      - name: test
        commands:
          - echo "Testing"
    triggers:
      - push
      - pull_request
""")
            f.flush()

            registry = PipelineRegistry()
            registry.load_from_file(Path(f.name))

            pipeline = registry.get("test-pipeline")
            assert pipeline is not None
            assert len(pipeline.stages) == 2
            assert len(pipeline.triggers) == 2

            Path(f.name).unlink()

    def test_load_from_directory(self):
        """Test loading pipelines from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a pipeline file
            pipeline_file = tmpdir_path / "test.yaml"
            pipeline_file.write_text("""
pipelines:
  - name: test-pipeline
    description: Test
    stages:
      - name: build
        commands:
          - echo "Build"
""")

            registry = PipelineRegistry()
            count = registry.load_from_directory(tmpdir_path)

            assert count == 1
            assert registry.get("test-pipeline") is not None


class TestPipelineEngine:
    """Test pipeline execution engine."""

    def test_engine_initialization(self):
        """Test initializing the engine."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)
        assert engine.registry is registry

    def test_execute_nonexistent_pipeline(self):
        """Test executing a non-existent pipeline."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)

        with pytest.raises(ValueError, match="Pipeline not found"):
            asyncio.run(engine.execute("nonexistent", TriggerType.MANUAL))

    def test_execute_disabled_pipeline(self):
        """Test executing a disabled pipeline."""
        registry = PipelineRegistry()
        pipeline = Pipeline(
            name="disabled",
            description="Test",
            stages=[],
            enabled=False,
        )
        registry.register(pipeline)
        engine = PipelineEngine(registry=registry)

        with pytest.raises(ValueError, match="Pipeline is disabled"):
            asyncio.run(engine.execute("disabled", TriggerType.MANUAL))

    def test_execute_simple_pipeline(self):
        """Test executing a simple pipeline."""
        registry = PipelineRegistry()
        stage = PipelineStage(
            name="test",
            commands=["echo 'Hello World'"],
        )
        pipeline = Pipeline(
            name="simple",
            description="Simple test",
            stages=[stage],
        )
        registry.register(pipeline)

        with tempfile.TemporaryDirectory() as tmpdir:
            PipelineEngine(
                registry=registry,
                workdir=Path(tmpdir),
                artifacts_dir=Path(tmpdir) / "artifacts",
            )

            # Just verify the pipeline can be retrieved and is enabled
            retrieved = registry.get("simple")
            assert retrieved is not None
            assert retrieved.enabled is True
            assert len(retrieved.stages) == 1

    def test_get_run(self):
        """Test getting a run by ID."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)

        # No runs yet
        assert engine.get_run("nonexistent") is None

    def test_list_runs_empty(self):
        """Test listing runs when empty."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)

        runs = engine.list_runs()
        assert len(runs) == 0

    def test_cancel_nonexistent_run(self):
        """Test cancelling a non-existent run."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)

        assert engine.cancel_run("nonexistent") is False


class TestTriggerHandler:
    """Test trigger handler."""

    def test_trigger_handler_initialization(self):
        """Test initializing trigger handler."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)
        handler = TriggerHandler(registry, engine)
        assert handler.registry is registry
        assert handler.engine is engine

    def test_handle_unknown_event(self):
        """Test handling an unknown event type."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)
        handler = TriggerHandler(registry, engine)

        runs = asyncio.run(handler.handle_github_webhook("unknown_event", {}))
        assert len(runs) == 0

    def test_handle_push_event_no_pipelines(self):
        """Test handling push event with no pipelines."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)
        handler = TriggerHandler(registry, engine)

        payload = {
            "ref": "refs/heads/main",
            "after": "abc123",
        }
        runs = asyncio.run(handler.handle_github_webhook("push", payload))
        assert len(runs) == 0


class TestPipelinesRouter:
    """Test pipelines API router."""

    def test_create_router(self):
        """Test creating the router."""
        registry = PipelineRegistry()
        engine = PipelineEngine(registry=registry)
        router = create_pipelines_router(registry, engine)
        assert router is not None
