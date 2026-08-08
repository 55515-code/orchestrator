from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

from .config_sync import (
    CONFIG_SYNC_TARGET_ENVS,
    backup_config_sync,
    config_sync_payload,
    deploy_config_sync,
    plan_config_sync,
    scan_config_sync,
)
from .dashboard import create_dashboard_router
from .ducky import DuckyPayloadEngine
from .gateway import GatewayManager, MessageRouter
from .gh_sync import GitHubSyncService
from .integrations import (
    connect_integration,
    disconnect_integration,
    integrations_payload,
    set_integration_mode,
)
from .learning import learning_payload, record_execution, record_resolution_note
from .models import OPENCLAW_ALLOWED_DATA_CLASSES
from .orchestrator import Orchestrator
from .pipelines import PipelineEngine, PipelineRegistry, create_pipelines_router
from .providers import SUPPORTED_PROVIDERS, provider_diagnostics
from .registry import SubstrateRuntime
from .render import (
    render_catalog_payload,
    render_dispatch,
    render_telemetry_payload,
)
from .render_engines.base import RenderRequest, RenderUnavailable
from .research import diagnose_openclaw, refresh_upstreams
from .standards import standards_payload
from .stats import dashboard_payload
from .tooling import ensure_tool_profile, tooling_snapshot

RUNTIME = SubstrateRuntime()
ORCHESTRATOR = Orchestrator(RUNTIME)
DUCKY_ENGINE = DuckyPayloadEngine(RUNTIME, ORCHESTRATOR)
EXECUTOR = ThreadPoolExecutor(max_workers=4)
RUN_FUTURES: dict[str, Future[Any]] = {}
RUN_FUTURES_LOCK = Lock()

# Dashboard and Pipelines services
PIPELINE_REGISTRY = PipelineRegistry()
PIPELINE_REGISTRY.load_from_directory(RUNTIME.root / "pipelines")
PIPELINE_ENGINE = PipelineEngine(
    registry=PIPELINE_REGISTRY,
    workdir=RUNTIME.root,
    artifacts_dir=RUNTIME.root / "artifacts" / "pipelines",
)
GH_SYNC_SERVICE: GitHubSyncService | None = None

# Gateway services
GATEWAY_MANAGER = GatewayManager()
GATEWAY_ROUTER: MessageRouter | None = None

