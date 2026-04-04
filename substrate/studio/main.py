from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.requests import Request

from substrate.orchestrator import Orchestrator
from substrate.registry import SubstrateRuntime

from .connection import codex_diagnostics, start_device_auth, test_connection
from .db import init_database
from .deployment import DeploymentRequest, get_task_status, install_headless_task, uninstall_headless_task
from .models import AppConfig, Job, RunRecord
from .notification_service import DEFAULT_NOTIFICATION_TO, compute_notification_readiness, send_test_notification
from .preflight import run_preflight
from .rc2.services.cloud_service import assert_cloud_readiness, compute_cloud_readiness
from .rc2.services.cloud_service import discover_cloud_targets
from .rc2.services.connection_service import build_connection_status, next_backoff_seconds, remaining_auth_cooldown_seconds
from .rc2.services.run_service import execute_now
from .rc2.services.settings_service import apply_runtime_defaults, apply_settings_update, ensure_app_config, to_settings_out, utcnow_naive
from .runtime_config import DEFAULT_VERSION, RuntimeOptions, load_json, normalize_channel
from .scheduler_service import SchedulerService
from .schemas import (
    ApiKeyPayload,
    ConnectionModePayload,
    ConnectionStatusOut,
    CloudReadinessOut,
    CloudTargetsOut,
    DeviceAuthStartOut,
    DeploymentInstallPayload,
    JobCreate,
    JobOut,
    JobUpdate,
    NotificationReadinessOut,
    NotificationTestOut,
    NotificationTestPayload,
    PreflightOut,
    RunOut,
    SmtpPasswordPayload,
    SettingsOut,
    SettingsUpdate,
    SystemRuntimeOut,
    SystemUpdateStatusOut,
)
from .security import clear_secret, save_secret
from .windows_integration import windows_app_mode_install, windows_app_mode_uninstall, windows_host_start, windows_host_stop


class TogglePayload(BaseModel):
    enabled: bool


def _default_runtime_options(project_root: Path) -> RuntimeOptions:
    return RuntimeOptions(mode="server", channel="stable", host="127.0.0.1", port=8787, version=DEFAULT_VERSION)


def _packaged_backend_runtime_status(options: RuntimeOptions) -> tuple[str, str | None]:
    status_override = (os.getenv("CODEX_PACKAGED_BACKEND_STATUS") or "").strip().lower()
    diagnostic_override = (os.getenv("CODEX_PACKAGED_BACKEND_DIAGNOSTIC") or "").strip() or None
    if status_override in {"ok", "blocked", "unavailable"}:
        return status_override, diagnostic_override
    if not options.desktop_mode:
        return "unavailable", None
    if options.bundled_codex_executable and Path(options.bundled_codex_executable).is_file():
        return "ok", None
    return "unavailable", "desktop_packaged_backend_unavailable"


