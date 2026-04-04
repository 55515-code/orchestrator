from __future__ import annotations

import json
import os
import shlex
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from substrate.orchestrator import Orchestrator, ScheduledJobSpec

from .cloud_exec import classify_cloud_failure
from .models import AppConfig, Job, RunRecord
from .notification_service import build_cloud_summary_prompt, send_run_notification
from .security import load_secret


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_codex_command(
    job: Job, final_message_path: Path, prompt: str | None = None
) -> list[str]:
    effective_prompt = prompt if prompt is not None else job.prompt
    args = _parse_args(job.codex_args)
    if job.mode == "exec":
        command = [
            "codex",
            "exec",
            "--sandbox",
            job.sandbox or "read-only",
            "--json",
            "--output-last-message",
            str(final_message_path),
        ]
        command.extend(args)
        command.append(effective_prompt)
        return command
    command = [
        "codex",
        "cloud",
        "exec",
        "--env",
        job.cloud_env_id or "",
        "--attempts",
        str(job.attempts or 1),
    ]
    command.extend(args)
    command.append(effective_prompt)
    return command


def _parse_args(codex_args: str | None) -> list[str]:
    if not codex_args:
        return []
    try:
        parsed = json.loads(codex_args)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        return shlex.split(codex_args)
    return []


def _parse_env_map(env_json: str | None) -> dict[str, str]:
    if not env_json:
        return {}
    try:
        parsed = json.loads(env_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def _effective_runtime(session: Session) -> AppConfig | None:
    return session.query(AppConfig).filter(AppConfig.id == 1).one_or_none()


def _resolved_cloud_env_id(job: Job, app_config: AppConfig | None) -> str:
    if job.cloud_env_id:
        return job.cloud_env_id
    if app_config and app_config.default_cloud_env_id:
        return app_config.default_cloud_env_id
    return ""


def _is_git_repository(path: Path) -> bool:
    candidate = path
    if not candidate.exists():
        return False
    if candidate.is_file():
        candidate = candidate.parent
    for probe in [candidate, *candidate.parents]:
        if (probe / ".git").exists():
            return True
    return False


def execute_job(
    session: Session,
    job: Job,
    run_root: Path,
    orchestrator: Orchestrator,
) -> RunRecord:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = run_root / f"job_{job.id}" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    final_message_path = run_dir / "final_message.txt"
    stdout_path = run_dir / ("events.jsonl" if job.mode == "exec" else "stdout.log")
    stderr_path = run_dir / "stderr.log"
    metadata_path = run_dir / "run_metadata.json"

    app_config = _effective_runtime(session)
    if job.mode == "cloud_exec":
        job.cloud_env_id = _resolved_cloud_env_id(job, app_config)
    execution_prompt = job.prompt
    if job.mode == "cloud_exec" and bool(job.notify_email_enabled):
        execution_prompt = build_cloud_summary_prompt(job.prompt)
    command = build_codex_command(job, final_message_path, execution_prompt)
    executable = (
        app_config.codex_executable.strip()
        if app_config and app_config.codex_executable
        else "codex"
    )
    command[0] = executable
    executable_available = bool(shutil.which(executable) or Path(executable).is_file())

    env = dict(os.environ)
    if app_config:
        if app_config.codex_home:
            env["CODEX_HOME"] = app_config.codex_home
        env.update(_parse_env_map(app_config.global_env_json))
        if app_config.api_key_secret_ref and app_config.api_key_env_var:
            secret = load_secret(app_config.api_key_secret_ref)
            if secret:
                env[app_config.api_key_env_var] = secret
    env.update(_parse_env_map(job.env_json))

    working_dir_base = (
        app_config.default_working_directory
        if app_config and app_config.default_working_directory
        else "."
    )
    working_dir = Path(job.working_directory or working_dir_base).resolve()
    if (
        job.mode == "exec"
        and "--skip-git-repo-check" not in command
        and not _is_git_repository(working_dir)
    ):
        command.insert(len(command) - 1, "--skip-git-repo-check")

    run = RunRecord(
        job_id=job.id,
        status="running",
        command=shlex.join(command),
        started_at=utcnow_naive(),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        metadata_path=str(metadata_path),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    status = "failed"
    return_code: int | None = None
    message = ""
    error_text = ""
    failure_category: str | None = None
    diagnostic_code: str | None = None
    retryable = False
    cloud_output: str | None = None
    output_blob = ""
    orchestrator_run_id: str | None = None
    orchestrator_status: str | None = None
    orchestrator_artifact: str | None = None

    try:
        if not executable_available:
            raise FileNotFoundError(executable)
        bridge_result = orchestrator.run_scheduled_job(
            spec=ScheduledJobSpec(
                repo_slug=job.repo_slug or "substrate-core",
                stage=job.stage or "local",
                requested_mode=job.requested_mode or "mutate",
                command=command,
                workdir=str(working_dir),
                allow_mutations=bool(job.allow_mutations),
                allow_stage_skip=bool(job.allow_stage_skip),
                timeout_seconds=float(job.timeout_seconds or 1800),
                env=env,
                description=f"Scheduler job '{job.name}'",
            )
        )
        orchestrator_run_id = bridge_result.run_id
        orchestrator_status = bridge_result.status
        orchestrator_artifact = bridge_result.artifact_path
        return_code = bridge_result.exit_code
        status = "completed" if bridge_result.status == "success" else "failed"
        error_text = bridge_result.error_text or ""

        if orchestrator_artifact and Path(orchestrator_artifact).exists():
            output_blob = Path(orchestrator_artifact).read_text(
                encoding="utf-8", errors="ignore"
            )
    except FileNotFoundError:
        status = "failed"
        return_code = 127
        failure_category = "env_missing"
        diagnostic_code = "missing_executable"
        error_text = (
            f"Codex executable '{executable}' was not found. "
            "Update Execution Settings > Codex Executable or install Codex CLI in this runtime."
        )

    stdout_path.write_text(output_blob, encoding="utf-8")
    stderr_path.write_text(error_text, encoding="utf-8")

    if final_message_path.exists():
        message = final_message_path.read_text(encoding="utf-8", errors="ignore").strip()[
            :4000
        ]
    elif error_text:
        message = error_text
    elif status != "completed" and output_blob:
        message = output_blob[-4000:]

    if job.mode == "cloud_exec":
        cloud_output = output_blob
        if status != "completed":
            cloud_failure = classify_cloud_failure(message or output_blob, return_code)
            failure_category = cloud_failure.category
            retryable = bool(cloud_failure.retryable)
            diagnostic_code = cloud_failure.category
    elif status != "completed":
        failure_category = failure_category or "unknown"
        diagnostic_code = diagnostic_code or "uncategorized_failure"

    finished_at = utcnow_naive()
    run.status = status
    run.return_code = return_code
    run.finished_at = finished_at
    run.message = message
    run.failure_category = failure_category
    run.diagnostic_code = diagnostic_code
    run.retryable = retryable
    run.orchestrator_run_id = orchestrator_run_id
    run.orchestrator_status = orchestrator_status
    run.orchestrator_artifact = orchestrator_artifact

    if app_config:
        notification_result = send_run_notification(
            config=app_config,
            job=job,
            run=run,
            cloud_output=cloud_output,
        )
    else:
        notification_result = {
            "status": "skipped",
            "error": "runtime_config_missing",
            "recipient": None,
            "sent_at": None,
        }
    run.notification_status = notification_result.get("status") or "skipped"
    run.notification_error = notification_result.get("error")
    run.notification_recipient = notification_result.get("recipient")
    run.notification_sent_at = notification_result.get("sent_at")

    payload = {
        "job_id": job.id,
        "status": status,
        "return_code": return_code,
        "failure_category": failure_category,
        "diagnostic_code": diagnostic_code,
        "retryable": retryable,
        "orchestrator_run_id": orchestrator_run_id,
        "orchestrator_status": orchestrator_status,
        "orchestrator_artifact": orchestrator_artifact,
        "notification_status": run.notification_status,
        "notification_error": run.notification_error,
        "notification_recipient": run.notification_recipient,
        "notification_sent_at_utc": run.notification_sent_at.isoformat()
        if run.notification_sent_at
        else None,
        "started_at_utc": run.started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "command": command,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "final_message_path": str(final_message_path),
    }
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    job.last_run_at = finished_at
    job.last_status = status
    job.last_message = message[:1000] if message else None
    job.updated_at = finished_at

    session.add(run)
    session.add(job)
    session.commit()
    session.refresh(run)
    return run