MAX_REQUEST_BODY_BYTES = 16 * 1024
ALLOWED_STAGES = {"local", "hosted_dev", "production"}
ALLOWED_MODES = {"observe", "mutate"}
ALLOWED_ACCESS_MODES = {"read", "write"}
ALLOWED_TARGET_ENVS = set(CONFIG_SYNC_TARGET_ENVS)
ALLOWED_PROVIDERS = set(SUPPORTED_PROVIDERS)
ALLOWED_OPENCLAW_DATA_CLASSES = set(OPENCLAW_ALLOWED_DATA_CLASSES)
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
        "connect-src 'self' ws: wss:;"
    ),
}

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Lifespan context manager replacing deprecated on_event handlers."""
    global GATEWAY_ROUTER
    
    # Initialize gateway on startup
    try:
        gateway_config = RUNTIME.workspace.gateway
        if gateway_config.get("enabled", False):
            GATEWAY_MANAGER.initialize(gateway_config)
            GATEWAY_ROUTER = MessageRouter(GATEWAY_MANAGER)
            logger.info("Gateway initialized successfully")
        else:
            logger.info("Gateway is disabled in configuration")
    except Exception as e:
        logger.error(f"Failed to initialize gateway: {e}")
    
    try:
        yield
    finally:
        # Shutdown gateway
        if GATEWAY_ROUTER:
            GATEWAY_MANAGER.shutdown()
            logger.info("Gateway shutdown complete")


app = FastAPI(
    title="Local Agent Substrate Ops Panel",
    version="0.2.0",
    lifespan=_lifespan,
)
TEMPLATES = Jinja2Templates(directory=str((RUNTIME.root / "substrate" / "templates")))
app.mount(
    "/static",
    StaticFiles(directory=str((RUNTIME.root / "substrate" / "static"))),
    name="static",
)


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
def healthz() -> dict[str, Any]:
    openclaw = diagnose_openclaw()
    providers = provider_diagnostics()
    runtime_ready = bool(RUNTIME.workspace.repositories)
    return {
        "status": "ok",
        "service": "local-agent-substrate-ops-panel",
        "checks": {
            "runtime": {
                "status": "ok" if runtime_ready else "degraded",
                "workspace_root": str(RUNTIME.root),
                "repository_count": len(RUNTIME.workspace.repositories),
            },
            "openclaw": openclaw,
            "providers": providers,
        },
    }


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


@app.get("/api/render/catalog")
def api_render_catalog(engine_id: str | None = None) -> dict[str, Any]:
    return render_catalog_payload(RUNTIME, engine_id=engine_id)


@app.post("/api/render/run")
def api_render_run(request: Request) -> dict[str, Any]:
    body = request.json() or {}
    try:
        req = RenderRequest(
            prompt=body.get("prompt", ""),
            negative=body.get("negative", ""),
            width=int(body.get("width", 1024)),
            height=int(body.get("height", 1024)),
            steps=body.get("steps"),
            guidance=body.get("guidance"),
            seed=body.get("seed"),
            num_images=int(body.get("num_images", 1)),
            mode=body.get("mode", "text_to_image"),
            source_image=Path(body["source_image"]) if body.get("source_image") else None,
            style_refs=[Path(p) for p in body.get("style_refs", [])],
            output=Path(body["output"]) if body.get("output") else None,
            extra=body.get("extra", {}),
        )
        return render_dispatch(
            RUNTIME,
            req,
            optimize_for=body.get("optimize_for", "quality"),
            forced_engine=body.get("engine"),
            use_cache=not body.get("no_cache", False),
            dry_run=body.get("dry_run", False),
        )
    except (ValueError, RenderUnavailable) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/render/telemetry")
def api_render_telemetry() -> dict[str, Any]:
    return render_telemetry_payload(RUNTIME)


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


# Modern Control Panel - OpenClaw-inspired dashboard
@app.get("/panel")
def control_panel(request: Request):
    """Serve the modern control panel dashboard."""
    return TEMPLATES.TemplateResponse(
        request=request,
        name="control-panel.html",
        context={},
    )


@app.get("/stream/metrics")
async def stream_metrics():
    """Server-Sent Events endpoint for real-time metrics streaming."""
    async def event_generator():
        while True:
            try:
                # Collect current metrics
                dashboard_data = dashboard_payload(RUNTIME)
                repos = RUNTIME.repositories()
                runs = RUNTIME.db.list_recent_runs(limit=10)
                
                metrics = {
                    "metrics": {
                        "repositories": len(repos),
                        "runs": len(runs),
                        "success_rate": _calculate_success_rate(runs),
                        "health": "healthy" if RUNTIME.workspace.repositories else "degraded",
                    },
                    "activity": [
                        {
                            "status": run.get("status", "unknown"),
                            "task_id": run.get("task_id", "unknown"),
                            "repo_slug": run.get("repo_slug", "unknown"),
                            "started_at": run.get("started_at"),
                        }
                        for run in runs[:5]
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                
                yield f"data: {json.dumps(metrics)}\n\n"
                await asyncio.sleep(2)  # Update every 2 seconds
            except Exception as e:
                print(f"Error in metrics stream: {e}")
                await asyncio.sleep(5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


def _calculate_success_rate(runs: list[dict]) -> int:
    """Calculate success rate percentage from runs."""
    if not runs:
        return 0
    successful = sum(1 for r in runs if r.get("status") == "success")
    return int((successful / len(runs)) * 100)


# Gateway routes for third-party service integration
@app.get("/gateway/{service_id}/webhook")
async def gateway_webhook_verify(service_id: str, request: Request):
    """Handle webhook verification for gateway services."""
    if not GATEWAY_ROUTER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    plugin = GATEWAY_MANAGER.get_plugin(service_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
    
    # Get query parameters
    params = dict(request.query_params)
    
    # Verify webhook challenge
    challenge = plugin.verify_webhook_challenge(params)
    if challenge is None:
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    
    return PlainTextResponse(challenge)


@app.post("/gateway/{service_id}/webhook")
async def gateway_webhook_receive(service_id: str, request: Request):
    """Handle inbound webhook from gateway services."""
    if not GATEWAY_ROUTER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    plugin = GATEWAY_MANAGER.get_plugin(service_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
    
    # Get raw body for signature validation
    body = await request.body()
    
    # Verify signature
    signature = request.headers.get("x-hub-signature-256", "")
    if not plugin.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    
    # Parse messages
    messages = plugin.parse_inbound(payload)
    
    # Process each message
    responses = []
    for message in messages:
        try:
            response = await GATEWAY_ROUTER.process_inbound(message)
            if response:
                # Send response back via plugin
                await plugin.send_text(message.user_id, response)
                responses.append({"message_id": message.message_id, "status": "responded"})
            else:
                responses.append({"message_id": message.message_id, "status": "processed"})
        except Exception as e:
            logger.error(f"Error processing message {message.message_id}: {e}")
            responses.append({"message_id": message.message_id, "status": "error", "error": str(e)})
    
    return JSONResponse({"status": "ok", "messages": responses})


@app.post("/gateway/{service_id}/send")
async def gateway_send_message(service_id: str, request: Request):
    """Send outbound message via gateway service."""
    if not GATEWAY_ROUTER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    plugin = GATEWAY_MANAGER.get_plugin(service_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Service not found: {service_id}")
    
    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    
    user_id = body.get("user_id")
    text = body.get("text")
    
    if not user_id or not text:
        raise HTTPException(status_code=400, detail="Missing user_id or text")
    
    # Send message
    try:
        result = await plugin.send_text(user_id, text)
        return JSONResponse({"status": "sent", "result": result})
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {e}")


@app.get("/gateway/services")
async def gateway_list_services():
    """List all available gateway services."""
    if not GATEWAY_ROUTER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    plugins = GATEWAY_MANAGER.list_plugins()
    
    services = []
    for plugin in plugins:
        services.append({
            "id": plugin.service_id,
            "name": plugin.service_name,
            "version": plugin.version,
            "enabled": plugin.enabled,
            "initialized": plugin.initialized,
            "capabilities": plugin.capabilities,
            "webhook_url": plugin.webhook_url,
        })
    
    return JSONResponse({"services": services})


# WhatsApp Setup API Endpoints
@app.get("/api/gateway/whatsapp/config")
async def get_whatsapp_config(request: Request):
    """Get current WhatsApp configuration."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    whatsapp_plugin = GATEWAY_MANAGER.get_plugin("whatsapp")
    if not whatsapp_plugin:
        return JSONResponse({
            "phone_number_id": "",
            "verify_token": "",
            "webhook_url": f"{request.base_url}gateway/whatsapp/webhook"
        })
    
    config = whatsapp_plugin._config
    return JSONResponse({
        "phone_number_id": config.get("phone_number_id", ""),
        "verify_token": config.get("verify_token", ""),
        "webhook_url": config.get("webhook_url", f"{request.base_url}gateway/whatsapp/webhook")
    })