def create_app(
    start_scheduler: bool = True,
    db_url: str | None = None,
    runtime_options: RuntimeOptions | None = None,
    runtime: SubstrateRuntime | None = None,
    orchestrator: Orchestrator | None = None,
    static_mount_path: str = "/studio-static",
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.runtime_options.desktop_mode:
            app.state.runtime_options.write_desktop_state(project_root, healthy=True)
        if start_scheduler and os.getenv("CODEX_SCHEDULER_DISABLE_AUTOSTART", "0") != "1":
            app.state.scheduler_service.start()
        try:
            yield
        finally:
            app.state.scheduler_service.shutdown()
            if app.state.runtime_options.desktop_mode:
                app.state.runtime_options.write_desktop_state(project_root, healthy=False)

    app = FastAPI(title="Codex Scheduler Studio", version="0.1.0-rc1", lifespan=lifespan)
    base_dir = Path(__file__).resolve().parent
    resolved_runtime = runtime or SubstrateRuntime(base_dir.parent)
    resolved_orchestrator = orchestrator or Orchestrator(resolved_runtime)
    project_root = resolved_runtime.root
    resolved_runtime_options = runtime_options or _default_runtime_options(project_root)
    resolved_runtime_options.channel = normalize_channel(resolved_runtime_options.channel)
    resolved_runtime_options.ensure_directories(project_root)
    run_root = resolved_runtime_options.run_root(project_root)
    if not resolved_runtime_options.desktop_mode:
        run_root = resolved_runtime.paths["memory"] / "studio-runs"
    run_root.mkdir(parents=True, exist_ok=True)

    if db_url:
        effective_db_url = db_url
    else:
        env_db = os.getenv("CODEX_SCHEDULER_DB")
        if env_db:
            effective_db_url = env_db
        elif resolved_runtime_options.desktop_mode:
            effective_db_url = resolved_runtime_options.default_db_url(project_root)
        else:
            effective_db_url = f"sqlite:///{resolved_runtime.paths['state'] / 'studio_scheduler.db'}"
    session_factory, _ = init_database(effective_db_url)
    scheduler_service = SchedulerService(
        session_factory=session_factory,
        run_root=run_root,
        orchestrator=resolved_orchestrator,
    )

    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount(
        static_mount_path,
        StaticFiles(directory=str(base_dir / "static")),
        name="studio-static",
    )

    app.state.session_factory = session_factory
    app.state.scheduler_service = scheduler_service
    app.state.run_root = run_root
    app.state.runtime_options = resolved_runtime_options
    app.state.runtime = resolved_runtime
    app.state.orchestrator = resolved_orchestrator

    with session_factory() as bootstrap_session:
        config = ensure_app_config(bootstrap_session)
        config = apply_runtime_defaults(config, resolved_runtime_options, project_root)
        bootstrap_session.add(config)
        bootstrap_session.commit()

    def get_session() -> Session:
        with app.state.session_factory() as session:
            yield session

    def require_desktop_session(request: Request) -> None:
        options: RuntimeOptions = app.state.runtime_options
        if not options.desktop_mode:
            return
        expected = options.session_token or ""
        if not expected:
            raise HTTPException(status_code=409, detail="Desktop session token is not configured.")
        if request.cookies.get("codex_desktop_session") != expected:
            raise HTTPException(status_code=403, detail="Desktop session is not established.")

    def _render_index_template(request: Request) -> HTMLResponse:
        # Keep compatibility with Starlette/Jinja API changes across releases.
        try:
            return templates.TemplateResponse(request=request, name="index.html")
        except TypeError:
            return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return _render_index_template(request)

    @app.get("/desktop/bootstrap")
    def desktop_bootstrap(token: str, request: Request) -> RedirectResponse:
        if not app.state.runtime_options.desktop_mode:
            raise HTTPException(status_code=404, detail="Desktop bootstrap is only available in desktop mode.")
        if token != (app.state.runtime_options.session_token or ""):
            raise HTTPException(status_code=403, detail="Desktop bootstrap token is invalid.")
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="codex_desktop_session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return response

    @app.get("/api/health")
    def health(session: Session = Depends(get_session)) -> dict[str, str | bool]:
        config = ensure_app_config(session)
        checks = run_preflight(config.codex_executable)
        has_errors = any(check.status == "error" for check in checks)
        return {
            "status": "degraded" if has_errors else "ok",
            "time": utcnow_naive().isoformat(),
            "preflight_ok": not has_errors,
        }

    @app.get("/api/system/runtime", response_model=SystemRuntimeOut)
    def system_runtime() -> SystemRuntimeOut:
        options: RuntimeOptions = app.state.runtime_options
        project_data_dir = options.resolved_data_dir(project_root) if options.desktop_mode else None
        packaged_backend_status, diagnostic_code = _packaged_backend_runtime_status(options)
        return SystemRuntimeOut(
            mode=options.mode,
            channel=options.channel,
            version=options.version,
            update_capable=bool(options.update_base_url),
            bundled_codex_cli=bool(options.bundled_codex_executable),
            data_dir=str(project_data_dir) if project_data_dir else None,
            packaged_backend_status=packaged_backend_status,
            diagnostic_code=diagnostic_code,
        )

    @app.post("/api/system/restart-backend")
    def system_restart_backend(request: Request) -> dict[str, str | bool]:
        require_desktop_session(request)
        options: RuntimeOptions = app.state.runtime_options
        if not options.desktop_mode:
            raise HTTPException(status_code=409, detail="Backend restart is only available in desktop mode.")
        options.queue_restart(project_root)
        return {"accepted": True, "status": "queued"}

    @app.get("/api/system/update-status", response_model=SystemUpdateStatusOut)
    def system_update_status() -> SystemUpdateStatusOut:
        options: RuntimeOptions = app.state.runtime_options
        payload = load_json(options.update_status_path(project_root)) if options.desktop_mode else None
        return SystemUpdateStatusOut(
            channel=options.channel,
            enabled=bool(options.update_base_url),
            update_base_url=options.update_base_url,
            last_check_at=(payload or {}).get("last_check_at"),
            last_result=(payload or {}).get("last_result"),
            last_error=(payload or {}).get("last_error"),
        )

    @app.get("/api/preflight", response_model=PreflightOut)
    def preflight(session: Session = Depends(get_session)) -> PreflightOut:
        config = ensure_app_config(session)
        checks = run_preflight(config.codex_executable)
        has_errors = any(check.status == "error" for check in checks)
        return PreflightOut(
            status="error" if has_errors else "ok",
            checks=[
                {
                    "name": check.name,
                    "status": check.status,
                    "detail": check.detail,
                }
                for check in checks
            ],
        )

    @app.get("/api/settings", response_model=SettingsOut)
    def get_settings(session: Session = Depends(get_session)) -> SettingsOut:
        config = ensure_app_config(session)
        return to_settings_out(config)

    @app.put("/api/settings", response_model=SettingsOut)
    def update_settings(payload: SettingsUpdate, session: Session = Depends(get_session)) -> SettingsOut:
        config = ensure_app_config(session)
        config = apply_settings_update(config, payload)
        session.add(config)
        session.commit()
        session.refresh(config)
        return to_settings_out(config)

    @app.post("/api/connection/mode", response_model=SettingsOut)
    def set_connection_mode(payload: ConnectionModePayload, session: Session = Depends(get_session)) -> SettingsOut:
        config = ensure_app_config(session)
        if payload.auth_mode not in {"chatgpt_account", "api_key"}:
            raise HTTPException(status_code=422, detail="auth_mode must be chatgpt_account or api_key.")
        config.auth_mode = payload.auth_mode
        config.updated_at = utcnow_naive()
        session.add(config)
        session.commit()
        session.refresh(config)
        return to_settings_out(config)

    @app.get("/api/connection/status", response_model=ConnectionStatusOut)
    def connection_status(session: Session = Depends(get_session)) -> ConnectionStatusOut:
        config = ensure_app_config(session)
        diag = codex_diagnostics(config.codex_executable, config.codex_home)
        now = utcnow_naive()
        retry_after = remaining_auth_cooldown_seconds(config, now)
        return build_connection_status(config, diag, retry_after)

    @app.post("/api/connection/device-auth/start", response_model=DeviceAuthStartOut)
    def connection_start_device_auth(session: Session = Depends(get_session)) -> DeviceAuthStartOut:
        config = ensure_app_config(session)
        now = utcnow_naive()
        retry_after = remaining_auth_cooldown_seconds(config, now)
        if retry_after > 0:
            raise HTTPException(
                status_code=429,
                detail={
                    "message": "Device authentication is temporarily rate-limited. Please wait before retrying.",
                    "retry_after_seconds": retry_after,
                    "rate_limited_until": config.auth_rate_limited_until.isoformat() if config.auth_rate_limited_until else None,
                },
            )

        result = start_device_auth(config.codex_executable, config.codex_home)
        if result.get("rate_limited"):
            cooldown = int(result.get("retry_after_seconds") or next_backoff_seconds(config.auth_rate_limit_hits or 0))
            config.auth_rate_limit_hits = (config.auth_rate_limit_hits or 0) + 1
            config.auth_rate_limited_until = now + timedelta(seconds=max(1, cooldown))
            config.last_connection_status = "rate_limited"
            config.last_connection_message = (result.get("error") or result.get("raw_output") or "")[:1000]
            config.updated_at = now
            session.add(config)
            session.commit()
            raise HTTPException(
                status_code=429,
                detail={
                    "message": config.last_connection_message or "Device authentication is rate-limited.",
                    "retry_after_seconds": cooldown,
                    "rate_limited_until": config.auth_rate_limited_until.isoformat() if config.auth_rate_limited_until else None,
                },
            )

        config.last_connection_status = "started" if result.get("ok") else "error"
        if result.get("ok"):
            config.last_connection_message = "Sign-in link and one-time code generated. Complete sign-in in browser, then click Test Connection."
        else:
            config.last_connection_message = (result.get("error") or result.get("raw_output") or "")[:1000]
        if result.get("ok"):
            config.auth_rate_limited_until = None
            config.auth_rate_limit_hits = 0
        config.updated_at = now
        session.add(config)
        session.commit()
        return DeviceAuthStartOut(**result)

    @app.post("/api/connection/test")
    def connection_test(session: Session = Depends(get_session)) -> dict:
        config = ensure_app_config(session)
        result = test_connection(config.codex_executable, config.codex_home, config.default_working_directory)
        config.last_connection_status = "ok" if result.get("ok") else "failed"
        config.last_connection_message = (result.get("message") or result.get("output") or "")[:1000]
        config.updated_at = utcnow_naive()
        session.add(config)
        session.commit()
        return result

    @app.get("/api/cloud/readiness", response_model=CloudReadinessOut)
    def cloud_readiness(
        cloud_env_id: str | None = None,
        working_directory: str | None = None,
        session: Session = Depends(get_session),
    ) -> CloudReadinessOut:
        readiness = compute_cloud_readiness(
            session=session,
            config=ensure_app_config(session),
            cloud_env_id=cloud_env_id,
            working_directory=working_directory,
        )
        return CloudReadinessOut(**readiness)

    @app.get("/api/cloud/targets", response_model=CloudTargetsOut)
    def cloud_targets(
        working_directory: str | None = None,
        session: Session = Depends(get_session),
    ) -> CloudTargetsOut:
        targets = discover_cloud_targets(
            config=ensure_app_config(session),
            working_directory=working_directory,
        )
        return CloudTargetsOut(**targets)

    @app.post("/api/settings/api-key")
    def set_api_key(payload: ApiKeyPayload, session: Session = Depends(get_session)) -> dict[str, str]:
        config = ensure_app_config(session)
        secret_ref = config.api_key_secret_ref or "default_api_key"
        save_secret(secret_ref, payload.api_key.strip())
        if not config.api_key_secret_ref:
            config.api_key_secret_ref = secret_ref
        config.updated_at = utcnow_naive()
        session.add(config)
        session.commit()
        return {"status": "stored"}

    @app.delete("/api/settings/api-key")
    def delete_api_key(session: Session = Depends(get_session)) -> dict[str, str]:
        config = ensure_app_config(session)
        if config.api_key_secret_ref:
            clear_secret(config.api_key_secret_ref)
            config.api_key_secret_ref = None
            config.updated_at = utcnow_naive()
            session.add(config)
            session.commit()
        return {"status": "deleted"}

    @app.post("/api/settings/smtp-password")
    def set_smtp_password(payload: SmtpPasswordPayload, session: Session = Depends(get_session)) -> dict[str, str]:
        config = ensure_app_config(session)
        secret_value = payload.password.strip()
        if not secret_value:
            raise HTTPException(status_code=422, detail="SMTP password cannot be blank.")
        secret_ref = config.smtp_password_secret_ref or "default_smtp_password"
        save_secret(secret_ref, secret_value)
        if not config.smtp_password_secret_ref:
            config.smtp_password_secret_ref = secret_ref
        config.updated_at = utcnow_naive()
        session.add(config)
        session.commit()
        return {"status": "stored"}

    @app.delete("/api/settings/smtp-password")
    def delete_smtp_password(session: Session = Depends(get_session)) -> dict[str, str]:
        config = ensure_app_config(session)
        if config.smtp_password_secret_ref:
            clear_secret(config.smtp_password_secret_ref)
            config.smtp_password_secret_ref = None
            config.updated_at = utcnow_naive()
            session.add(config)
            session.commit()
        return {"status": "deleted"}

    @app.get("/api/notifications/readiness", response_model=NotificationReadinessOut)
    def notifications_readiness(session: Session = Depends(get_session)) -> NotificationReadinessOut:
        config = ensure_app_config(session)
        readiness = compute_notification_readiness(config)
        return NotificationReadinessOut(**readiness)

    @app.post("/api/notifications/test", response_model=NotificationTestOut)
    def notifications_test(
        payload: NotificationTestPayload | None = None,
        session: Session = Depends(get_session),
    ) -> NotificationTestOut:
        config = ensure_app_config(session)
        recipient = (
            (payload.recipient if payload else None)
            or config.default_notification_to
            or DEFAULT_NOTIFICATION_TO
        )
        result = send_test_notification(
            config=config,
            recipient=(recipient or "").strip() or None,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail={"message": result.get("summary") or "Test email failed.", **result})
        return NotificationTestOut(**result)

    @app.get("/api/jobs", response_model=list[JobOut])
    def list_jobs(session: Session = Depends(get_session)) -> list[Job]:
        return session.query(Job).order_by(Job.created_at.desc()).all()

    @app.post("/api/jobs", response_model=JobOut, status_code=201)
    def create_job(payload: JobCreate, session: Session = Depends(get_session)) -> Job:
        existing = session.query(Job).filter(Job.name == payload.name).one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Job name already exists.")
        payload_data = payload.model_dump()
        scheduler_defaults = app.state.runtime.workspace.scheduler
        if payload_data.get("repo_slug") in {None, "", "substrate-core"}:
            payload_data["repo_slug"] = scheduler_defaults.default_repo_slug
        if payload_data.get("stage") in {None, "", "local"}:
            payload_data["stage"] = scheduler_defaults.default_stage
        if payload.mode == "cloud_exec" and payload.enabled:
            assert_cloud_readiness(
                session=session,
                config=ensure_app_config(session),
                cloud_env_id=payload.cloud_env_id,
                working_directory=payload.working_directory,
            )
        job = Job(**payload_data)
        now = utcnow_naive()
        job.created_at = now
        job.updated_at = now
        session.add(job)
        session.commit()
        session.refresh(job)
        app.state.scheduler_service.reload_all()
        return job

    @app.put("/api/jobs/{job_id}", response_model=JobOut)
    def update_job(job_id: int, payload: JobUpdate, session: Session = Depends(get_session)) -> Job:
        job = session.query(Job).filter(Job.id == job_id).one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if payload.mode == "cloud_exec" and payload.enabled:
            assert_cloud_readiness(
                session=session,
                config=ensure_app_config(session),
                cloud_env_id=payload.cloud_env_id,
                working_directory=payload.working_directory,
            )
        for key, value in payload.model_dump().items():
            setattr(job, key, value)
        job.updated_at = utcnow_naive()
        session.add(job)
        session.commit()
        session.refresh(job)
        app.state.scheduler_service.reload_all()
        return job

    @app.patch("/api/jobs/{job_id}/enabled", response_model=JobOut)
    def toggle_job(job_id: int, payload: TogglePayload, session: Session = Depends(get_session)) -> Job:
        job = session.query(Job).filter(Job.id == job_id).one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if payload.enabled and job.mode == "cloud_exec":
            assert_cloud_readiness(
                session=session,
                config=ensure_app_config(session),
                cloud_env_id=job.cloud_env_id,
                working_directory=job.working_directory,
            )
        job.enabled = payload.enabled
        job.updated_at = utcnow_naive()
        session.add(job)
        session.commit()
        session.refresh(job)
        app.state.scheduler_service.reload_all()
        return job

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: int, session: Session = Depends(get_session)) -> None:
        job = session.query(Job).filter(Job.id == job_id).one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        session.delete(job)
        session.commit()
        app.state.scheduler_service.reload_all()
        return None

    @app.post("/api/jobs/{job_id}/run", response_model=RunOut)
    def run_now(job_id: int, session: Session = Depends(get_session)) -> RunRecord:
        job = session.query(Job).filter(Job.id == job_id).one_or_none()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.mode == "cloud_exec":
            assert_cloud_readiness(
                session=session,
                config=ensure_app_config(session),
                cloud_env_id=job.cloud_env_id,
                working_directory=job.working_directory,
            )
        return execute_now(
            session=session,
            job=job,
            run_root=app.state.run_root,
            orchestrator=app.state.orchestrator,
        )

    @app.get("/api/runs", response_model=list[RunOut])
    def list_runs(limit: int = 100, session: Session = Depends(get_session)) -> list[RunRecord]:
        bounded = max(1, min(limit, 500))
        return session.query(RunRecord).order_by(RunRecord.started_at.desc()).limit(bounded).all()

    @app.get("/api/jobs/{job_id}/runs", response_model=list[RunOut])
    def list_job_runs(job_id: int, limit: int = 100, session: Session = Depends(get_session)) -> list[RunRecord]:
        bounded = max(1, min(limit, 500))
        return (
            session.query(RunRecord)
            .filter(RunRecord.job_id == job_id)
            .order_by(RunRecord.started_at.desc())
            .limit(bounded)
            .all()
        )

    @app.post("/api/deployment/install")
    def install_deployment(payload: DeploymentInstallPayload, session: Session = Depends(get_session)) -> dict:
        config = ensure_app_config(session)
        request = DeploymentRequest(
            task_name=payload.task_name,
            host=payload.host,
            port=payload.port,
            python_path=payload.python_path,
            user=payload.user,
            logon_type=payload.logon_type,
            password=payload.password,
            codex_scheduler_db=payload.codex_scheduler_db,
            codex_scheduler_disable_autostart=payload.codex_scheduler_disable_autostart,
            run_level=payload.run_level,
            working_directory=str(project_root),
        )
        result = install_headless_task(request)
        config.deployment_task_name = payload.task_name
        config.deployment_host = payload.host
        config.deployment_port = payload.port
        config.deployment_user = payload.user
        config.updated_at = utcnow_naive()
        session.add(config)
        session.commit()
        return result

    @app.get("/api/deployment/{task_name}")
    def deployment_status(task_name: str) -> dict:
        return get_task_status(task_name)

    @app.delete("/api/deployment/{task_name}")
    def remove_deployment(task_name: str, session: Session = Depends(get_session)) -> dict:
        result = uninstall_headless_task(task_name)
        config = ensure_app_config(session)
        if config.deployment_task_name == task_name:
            config.deployment_task_name = None
            config.updated_at = utcnow_naive()
            session.add(config)
            session.commit()
        return result

    @app.post("/api/windows/app-mode/install")
    def windows_install_app_mode() -> dict:
        if not app.state.runtime.workspace.scheduler.windows_app_mode_enabled:
            raise HTTPException(status_code=404, detail="Windows app-mode features are disabled.")
        result = windows_app_mode_install()
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail={"message": result.get("message") or "Install failed.", **result})
        return result

    @app.delete("/api/windows/app-mode/install")
    def windows_uninstall_app_mode() -> dict:
        if not app.state.runtime.workspace.scheduler.windows_app_mode_enabled:
            raise HTTPException(status_code=404, detail="Windows app-mode features are disabled.")
        result = windows_app_mode_uninstall()
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail={"message": result.get("message") or "Uninstall failed.", **result})
        return result

    @app.post("/api/windows/host/start")
    def windows_start_host() -> dict:
        if not app.state.runtime.workspace.scheduler.windows_features_enabled:
            raise HTTPException(status_code=404, detail="Windows host features are disabled.")
        result = windows_host_start()
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail={"message": result.get("message") or "Host start failed.", **result})
        return result

    @app.post("/api/windows/host/stop")
    def windows_stop_host() -> dict:
        if not app.state.runtime.workspace.scheduler.windows_features_enabled:
            raise HTTPException(status_code=404, detail="Windows host features are disabled.")
        result = windows_host_stop()
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail={"message": result.get("message") or "Host stop failed.", **result})
        return result

    return app
