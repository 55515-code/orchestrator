from __future__ import annotations

import json
import re
import shutil
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config_sync import (
    CONFIG_SYNC_TARGET_ENVS,
    backup_config_sync,
    config_sync_payload,
    deploy_config_sync,
    plan_config_sync,
    scan_config_sync,
)
from .ducky import DuckyPayloadEngine
from .integrations import (
    connect_integration,
    disconnect_integration,
    integrations_payload,
    set_integration_mode,
)
from .learning import learning_payload, record_execution, record_resolution_note
from .orchestrator import Orchestrator
from .registry import SubstrateRuntime
from .research import refresh_upstreams
from .standards import standards_payload
from .stats import dashboard_payload
from .studio.main import create_app as create_studio_app
from .tooling import ensure_tool_profile, tooling_snapshot

RUNTIME = SubstrateRuntime()
ORCHESTRATOR = Orchestrator(RUNTIME)
DUCKY_ENGINE = DuckyPayloadEngine(RUNTIME, ORCHESTRATOR)
EXECUTOR = ThreadPoolExecutor(max_workers=4)
RUN_FUTURES: dict[str, Future[Any]] = {}
RUN_FUTURES_LOCK = Lock()
STUDIO_APP = create_studio_app(
    start_scheduler=bool(RUNTIME.workspace.scheduler.enabled),
    runtime=RUNTIME,
    orchestrator=ORCHESTRATOR,
    static_mount_path="/studio-static",
)

MAX_REQUEST_BODY_BYTES = 16 * 1024
ALLOWED_STAGES = {"local", "hosted_dev", "production"}
ALLOWED_MODES = {"observe", "mutate"}
ALLOWED_ACCESS_MODES = {"read", "write"}
ALLOWED_TARGET_ENVS = set(CONFIG_SYNC_TARGET_ENVS)
ALLOWED_PROVIDERS = {"mock", "local", "anthropic", "ollama"}
ALLOWED_OPENCLAW_DATA_CLASSES = {"synthetic", "redacted"}
MAX_SLUG_LENGTH = 64
MAX_TEXT_LENGTH = 2048
MAX_MODEL_LENGTH = 128
MAX_CHAIN_PATH_LENGTH = 256
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "img-src 'self' data:; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'"
    ),
}

app = FastAPI(
    title="Local Agent Substrate Ops Panel",
    version="0.2.0",
)
TEMPLATES = Jinja2Templates(directory=str((RUNTIME.root / "substrate" / "templates")))
app.mount(
    "/static",
    StaticFiles(directory=str((RUNTIME.root / "substrate" / "static"))),
    name="static",
)


@app.on_event("startup")
def _startup_studio_scheduler() -> None:
    if (
        hasattr(STUDIO_APP.state, "scheduler_service")
        and RUNTIME.workspace.scheduler.enabled
    ):
        STUDIO_APP.state.scheduler_service.start()


@app.on_event("shutdown")
def _shutdown_studio_scheduler() -> None:
    if hasattr(STUDIO_APP.state, "scheduler_service"):
        STUDIO_APP.state.scheduler_service.shutdown()


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "on", "yes"}


def _submit(run_id: str, fn, *args, **kwargs) -> None:
    future = EXECUTOR.submit(fn, *args, **kwargs)
    with RUN_FUTURES_LOCK:
        RUN_FUTURES[run_id] = future

    def _cleanup(completed: Future[Any]) -> None:
        with RUN_FUTURES_LOCK:
            RUN_FUTURES.pop(run_id, None)
        try:
            completed.result()
        except Exception:
            # Errors are persisted by orchestrator run records.
            pass

    future.add_done_callback(_cleanup)


def _wants_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
):
    if _wants_json(request):
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if details:
            payload["error"]["details"] = details
        return JSONResponse(payload, status_code=status_code)
    return PlainTextResponse(f"{code}: {message}", status_code=status_code)