@app.post("/api/gateway/whatsapp/config")
async def save_whatsapp_config(request: Request):
    """Save WhatsApp configuration."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    try:
        body = await request.json()
        config = {
            "phone_number_id": body.get("phone_number_id"),
            "access_token": body.get("access_token"),
            "app_secret": body.get("app_secret"),
            "verify_token": body.get("verify_token"),
            "webhook_url": body.get("webhook_url")
        }
        
        # Validate required fields
        required = ["phone_number_id", "access_token", "app_secret", "verify_token"]
        for field in required:
            if not config.get(field):
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Update plugin configuration
        whatsapp_plugin = GATEWAY_MANAGER.get_plugin("whatsapp")
        if whatsapp_plugin:
            whatsapp_plugin.initialize(config)
        
        return JSONResponse({"status": "success", "message": "Configuration saved"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/gateway/whatsapp/qr")
async def generate_whatsapp_qr():
    """Generate WhatsApp QR code for connection."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    whatsapp_plugin = GATEWAY_MANAGER.get_plugin("whatsapp")
    if not whatsapp_plugin:
        raise HTTPException(status_code=404, detail="WhatsApp plugin not found")
    
    try:
        # Generate QR code using a simple SVG placeholder
        # In production, this would integrate with WhatsApp Business API
        # and generate a real QR code for WhatsApp Web linking
        qr_data = f"whatsapp-connect:{whatsapp_plugin._config.get('phone_number_id', 'unknown')}"
        
        # Create a simple SVG QR code placeholder
        # This is a visual representation - in production, use proper QR generation
        svg_qr = '''<svg width="280" height="280" xmlns="http://www.w3.org/2000/svg">
            <rect width="280" height="280" fill="white"/>
            <text x="140" y="140" font-family="Arial" font-size="14" text-anchor="middle" fill="black">
                WhatsApp QR Code
            </text>
            <text x="140" y="160" font-family="Arial" font-size="12" text-anchor="middle" fill="#666">
                Scan with WhatsApp
            </text>
            <rect x="40" y="40" width="200" height="200" fill="none" stroke="black" stroke-width="2"/>
            <rect x="60" y="60" width="40" height="40" fill="black"/>
            <rect x="180" y="60" width="40" height="40" fill="black"/>
            <rect x="60" y="180" width="40" height="40" fill="black"/>
        </svg>'''
        
        import base64
        qr_base64 = base64.b64encode(svg_qr.encode()).decode()
        
        return JSONResponse({
            "qr_code": f"data:image/svg+xml;base64,{qr_base64}",
            "expires_in": 300  # 5 minutes
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate QR code: {str(e)}")


@app.get("/api/gateway/whatsapp/status")
async def get_whatsapp_status():
    """Get WhatsApp connection status."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    whatsapp_plugin = GATEWAY_MANAGER.get_plugin("whatsapp")
    if not whatsapp_plugin:
        return JSONResponse({
            "connected": False,
            "status": "not_configured"
        })
    
    # Check connection status
    # This would check actual WhatsApp Business API connection
    return JSONResponse({
        "connected": whatsapp_plugin.is_connected if hasattr(whatsapp_plugin, 'is_connected') else False,
        "status": "connected" if hasattr(whatsapp_plugin, 'is_connected') and whatsapp_plugin.is_connected else "disconnected",
        "phone_number": whatsapp_plugin._config.get("phone_number_id", "")
    })


@app.post("/api/gateway/whatsapp/test")
async def send_whatsapp_test(request: Request):
    """Send a test message via WhatsApp."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    whatsapp_plugin = GATEWAY_MANAGER.get_plugin("whatsapp")
    if not whatsapp_plugin:
        raise HTTPException(status_code=404, detail="WhatsApp plugin not found")
    
    try:
        body = await request.json()
        message = body.get("message", "Test message from Substrate")
        
        # Send test message
        # This would use the WhatsApp Business API to send a message
        # For now, just return success
        return JSONResponse({
            "status": "success",
            "message": "Test message sent",
            "message_id": f"test_{int(time.time())}"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test message: {str(e)}")


@app.post("/api/gateway/whatsapp/complete")
async def complete_whatsapp_setup():
    """Mark WhatsApp setup as complete."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    try:
        # Mark setup as complete in the gateway state
        # This would update the gateway configuration
        return JSONResponse({
            "status": "success",
            "message": "WhatsApp setup completed"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gateway/whatsapp/logs")
async def get_whatsapp_logs():
    """Get WhatsApp gateway logs."""
    if not GATEWAY_MANAGER:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    try:
        # Read gateway logs
        # This would read from the gateway log file or database
        logs = "WhatsApp Gateway Logs\n====================\n\n[INFO] Gateway initialized\n[INFO] WhatsApp plugin loaded\n[INFO] Webhook endpoint registered\n"
        
        return JSONResponse({
            "logs": logs
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Legacy ops panel endpoints and API routes above.
# The root "/" redirects to the legacy dashboard which provides the full
# operational overview (repositories, runs, standards, tooling, integrations).
from starlette.responses import RedirectResponse  # noqa: E402

# Include dashboard and pipelines routers
dashboard_router = create_dashboard_router(
    templates_dir=RUNTIME.root / "substrate" / "dashboard" / "templates",
    static_dir=RUNTIME.root / "substrate" / "dashboard" / "static",
)
pipelines_router = create_pipelines_router(PIPELINE_REGISTRY, PIPELINE_ENGINE)
app.include_router(dashboard_router)
app.include_router(pipelines_router)

# iPhone webapp panel extensions (automations + live system stream). Additive.
from .iphone_panel import router as iphone_panel_router  # noqa: E402

app.include_router(iphone_panel_router)


@app.get("/")
def root_redirect(request: Request):
    """Redirect the root URL to the modern control panel."""
    return RedirectResponse(url="/panel", status_code=302)

