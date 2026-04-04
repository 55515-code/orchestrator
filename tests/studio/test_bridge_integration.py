from __future__ import annotations

from pathlib import Path

from substrate.orchestrator import Orchestrator, ScheduledJobSpec
from substrate.registry import SubstrateRuntime
from substrate.studio.db import init_database
from substrate.studio.models import AppConfig, Job
from substrate.studio.runner import execute_job


def _write_workspace(root: Path) -> None:
    (root / "workspace.yaml").write_text(
        """
version: 1
policy:
  default_mode: observe
  require_source_facts_before_mutation: false
  source_freshness_days: 30
  enforce_stage_flow: true
  stage_sequence:
    - local
    - hosted_dev
    - production
  pass_sequence:
    - research
    - development
    - testing
scheduler:
  enabled: true
  default_repo_slug: substrate-core
  default_stage: local
  windows_features_enabled: false
  windows_app_mode_enabled: false
repositories:
  - slug: substrate-core
    path: .
    allow_mutations: true
    default_mode: observe
    tasks: {}
""".strip(),
        encoding="utf-8",
    )


def test_scheduled_exec_records_scheduler_and_orchestrator_lineage(
    tmp_path: Path, monkeypatch
) -> None:
    _write_workspace(tmp_path)
    runtime = SubstrateRuntime(tmp_path)
    orchestrator = Orchestrator(runtime)
    session_factory, _ = init_database(f"sqlite:///{tmp_path / 'studio.db'}")
    run_root = tmp_path / "studio-runs"
    run_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "substrate.studio.runner.build_codex_command",
        lambda job, final_message_path, prompt=None: [
            "codex-placeholder",
            "-c",
            "print('bridge-ok')",
        ],
    )

    with session_factory() as session:
        session.add(
            AppConfig(
                id=1,
                codex_executable="python",
                default_working_directory=str(tmp_path),
            )
        )
        session.add(
            Job(
                name="bridge-success",
                mode="exec",
                enabled=True,
                schedule_type="interval",
                interval_minutes=5,
                prompt="bridge integration",
                sandbox="read-only",
                repo_slug="substrate-core",
                stage="local",
                requested_mode="observe",
                allow_mutations=False,
                allow_stage_skip=False,
                working_directory=".",
                timeout_seconds=120,
            )
        )
        session.commit()
        job = session.query(Job).filter(Job.name == "bridge-success").one()

        run = execute_job(session, job, run_root, orchestrator)

    assert run.status == "completed"
    assert run.orchestrator_run_id is not None

    orchestrator_run = runtime.db.get_run(run.orchestrator_run_id)
    assert orchestrator_run is not None
    assert orchestrator_run["status"] == "success"
    assert runtime.db.list_run_events(run.orchestrator_run_id)

    checkpoint_path = (
        runtime.paths["memory"]
        / "reliability"
        / "checkpoints"
        / f"{run.orchestrator_run_id}.jsonl"
    )
    assert checkpoint_path.exists()


def test_scheduled_job_stage_policy_blocks_without_prerequisite(tmp_path: Path) -> None:
    _write_workspace(tmp_path)
    runtime = SubstrateRuntime(tmp_path)
    orchestrator = Orchestrator(runtime)

    blocked = orchestrator.run_scheduled_job(
        spec=ScheduledJobSpec(
            repo_slug="substrate-core",
            stage="hosted_dev",
            requested_mode="observe",
            allow_mutations=False,
            allow_stage_skip=False,
            command=["python", "-c", "print('blocked')"],
            workdir=".",
        )
    )
    assert blocked.status == "failed"
    assert runtime.db.get_run(blocked.run_id) is None

    bypassed = orchestrator.run_scheduled_job(
        spec=ScheduledJobSpec(
            repo_slug="substrate-core",
            stage="hosted_dev",
            requested_mode="observe",
            allow_mutations=False,
            allow_stage_skip=True,
            command=["python", "-c", "print('ok')"],
            workdir=".",
        )
    )
    assert bypassed.status == "success"
    assert runtime.db.get_run(bypassed.run_id) is not None