def _normalize_text(value: str, field: str, *, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field} is required.")
    if len(normalized) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be at most {max_length} characters.",
        )
    return normalized


def _normalize_slug(value: str, field: str = "slug") -> str:
    normalized = _normalize_text(value, field, max_length=MAX_SLUG_LENGTH)
    if not SLUG_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"{field} must match {SLUG_RE.pattern}.",
        )
    return normalized


def _normalize_name(value: str, field: str) -> str:
    normalized = _normalize_text(value, field, max_length=MAX_MODEL_LENGTH)
    if not NAME_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"{field} contains unsupported characters.",
        )
    return normalized


def _normalize_choice(value: str, field: str, allowed: set[str]) -> str:
    normalized = _normalize_text(value, field, max_length=32)
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be one of: {', '.join(sorted(allowed))}.",
        )
    return normalized


def _resolve_workspace_chain_path(chain_path: str) -> str:
    normalized = _normalize_text(
        chain_path, "chain_path", max_length=MAX_CHAIN_PATH_LENGTH
    )
    raw_candidate = Path(normalized)
    if raw_candidate.is_absolute():
        raise HTTPException(
            status_code=400, detail="chain_path must be workspace-relative."
        )
    if any(part == ".." for part in raw_candidate.parts):
        raise HTTPException(
            status_code=400, detail="chain_path may not traverse parent directories."
        )
    resolved = (RUNTIME.root / raw_candidate).resolve()
    if resolved.is_relative_to(RUNTIME.root) is False:
        raise HTTPException(
            status_code=400, detail="chain_path must stay within the workspace."
        )
    if resolved.suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(
            status_code=400, detail="chain_path must point to a YAML file."
        )
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Chain config not found.")
    return resolved.relative_to(RUNTIME.root).as_posix()


def _validate_repo_slug(repo_slug: str) -> str:
    normalized = _normalize_slug(repo_slug, "repo_slug")
    if normalized not in RUNTIME.repositories():
        raise HTTPException(status_code=404, detail="Unknown repository slug.")
    return normalized


def _validate_stage(stage: str) -> str:
    return _normalize_choice(stage, "stage", ALLOWED_STAGES)


def _validate_mode(mode: str) -> str:
    return _normalize_choice(mode, "mode", ALLOWED_MODES)


def _validate_access_mode(mode: str) -> str:
    return _normalize_choice(mode, "access_mode", ALLOWED_ACCESS_MODES)


def _validate_target_env(target: str | None) -> str:
    if target is None or not str(target).strip():
        return "current"
    normalized = _normalize_text(target, "target", max_length=32).lower()
    aliases = {"darwin": "mac", "macos": "mac", "osx": "mac", "win": "windows"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in ALLOWED_TARGET_ENVS:
        raise HTTPException(
            status_code=400,
            detail=f"target must be one of: {', '.join(sorted(ALLOWED_TARGET_ENVS))}.",
        )
    return normalized


def _parse_path_filters(raw_paths: str | None) -> list[str]:
    if raw_paths is None:
        return []
    separators = raw_paths.replace("\n", ",").split(",")
    return [item.strip() for item in separators if item.strip()]


def _validate_provider(provider: str) -> str:
    normalized = _normalize_name(provider, "provider")
    if normalized not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider must be one of: {', '.join(sorted(ALLOWED_PROVIDERS))}.",
        )
    return normalized


def _validate_openclaw_data_class(data_class: str) -> str:
    normalized = _normalize_choice(
        data_class,
        "openclaw_data_class",
        ALLOWED_OPENCLAW_DATA_CLASSES,
    )
    return normalized


def _validate_objective(objective: str) -> str:
    return _normalize_text(objective, "objective", max_length=MAX_TEXT_LENGTH)


def _validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=400, detail="port must be between 1 and 65535.")
    return port


def _detect_access_tools() -> dict[str, str | None]:
    return {
        "cloudflared": shutil.which("cloudflared"),
        "tailscale": shutil.which("tailscale"),
        "ssh": shutil.which("ssh"),
    }


def _pinch_hints(port: int = 8090, repo_slug: str | None = None) -> dict[str, Any]:
    base_url = f"http://127.0.0.1:{port}"
    tools = _detect_access_tools()
    access: list[dict[str, Any]] = []

    if tools["cloudflared"]:
        access.append(
            {
                "tool": "cloudflared",
                "available": True,
                "scope": "public",
                "command": f"cloudflared tunnel --url {base_url}",
                "notes": "Quick tunnel for local testing. Cloudflare docs note this is for development use.",
            }
        )
    else:
        access.append(
            {
                "tool": "cloudflared",
                "available": False,
                "scope": "public",
                "command": f"cloudflared tunnel --url {base_url}",
                "notes": "Install cloudflared to use a free development tunnel.",
            }
        )

    if tools["tailscale"]:
        access.append(
            {
                "tool": "tailscale",
                "available": True,
                "scope": "tailnet",
                "command": f"tailscale serve localhost:{port}",
                "alternate": "tailscale funnel (for public exposure, if enabled in your tailnet policy)",
                "notes": "Serve keeps access inside your tailnet; Funnel exposes it publicly.",
            }
        )
    else:
        access.append(
            {
                "tool": "tailscale",
                "available": False,
                "scope": "tailnet",
                "command": f"tailscale serve localhost:{port}",
                "alternate": "tailscale funnel (for public exposure, if enabled in your tailnet policy)",
                "notes": "Install Tailscale to publish a secure tailnet or funnel endpoint.",
            }
        )

    if tools["ssh"]:
        access.append(
            {
                "tool": "ssh",
                "available": True,
                "scope": "bastion",
                "command": f"ssh -N -R {port}:127.0.0.1:{port} user@remote-host",
                "notes": "Useful when you have a reachable bastion or jump host.",
            }
        )
    else:
        access.append(
            {
                "tool": "ssh",
                "available": False,
                "scope": "bastion",
                "command": f"ssh -N -R {port}:127.0.0.1:{port} user@remote-host",
                "notes": "Install OpenSSH client to use a reverse tunnel fallback.",
            }
        )

    diagnostics: list[dict[str, Any]] = [
        {
            "label": "health",
            "command": f"curl -fsS {base_url}/healthz",
        },
        {
            "label": "recent runs",
            "command": "uv run python scripts/substrate_cli.py runs",
        },
        {
            "label": "repository scan",
            "command": "uv run python scripts/substrate_cli.py scan",
        },
    ]
    if repo_slug:
        diagnostics.append(
            {
                "label": "repo dry run",
                "command": (
                    "uv run python scripts/substrate_cli.py run-chain "
                    f'--repo {repo_slug} --objective "Recovery check" --stage local --dry-run'
                ),
            }
        )

    return {
        "base_url": base_url,
        "tools": tools,
        "access": access,
        "diagnostics": diagnostics,
    }


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            if not content_length.isdigit():
                return _error_response(
                    request,
                    400,
                    "invalid_request",
                    "Malformed Content-Length header.",
                )
            if int(content_length) > MAX_REQUEST_BODY_BYTES:
                return _error_response(
                    request,
                    413,
                    "payload_too_large",
                    f"Request body exceeds {MAX_REQUEST_BODY_BYTES} bytes.",
                )
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _error_response(
        request,
        422,
        "validation_error",
        "Request validation failed.",
        details={"errors": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return _error_response(
        request,
        exc.status_code,
        "http_error",
        detail,
        details={"detail": exc.detail} if not isinstance(exc.detail, str) else None,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return _error_response(
        request,
        500,
        "internal_server_error",
        "Internal server error.",
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/legacy")
@app.get("/legacy/")
def dashboard(request: Request):
    if not RUNTIME.db.latest_repository_snapshots():
        RUNTIME.scan_repositories(persist=True)
    payload = dashboard_payload(RUNTIME)
    payload["workspace_repositories"] = sorted(RUNTIME.repositories().keys())
    payload["stage_sequence"] = RUNTIME.workspace.policy.stage_sequence
    payload["pass_sequence"] = RUNTIME.workspace.policy.pass_sequence
    payload["payloads"] = DUCKY_ENGINE.list_payloads()
    return TEMPLATES.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=payload,
    )


@app.get("/runs/{run_id}")
def run_details(request: Request, run_id: str):
    run = RUNTIME.db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    events = RUNTIME.db.list_run_events(run_id)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="run_detail.html",
        context={"run": run, "events": events},
    )


@app.get("/api/dashboard")
def api_dashboard() -> dict[str, Any]:
    payload = dashboard_payload(RUNTIME)
    payload["pinch"] = _pinch_hints()
    payload["payloads"] = DUCKY_ENGINE.list_payloads()
    payload["stage_sequence"] = RUNTIME.workspace.policy.stage_sequence
    payload["pass_sequence"] = RUNTIME.workspace.policy.pass_sequence
    return payload


@app.get("/api/hints")
def api_hints(repo_slug: str | None = None, port: int = 8090) -> dict[str, Any]:
    if repo_slug is not None:
        repo_slug = _validate_repo_slug(repo_slug)
    return _pinch_hints(port=port, repo_slug=repo_slug)


@app.get("/api/hints/access")
def api_hints_access(port: int = 8090) -> dict[str, Any]:
    return {"access": _pinch_hints(port=port)["access"]}


@app.get("/api/hints/diagnostics")
def api_hints_diagnostics(
    repo_slug: str | None = None, port: int = 8090
) -> dict[str, Any]:
    if repo_slug is not None:
        repo_slug = _validate_repo_slug(repo_slug)
    payload = _pinch_hints(port=port, repo_slug=repo_slug)
    return {"base_url": payload["base_url"], "diagnostics": payload["diagnostics"]}


@app.get("/api/standards")
def api_standards(track: str | None = None) -> dict[str, Any]:
    track_id = _normalize_slug(track, "track") if track else None
    return standards_payload(RUNTIME, track_id=track_id)


@app.get("/api/tooling")
def api_tooling(profile: str | None = None) -> dict[str, Any]:
    profile_id = _normalize_slug(profile, "profile") if profile else None
    return tooling_snapshot(RUNTIME, profile_id=profile_id)


@app.get("/api/integrations")
def api_integrations() -> dict[str, Any]:
    return integrations_payload(RUNTIME)


@app.post("/api/integrations/connect")
def api_integrations_connect(
    request: Request,
    service_id: str = Form(...),
    auth_method: str = Form(""),
    token_ref: str = Form(""),
    granted_scopes: str = Form(""),
    access_mode: str = Form("read"),
    write_directive: str = Form(""),
) -> dict[str, Any]:
    _ = request
    try:
        result = connect_integration(
            RUNTIME,
            service_id=_normalize_slug(service_id, "service_id"),
            auth_method=auth_method.strip() or None,
            token_ref=token_ref.strip() or None,
            granted_scopes=granted_scopes,
            mode=_validate_access_mode(access_mode),
            write_directive=write_directive,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/integrations/mode")
def api_integrations_mode(
    request: Request,
    service_id: str = Form(...),
    access_mode: str = Form(...),
    write_directive: str = Form(""),
) -> dict[str, Any]:
    _ = request
    try:
        result = set_integration_mode(
            RUNTIME,
            service_id=_normalize_slug(service_id, "service_id"),
            mode=_validate_access_mode(access_mode),
            write_directive=write_directive,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/integrations/disconnect")
def api_integrations_disconnect(
    request: Request,
    service_id: str = Form(...),
) -> dict[str, Any]:
    _ = request
    try:
        result = disconnect_integration(
            RUNTIME,
            service_id=_normalize_slug(service_id, "service_id"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.get("/api/learning")
def api_learning(limit: int = 30) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 200))
    return learning_payload(RUNTIME, limit=bounded_limit)


@app.post("/api/learning/resolve")
def api_learning_resolve(
    request: Request,
    signature: str = Form(...),
    resolution: str = Form(...),
    path_reference: str = Form(""),
) -> dict[str, Any]:
    _ = request
    normalized_signature = _normalize_text(signature, "signature", max_length=64)
    normalized_resolution = _normalize_text(resolution, "resolution", max_length=1024)
    try:
        note = record_resolution_note(
            RUNTIME,
            signature=normalized_signature,
            resolution=normalized_resolution,
            path_reference=path_reference.strip() or None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "note": note}


@app.get("/api/config-sync")
def api_config_sync() -> dict[str, Any]:
    return config_sync_payload(RUNTIME)


@app.post("/api/config-sync/scan")
def api_config_sync_scan(request: Request) -> dict[str, Any]:
    _ = request
    result = scan_config_sync(RUNTIME)
    record_execution(
        RUNTIME,
        run_type="config-sync-scan",
        run_id=None,
        repo_slug=None,
        stage="local",
        command="config-sync-scan",
        status="success",
        exit_code=0,
        stdout=json.dumps(result, ensure_ascii=False),
        note="Backup and sync scan",
    )
    return {"ok": True, **result}


@app.post("/api/config-sync/backup")
def api_config_sync_backup(
    request: Request,
    paths: str = Form(""),
    profiles: str = Form(""),
) -> dict[str, Any]:
    _ = request
    result = backup_config_sync(
        RUNTIME,
        selection=_parse_path_filters(paths),
        profile_ids=_parse_path_filters(profiles),
    )
    record_execution(
        RUNTIME,
        run_type="config-sync-backup",
        run_id=None,
        repo_slug=None,
        stage="local",
        command="config-sync-backup",
        status="success",
        exit_code=0,
        stdout=json.dumps(result, ensure_ascii=False),
        note="Backup and sync snapshot",
    )
    return {"ok": True, **result}


@app.post("/api/config-sync/plan")
def api_config_sync_plan(
    request: Request,
    target: str = Form(""),
    paths: str = Form(""),
    profiles: str = Form(""),
    line_endings: str = Form("auto"),
    conversion_mode: str = Form("auto"),
) -> dict[str, Any]:
    _ = request
    result = plan_config_sync(
        RUNTIME,
        target_env=_validate_target_env(target),
        selection=_parse_path_filters(paths),
        profile_ids=_parse_path_filters(profiles),
        line_endings_mode=line_endings,
        conversion_mode=conversion_mode,
    )
    record_execution(
        RUNTIME,
        run_type="config-sync-plan",
        run_id=None,
        repo_slug=None,
        stage="local",
        command=f"config-sync-plan --target {target or 'current'}",
        status="success",
        exit_code=0,
        stdout=json.dumps(result, ensure_ascii=False),
        note="Backup and sync deployment plan",
    )
    return {"ok": True, **result}


@app.post("/api/config-sync/deploy")
def api_config_sync_deploy(
    request: Request,
    target: str = Form(""),
    paths: str = Form(""),
    profiles: str = Form(""),
    line_endings: str = Form("auto"),
    conversion_mode: str = Form("auto"),
    apply: str = Form("false"),
    directive: str = Form(""),
    destination: str = Form(""),
) -> dict[str, Any]:
    _ = request
    try:
        result = deploy_config_sync(
            RUNTIME,
            target_env=_validate_target_env(target),
            apply=_parse_bool(apply),
            directive=directive,
            destination=destination.strip() or None,
            selection=_parse_path_filters(paths),
            profile_ids=_parse_path_filters(profiles),
            line_endings_mode=line_endings,
            conversion_mode=conversion_mode,
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_execution(
        RUNTIME,
        run_type="config-sync-deploy",
        run_id=None,
        repo_slug=None,
        stage="local",
        command=f"config-sync-deploy --target {target or 'current'} --apply",
        status="success",
        exit_code=0,
        stdout=json.dumps(result, ensure_ascii=False),
        note="Backup and sync deployment",
    )
    return {"ok": True, **result}


# Legacy dotfiles endpoints retained as aliases.
@app.get("/api/dotfiles")
def api_dotfiles() -> dict[str, Any]:
    return api_config_sync()


@app.post("/api/dotfiles/scan")
def api_dotfiles_scan(request: Request) -> dict[str, Any]:
    return api_config_sync_scan(request)


@app.post("/api/dotfiles/backup")
def api_dotfiles_backup(
    request: Request,
    paths: str = Form(""),
    profiles: str = Form(""),
) -> dict[str, Any]:
    return api_config_sync_backup(request=request, paths=paths, profiles=profiles)


@app.post("/api/dotfiles/plan")
def api_dotfiles_plan(
    request: Request,
    target: str = Form(""),
    paths: str = Form(""),
    profiles: str = Form(""),
    line_endings: str = Form("auto"),
    conversion_mode: str = Form("auto"),
) -> dict[str, Any]:
    return api_config_sync_plan(
        request=request,
        target=target,
        paths=paths,
        profiles=profiles,
        line_endings=line_endings,
        conversion_mode=conversion_mode,
    )


@app.post("/api/dotfiles/deploy")
def api_dotfiles_deploy(
    request: Request,
    target: str = Form(""),
    paths: str = Form(""),
    profiles: str = Form(""),
    line_endings: str = Form("auto"),
    conversion_mode: str = Form("auto"),
    apply: str = Form("false"),
    directive: str = Form(""),
    destination: str = Form(""),
) -> dict[str, Any]:
    return api_config_sync_deploy(
        request=request,
        target=target,
        paths=paths,
        profiles=profiles,
        line_endings=line_endings,
        conversion_mode=conversion_mode,
        apply=apply,
        directive=directive,
        destination=destination,
    )


@app.get("/api/payloads")
def api_payloads(repo_slug: str | None = None) -> dict[str, Any]:
    normalized_repo = _validate_repo_slug(repo_slug) if repo_slug else None
    return {"payloads": DUCKY_ENGINE.list_payloads(repo_slug=normalized_repo)}


@app.get("/api/payload-jobs/{job_id}")
def api_payload_job(job_id: str) -> dict[str, Any]:
    payload_job = DUCKY_ENGINE.get_job(job_id)
    if payload_job is None:
        raise HTTPException(status_code=404, detail="Payload job not found.")
    return payload_job


@app.post("/api/actions/scan")
def api_scan() -> dict[str, Any]:
    snapshots = RUNTIME.scan_repositories(persist=True)
    return {"ok": True, "count": len(snapshots)}


@app.post("/api/actions/refresh-sources")
def api_refresh_sources() -> dict[str, Any]:
    projects = refresh_upstreams(RUNTIME)
    return {"ok": True, "count": len(projects)}


@app.post("/api/actions/deps-ensure")
def api_deps_ensure(
    request: Request,
    profile_id: str = Form(...),
    apply: str = Form("false"),
) -> dict[str, Any]:
    _ = request
    normalized_profile = _normalize_slug(profile_id, "profile_id")
    try:
        result = ensure_tool_profile(
            RUNTIME,
            profile_id=normalized_profile,
            apply=_parse_bool(apply),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/actions/run-payload")
def api_run_payload(
    request: Request,
    payload_id: str = Form(...),
    repo_slug: str = Form(""),
    stage: str = Form("local"),
    allow_stage_skip: str = Form("false"),
    port: int = Form(8090),
    deps_profile: str = Form(""),
    deps_apply: str = Form("false"),
) -> dict[str, Any]:
    _ = request
    normalized_repo = (
        _validate_repo_slug(repo_slug.strip()) if repo_slug.strip() else None
    )
    normalized_payload = _normalize_slug(payload_id, "payload_id")
    normalized_port = _validate_port(port)
    deps_result: dict[str, Any] | None = None
    if deps_profile.strip():
        try:
            deps_result = ensure_tool_profile(
                RUNTIME,
                profile_id=_normalize_slug(deps_profile, "deps_profile"),
                apply=_parse_bool(deps_apply),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        payload_job_id = DUCKY_ENGINE.submit(
            payload_id=normalized_payload,
            repo_slug=normalized_repo,
            stage=_validate_stage(stage),
            allow_stage_skip=_parse_bool(allow_stage_skip),
            port=normalized_port,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response: dict[str, Any] = {
        "ok": True,
        "job_id": payload_job_id,
        "status_url": f"/api/payload-jobs/{payload_job_id}",
    }
    if deps_result is not None:
        response["deps"] = deps_result
    return response


@app.post("/api/actions/run-chain")
def api_run_chain(
    request: Request,
    repo_slug: str = Form(...),
    objective: str = Form(...),
    chain_path: str = Form("chains/local-agent-chain.yaml"),
    provider: str = Form("mock"),
    model: str = Form("mock-model"),
    stage: str = Form("local"),
    mode: str = Form("observe"),
    dry_run: str = Form("true"),
    allow_mutations: str = Form("false"),
    allow_stage_skip: str = Form("false"),
    openclaw_manual_trigger: str = Form("false"),
    openclaw_data_class: str = Form("synthetic"),
) -> JSONResponse:
    _ = request
    run_id = uuid.uuid4().hex
    _submit(
        run_id,
        ORCHESTRATOR.run_chain,
        repo_slug=_validate_repo_slug(repo_slug),
        objective=_validate_objective(objective),
        chain_path=_resolve_workspace_chain_path(chain_path),
        provider=_validate_provider(provider),
        model=_normalize_name(model, "model"),
        dry_run=_parse_bool(dry_run),
        stage=_validate_stage(stage),
        requested_mode=_validate_mode(mode),
        allow_mutations=_parse_bool(allow_mutations),
        allow_stage_skip=_parse_bool(allow_stage_skip),
        openclaw_manual_trigger=_parse_bool(openclaw_manual_trigger),
        openclaw_data_class=_validate_openclaw_data_class(openclaw_data_class),
        run_id=run_id,
    )
    return JSONResponse(
        {
            "ok": True,
            "run_id": run_id,
            "status_url": f"/api/runs/{run_id}",
            "hints_url": "/api/hints",
        }
    )


@app.post("/api/actions/run-task")
def api_run_task(
    request: Request,
    repo_slug: str = Form(...),
    task_id: str = Form(...),
    stage: str = Form("local"),
    mode: str = Form("observe"),
    allow_mutations: str = Form("false"),
    allow_stage_skip: str = Form("false"),
) -> JSONResponse:
    _ = request
    repo_slug = _validate_repo_slug(repo_slug)
    task_id = _normalize_slug(task_id, "task_id")
    repo = RUNTIME.resolve_repo(repo_slug)
    if task_id not in repo.tasks:
        raise HTTPException(status_code=404, detail="Unknown task id.")
    run_id = uuid.uuid4().hex
    _submit(
        run_id,
        ORCHESTRATOR.run_task,
        repo_slug=repo_slug,
        task_id=task_id,
        stage=_validate_stage(stage),
        requested_mode=_validate_mode(mode),
        allow_mutations=_parse_bool(allow_mutations),
        allow_stage_skip=_parse_bool(allow_stage_skip),
        run_id=run_id,
    )
    return JSONResponse(
        {
            "ok": True,
            "run_id": run_id,
            "status_url": f"/api/runs/{run_id}",
            "hints_url": "/api/hints",
        }
    )


@app.get("/api/runs/{run_id}")
def api_run(run_id: str) -> dict[str, Any]:
    run = RUNTIME.db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run["events"] = RUNTIME.db.list_run_events(run_id)
    return run


# Keep legacy endpoints above, and serve Studio as the default root experience.
app.mount("/", STUDIO_APP)
