from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .agents import (
    AgentConfigError,
    agent_status_payload,
    load_agents_config,
    run_agent,
)
from .chatbot.app import ChatbotApp
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
from .gateway.whatsapp_state import (
    append_log,
    load_config,
    public_config,
    save_config,
    tail_log,
)
from .gh_sync import GitHubSyncService
from .integrations import (
    connect_integration,
    disconnect_integration,
    integrations_payload,
    set_integration_mode,
)
from .iphone_panel import _gather_system_snapshot
from .learning import learning_payload, record_execution, record_resolution_note
from .models import OPENCLAW_ALLOWED_DATA_CLASSES
from .orchestrator import Orchestrator
from .panel_settings import load_panel_settings, save_panel_settings
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
from .vault import delete_secret as vault_delete_secret
from .vault import put_secret as vault_put_secret
from .vault import vault_status
from .proton_support import proton_status_payload, store_proton_credentials

logger = logging.getLogger(__name__)

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

# Real-time payload caching: dashboard_payload() re-aggregates standards /
# tooling / learning / config-sync on every call. Cache it briefly so SSE
# streams and API polls share one computation per TTL window instead of each
# client recomputing every few seconds.
DASHBOARD_PAYLOAD_TTL_SECONDS = 7.0
_dashboard_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_dashboard_cache_lock = Lock()

SYSTEM_METRICS_TTL_SECONDS = 1.5
_system_metrics_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_system_metrics_lock = Lock()


def _cached_dashboard_payload() -> dict[str, Any]:
    """Return the dashboard payload, recomputed at most every 7 seconds."""
    with _dashboard_cache_lock:
        now = time.monotonic()
        if (
            _dashboard_cache["payload"] is None
            or now - _dashboard_cache["ts"] > DASHBOARD_PAYLOAD_TTL_SECONDS
        ):
            _dashboard_cache["payload"] = dashboard_payload(RUNTIME)
            _dashboard_cache["ts"] = now
        return _dashboard_cache["payload"]


def _cached_system_metrics() -> dict[str, Any]:
    """Return system metrics (CPU/mem/disk/network), cached for 1.5 seconds."""
    with _system_metrics_lock:
        now = time.monotonic()
        if (
            _system_metrics_cache["payload"] is None
            or now - _system_metrics_cache["ts"] > SYSTEM_METRICS_TTL_SECONDS
        ):
            _system_metrics_cache["payload"] = _gather_system_snapshot()
            _system_metrics_cache["ts"] = now
        return _system_metrics_cache["payload"]


def _gather_network_metrics() -> dict[str, Any] | None:
    """Return host network counters, or None when psutil is unavailable."""
    try:
        import psutil

        io = psutil.net_io_counters()
        if io is None:
            return None
        return {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv,
            "packets_sent": io.packets_sent,
            "packets_recv": io.packets_recv,
            "errin": io.errin,
            "errout": io.errout,
        }
    except Exception:  # noqa: BLE001
        return None

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
        "frame-src http://127.0.0.1:* ws://127.0.0.1:* http://localhost:* ws://localhost:*; "
        "img-src 'self' data:; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self' ws: wss: http://127.0.0.1:* ws://127.0.0.1:*;"
    ),
}

# Host values accepted on state-changing panel requests. Loopback defaults are
# always allowed; deployments binding a custom host/port extend the set via the
# SUBSTRATE_PANEL_HOST / SUBSTRATE_PANEL_PORT environment variables, and the
# machine's own Tailscale names/IPs are added dynamically so access through
# `tailscale serve` keeps working.
ALLOWED_PANEL_HOSTS = {
    "127.0.0.1",
    "localhost",
    "127.0.0.1:8090",
    "localhost:8090",
}
# Cross-origin (CSRF / DNS-rebinding) surface for state-changing requests:
# plain-HTTP loopback origins plus the HTTPS tailnet origin.
ALLOWED_PANEL_ORIGIN_HOSTS = {"127.0.0.1", "localhost"}
TAILSCALE_BIN = shutil.which("tailscale")

# In-memory per-IP rate limiting (sliding window of requests per client).
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_REQUESTS = 100
_RATE_LIMITS: dict[str, list[float]] = {}
_RATE_LIMITS_LOCK = Lock()

# Short-lived cache of the machine's Tailscale host names/IPs (tailscale CLI
# invocations are slow, so they only run on cache expiry).
_TAILNET_HOSTS_CACHE: dict[str, Any] = {"at": 0.0, "hosts": set()}
_TAILNET_HOSTS_TTL = 300.0
_TAILNET_HOSTS_LOCK = Lock()


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
    except Exception as exc:
        logger.error("Failed to initialize gateway: %s", exc)
    
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
TEMPLATES = Jinja2Templates(directory=str(RUNTIME.root / "substrate" / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(RUNTIME.root / "substrate" / "static")),
    name="static",
)

# Embedded Kilo chat agent (same engine as the desktop chatbot). The routes
# are registered under the panel's own /api/* paths so the Kilo Code page can
# run real autonomous sessions from the browser.
CHATBOT = ChatbotApp()
CHATBOT.attach(app)


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
        except Exception as exc:
            logger.debug("_cleanup future result failed", exc_info=True)
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


# Configuration file browser: workspace config files editable from the panel.
# Everything is validated as YAML before save and writes are atomic (temp file
# + rename), so a bad edit never corrupts a live config.
CONFIG_FILES_WHITELIST: tuple[str, ...] = (
    "workspace.yaml",
    "agents.yaml",
    "standards.yaml",
    "tool_profiles.yaml",
    "integrations.yaml",
    "upstreams.yaml",
    "config_sync_profiles.yaml",
    "chains/local-agent-chain.yaml",
)
CONFIG_FILE_MAX_CHARS = 384 * 1024


def _resolve_config_file(relative_path: str) -> Path:
    raw = Path(relative_path).as_posix()
    if raw not in CONFIG_FILES_WHITELIST:
        raise HTTPException(
            status_code=400,
            detail="Only workspace config files from the whitelist are editable.",
        )
    resolved = (RUNTIME.root / raw).resolve()
    if not resolved.is_relative_to(RUNTIME.root):
        raise HTTPException(status_code=400, detail="Path escapes the workspace.")
    return resolved


def _config_files_index() -> list[dict[str, Any]]:
    """Describe the editable config files with contents and sync metadata."""
    files: list[dict[str, Any]] = []
    try:
        sync_payload = config_sync_payload(RUNTIME)
        entries_by_path = {
            str(entry.get("source_path") or ""): entry
            for entry in sync_payload.get("entries", [])
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("config sync entries lookup failed", exc_info=True)
        entries_by_path = {}
    for relative in CONFIG_FILES_WHITELIST:
        path = _resolve_config_file(relative)
        meta: dict[str, Any] = {
            "path": relative,
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "modified_at": (
                datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
                if path.exists()
                else None
            ),
            "sync": entries_by_path.get(str(path)),
        }
        if path.exists():
            try:
                meta["content"] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                meta["content"] = ""
                meta["read_error"] = "unreadable"
        else:
            meta["content"] = ""
        files.append(meta)
    return files


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


def _panel_auth_token() -> str:
    """Return the configured panel bearer token (empty when auth is disabled)."""
    return (
        os.environ.get("PANEL_AUTH_TOKEN")
        or os.environ.get("SUBSTRATE_PANEL_AUTH_TOKEN")
        or ""
    )


def _tailnet_self_hosts() -> set[str]:
    """Host names/IPs that reach this machine through Tailscale.

    Includes the TAILSCALE_HOST override, the machine's MagicDNS name,
    hostname, Tailscale IPs, and any HTTPS serve mounts reported by
    ``tailscale serve status``. Results are cached for _TAILNET_HOSTS_TTL
    because each lookup spawns a subprocess.
    """
    now = time.monotonic()
    with _TAILNET_HOSTS_LOCK:
        if now - _TAILNET_HOSTS_CACHE["at"] < _TAILNET_HOSTS_TTL:
            return set(_TAILNET_HOSTS_CACHE["hosts"])

    base_names: set[str] = set()
    serve_ports: set[str] = set()
    env_host = os.environ.get("TAILSCALE_HOST", "").strip().lower()
    if env_host:
        base_names.add(env_host)

    if TAILSCALE_BIN:
        try:
            out = subprocess.run(
                [TAILSCALE_BIN, "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0:
                data = json.loads(out.stdout)
                self_node = data.get("Self", {}) or {}
                dns_name = str(self_node.get("DNSName", "")).strip().lower().rstrip(".")
                if dns_name:
                    base_names.add(dns_name)
                    base_names.add(dns_name.split(".", 1)[0])
                host_name = str(self_node.get("HostName", "")).strip().lower()
                if host_name:
                    base_names.add(host_name)
                for addr in self_node.get("TailscaleIPs") or []:
                    ip = str(addr).split("/")[0].strip().lower()
                    if ip:
                        base_names.add(ip)
        except Exception as exc:  # noqa: BLE001 - tailscale may be absent or offline
            logger.debug("tailscale lookup failed", exc_info=True)
            pass

        try:
            out = subprocess.run(
                [TAILSCALE_BIN, "serve", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0:
                data = json.loads(out.stdout)
                for mount in (data.get("Web") or {}):
                    host, sep, port = str(mount).partition(":")
                    if host:
                        base_names.add(host.strip().lower())
                    if sep and port:
                        serve_ports.add(port.strip())
                serve_ports.update(str(p) for p in (data.get("TCP") or {}))
        except Exception:  # noqa: BLE001
            pass

    hosts: set[str] = set()
    for base in base_names:
        hosts.add(base)
        for port in serve_ports:
            hosts.add(f"{base}:{port}")

    with _TAILNET_HOSTS_LOCK:
        _TAILNET_HOSTS_CACHE["at"] = now
        _TAILNET_HOSTS_CACHE["hosts"] = hosts
    return set(hosts)


def _effective_panel_hosts() -> set[str]:
    """Host header values accepted on state-changing panel requests."""
    hosts = set(ALLOWED_PANEL_HOSTS)
    env_host = os.environ.get("SUBSTRATE_PANEL_HOST", "").strip().lower()
    env_port = os.environ.get("SUBSTRATE_PANEL_PORT", "").strip()
    if env_host:
        hosts.add(env_host)
        if env_port:
            hosts.add(f"{env_host}:{env_port}")
    elif env_port:
        hosts.add(f"127.0.0.1:{env_port}")
        hosts.add(f"localhost:{env_port}")
    hosts.update(_tailnet_self_hosts())
    return hosts


def _origin_allowed(origin: str) -> bool:
    """Return True only for trusted panel origins.

    Accepts plain-HTTP loopback origins (the panel itself) and HTTPS origins
    served through the machine's Tailscale names (``tailscale serve``). Uses
    parsed hostname comparison so lookalike domains such as
    ``http://localhost.evil.example`` are rejected even though they start with
    ``http://localhost``.
    """
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False
    if hostname in _tailnet_self_hosts():
        return parsed.scheme == "https"
    return parsed.scheme == "http" and hostname in ALLOWED_PANEL_ORIGIN_HOSTS


def _is_exempt_webhook_path(path: str) -> bool:
    """Internet-facing, HMAC-protected webhook endpoints.

    These are exempt from Origin/Host/auth enforcement because webhook
    providers (WhatsApp, etc.) legitimately call them cross-origin with a
    valid signature.
    """
    return path.startswith("/gateway/") and "/webhook" in path


def _auth_required_for(path: str, method: str) -> bool:
    """Whether a state-changing endpoint requires the panel bearer token.

    Every POST/PUT/PATCH/DELETE must authenticate except internet-facing
    HMAC-protected webhook paths.
    """
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    return not _is_exempt_webhook_path(path)


def _bearer_matches(authorization: str | None, expected: str) -> bool:
    """Constant-time comparison of a Bearer token against the expected value."""
    if not authorization or not authorization.startswith("Bearer "):
        return False
    provided = authorization[len("Bearer "):].strip()
    if not provided:
        return False
    return secrets.compare_digest(provided, expected)


def _rate_limit_key(request: Request) -> str:
    """Client identity for rate limiting.

    Tailscale Serve (the only proxy in front of the loopback listener) appends
    the original client IP to X-Forwarded-For, so the right-most entry is the
    peer closest to us; direct loopback clients fall back to the TCP peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return f"fwd:{parts[-1]}"
    if request.client and request.client.host:
        return f"peer:{request.client.host}"
    return "peer:unknown"


def _rate_limited(request: Request) -> int:
    """Count the request; return the Retry-After seconds (0 = allowed)."""
    key = _rate_limit_key(request)
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    with _RATE_LIMITS_LOCK:
        if len(_RATE_LIMITS) > 1024:
            for stale_key, timestamps in list(_RATE_LIMITS.items()):
                if not timestamps or timestamps[-1] <= cutoff:
                    _RATE_LIMITS.pop(stale_key, None)
        timestamps = _RATE_LIMITS.get(key)
        if timestamps is None:
            _RATE_LIMITS[key] = [now]
            return 0
        timestamps = [ts for ts in timestamps if ts > cutoff]
        if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            _RATE_LIMITS[key] = timestamps
            oldest = timestamps[0]
            retry_after = int(RATE_LIMIT_WINDOW_SECONDS - (now - oldest)) + 1
            return max(1, retry_after)
        timestamps.append(now)
        _RATE_LIMITS[key] = timestamps
        return 0


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    method = request.method
    path = request.url.path

    # Per-IP rate limiting on every request except static assets and health
    # probes. Returns 429 with a Retry-After header when exceeded.
    if not (path.startswith("/static/") or path == "/healthz"):
        retry_after = _rate_limited(request)
        if retry_after:
            response = _error_response(
                request,
                429,
                "rate_limited",
                "Too many requests; please slow down.",
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

    # Origin/Host validation: state-changing requests must come from the
    # loopback panel or the machine's Tailscale HTTPS origin (CSRF /
    # DNS-rebinding protection). Internet-facing HMAC-protected webhook paths
    # are exempt.
    if method in {"POST", "PUT", "PATCH", "DELETE"} and not _is_exempt_webhook_path(path):
        origin = request.headers.get("origin")
        if origin is not None and not _origin_allowed(origin):
            return _error_response(
                request,
                403,
                "origin_forbidden",
                "Cross-origin state-changing requests are not allowed.",
            )
        host = request.headers.get("host")
        if host is not None and host.strip().lower() not in _effective_panel_hosts():
            return _error_response(
                request,
                403,
                "host_forbidden",
                "Host header is not on the panel allowlist.",
            )

    # Bearer-token auth: enforced on every state-changing endpoint when a
    # PANEL_AUTH_TOKEN (or the SUBSTRATE_PANEL_AUTH_TOKEN fallback) is
    # configured. When unset the panel keeps its default loopback-open posture.
    if _auth_required_for(path, method):
        expected_token = _panel_auth_token()
        if expected_token and not _bearer_matches(
            request.headers.get("authorization"), expected_token
        ):
            return _error_response(
                request,
                401,
                "unauthorized",
                "A valid bearer token is required for this endpoint.",
            )

    if method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            if not content_length.isdigit():
                return _error_response(
                    request,
                    400,
                    "invalid_request",
                    "Malformed Content-Length header.",
                )
            # Config-file saves legitimately carry whole YAML files (agents.yaml
            # is ~5 KB but could grow); exempt only that one endpoint.
            cap = (
                512 * 1024
                if path == "/api/config/files/save"
                else MAX_REQUEST_BODY_BYTES
            )
            if int(content_length) > cap:
                return _error_response(
                    request,
                    413,
                    "payload_too_large",
                    f"Request body exceeds {cap} bytes.",
                )
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if not path.startswith("/static/"):
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
    # Copy: TemplateResponse mutates the context dict (injects `request`), and
    # the cached payload must never be mutated by a render.
    payload = dict(_cached_dashboard_payload())
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
    payload = dict(_cached_dashboard_payload())
    payload["pinch"] = _pinch_hints()
    payload["payloads"] = DUCKY_ENGINE.list_payloads()
    payload["stage_sequence"] = RUNTIME.workspace.policy.stage_sequence
    payload["pass_sequence"] = RUNTIME.workspace.policy.pass_sequence
    payload["panel_settings"] = load_panel_settings(RUNTIME.root)
    return payload


@app.get("/api/panel/settings")
def api_panel_settings() -> dict[str, Any]:
    return load_panel_settings(RUNTIME.root)


@app.post("/api/panel/settings")
async def api_panel_settings_save(request: Request) -> dict[str, Any]:
    _ = request
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    saved = save_panel_settings(RUNTIME.root, body)
    record_execution(
        RUNTIME,
        run_type="panel-settings",
        run_id=None,
        repo_slug=None,
        stage="local",
        command="panel-settings-save",
        status="success",
        exit_code=0,
        stdout=json.dumps(saved, ensure_ascii=False),
        note="Control panel preferences updated",
    )
    return {"ok": True, "settings": saved}


@app.get("/api/runs")
def api_runs(limit: int = 100) -> dict[str, Any]:
    bounded_limit = max(1, min(limit, 500))
    runs = RUNTIME.db.list_recent_runs(limit=bounded_limit)
    return {"runs": runs, "count": len(runs)}


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


# --- Secure Vault: secrets never touch plaintext files -----------------------
@app.get("/api/vault/status")
def api_vault_status() -> dict[str, Any]:
    return vault_status(RUNTIME)


@app.post("/api/vault/put")
def api_vault_put(
    request: Request,
    service_id: str = Form(...),
    secret: str = Form(...),
    auth_method: str = Form(""),
    access_mode: str = Form("read"),
    write_directive: str = Form(""),
) -> dict[str, Any]:
    _ = request
    # 500 KiB guard is enforced globally; tighten: raw secret length
    if len(secret.encode("utf-8")) > 8192:
        raise HTTPException(status_code=400, detail="Secret exceeds 8 KiB limit.")
    try:
        result = vault_put_secret(
            RUNTIME,
            service_id=_normalize_slug(service_id, "service_id"),
            secret=secret,
            auth_method=auth_method.strip() or None,
            mode=_validate_access_mode(access_mode),
            write_directive=write_directive,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/vault/delete")
def api_vault_delete(
    request: Request,
    service_id: str = Form(...),
) -> dict[str, Any]:
    _ = request
    try:
        result = vault_delete_secret(RUNTIME, service_id=_normalize_slug(service_id, "service_id"))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


# --- Proton integration (keyring-backed; TOTP via env, never argv) ----------
@app.get("/api/proton/status")
def api_proton_status(request: Request) -> dict[str, Any]:
    _ = request
    try:
        return proton_status_payload(RUNTIME)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.get("/api/proton/last-run")
def api_proton_last_run(request: Request) -> dict[str, Any]:
    _ = request
    try:
        from .proton_support import _last_run_payload

        return _last_run_payload(RUNTIME)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/proton/store")
def api_proton_store(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    totp: str = Form(""),
) -> dict[str, Any]:
    """Persist Proton credentials to the OS keyring (no plaintext files).

    `totp` is stored for future 2FA use but is NOT consumed now (2FA not
    yet enabled). Password/TOTP are wiped from the DOM after submission.
    """
    _ = request
    email = email.strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if len(password.encode("utf-8")) > 8192:
        raise HTTPException(status_code=400, detail="Password exceeds 8 KiB limit.")
    try:
        from .proton_support import store_proton_credentials

        store_proton_credentials(RUNTIME, email, password)
    except (KeyError, ValueError) as exc:
        if isinstance(exc, KeyError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "email": email, "note": "Stored in OS keyring."}


@app.post("/api/proton/connect")
def api_proton_connect(
    request: Request,
    email: str = Form(""),
    totp: str = Form(""),
) -> dict[str, Any]:
    """Launch the bridge login in a background thread; poll /api/proton/last-run."""
    _ = request
    from .proton_support import launch_proton_connect

    try:
        return launch_proton_connect(RUNTIME, email=email or None, totp=totp)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/proton/verify")
def api_proton_verify(request: Request) -> dict[str, Any]:
    """Explicit user action: single bounded IMAP + Drive probe."""
    _ = request
    from .proton_support import verify_proton

    try:
        return verify_proton(RUNTIME)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/proton/test-email")
def api_proton_test_email(request: Request) -> dict[str, Any]:
    """Send one verification email (human-initiated via the panel)."""
    _ = request
    from .proton_support import send_test_email

    try:
        return send_test_email(RUNTIME)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/proton/disconnect")
def api_proton_disconnect(request: Request) -> dict[str, Any]:
    """Remove Proton secrets from keyring and mark disconnected."""
    _ = request
    from .proton_support import disconnect_proton

    try:
        return disconnect_proton(RUNTIME)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


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
@app.get("/__panel_auth_bootstrap__.js", include_in_schema=False)
def panel_auth_bootstrap() -> PlainTextResponse:
    """Same-origin bootstrap that injects the panel auth token into fetch.

    Loaded only by the panel's own pages. The bearer token is required on
    every state-changing endpoint; this bootstrap lets the browser UI
    authenticate without exposing the token to third-party origins. It is a
    no-op (window.PANEL_AUTH_TOKEN stays empty) when no token is configured.
    """
    token = _panel_auth_token()
    code = f"window.PANEL_AUTH_TOKEN = {json.dumps(token)};\n"
    code += (
        "(function () {\n"
        "  if (window.__panelAuthFetchPatched) return;\n"
        "  window.__panelAuthFetchPatched = true;\n"
        "  const _fetch = window.fetch.bind(window);\n"
        "  window.fetch = function (input, init) {\n"
        "    init = init || {};\n"
        "    const headers = new Headers(init.headers || {});\n"
        "    if (window.PANEL_AUTH_TOKEN && !headers.has('Authorization')) {\n"
        "      headers.set('Authorization', 'Bearer ' + window.PANEL_AUTH_TOKEN);\n"
        "    }\n"
        "    return _fetch(input, Object.assign({}, init, { headers: headers }));\n"
        "  };\n"
        "})();\n"
    )
    return PlainTextResponse(code, media_type="application/javascript")


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
                runs = RUNTIME.db.list_recent_runs(limit=20)
                stage_counts: dict[str, int] = {}
                for run in runs:
                    stage = run.get("stage") or "local"
                    stage_counts[stage] = stage_counts.get(stage, 0) + 1

                payload = {
                    "metrics": {
                        "repositories": RUNTIME.db.latest_repository_snapshots(),
                        "runs": runs,
                        "success_rate": _calculate_success_rate(runs),
                        "health": "healthy" if RUNTIME.workspace.repositories else "degraded",
                    },
                    "stage_counts": stage_counts,
                    "activity": [
                        {
                            "status": run.get("status", "unknown"),
                            "task_id": run.get("task_id", "unknown"),
                            "repo_slug": run.get("repo_slug", "unknown"),
                            "started_at": run.get("started_at"),
                        }
                        for run in runs[:5]
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

                yield f"data: {json.dumps(payload)}\n\n"
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
        append_log(RUNTIME.root, "webhook", f"verification failed for {service_id}")
        raise HTTPException(status_code=403, detail="Webhook verification failed")

    append_log(
        RUNTIME.root, "webhook", f"verification challenge answered for {service_id}"
    )
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
        append_log(RUNTIME.root, "webhook", f"signature validation failed for {service_id}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    append_log(
        RUNTIME.root,
        "webhook",
        f"received payload for {service_id} ({len(body)} bytes)",
    )
    
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
        append_log(RUNTIME.root, "send", f"outbound message to {user_id} via {service_id}")
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
WHATSAPP_CONFIG_KEYS = {
    "phone_number_id",
    "access_token",
    "app_secret",
    "verify_token",
    "webhook_url",
    "graph_api_version",
}
WHATSAPP_REQUIRED = ["phone_number_id", "access_token", "app_secret", "verify_token"]


def _whatsapp_plugin():
    """Return the live WhatsApp plugin instance or None."""
    if not GATEWAY_MANAGER:
        return None
    try:
        return GATEWAY_MANAGER.get_plugin("whatsapp")
    except Exception:  # noqa: BLE001
        return None


@app.get("/api/gateway/whatsapp/config")
async def get_whatsapp_config(request: Request):
    """Get the persisted WhatsApp configuration (secrets masked)."""
    stored = public_config(RUNTIME.root)
    plugin = _whatsapp_plugin()
    plugin_config = plugin._config if plugin else {}
    return JSONResponse(
        {
            "phone_number_id": stored.get("phone_number_id", ""),
            "verify_token_configured": bool(stored.get("verify_token")),
            "access_token_configured": bool(stored.get("access_token")),
            "app_secret_configured": bool(stored.get("app_secret")),
            "webhook_url": plugin_config.get(
                "webhook_url",
                stored.get("webhook_url")
                or f"{request.base_url}gateway/whatsapp/webhook",
            ),
        }
    )


@app.post("/api/gateway/whatsapp/config")
async def save_whatsapp_config(request: Request):
    """Validate and persist WhatsApp Cloud API credentials, then load the plugin."""
    body = await request.json()
    raw = {key: (body.get(key) or "").strip() for key in WHATSAPP_CONFIG_KEYS}
    # Empty secret fields mean "reuse the existing keyring value" (user left masked placeholder).
    try:
        existing = load_config(RUNTIME.root)
    except Exception:  # noqa: BLE001
        existing = {}
    secret_keys = ("access_token", "app_secret", "verify_token")
    config = {}
    for key in WHATSAPP_CONFIG_KEYS:
        if key in secret_keys and not raw.get(key):
            if existing.get(key):
                config[key] = existing[key]
            else:
                config[key] = ""
        else:
            config[key] = raw.get(key, "")
    missing = [field for field in WHATSAPP_REQUIRED if not config[field]]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field(s): {', '.join(missing)}",
        )
    if config.get("graph_api_version") and not re.match(
        r"^v\d+(\.\d+)?$", config["graph_api_version"]
    ):
        raise HTTPException(status_code=400, detail="Invalid graph_api_version.")

    # Load the plugin (re-registration overwrites any prior instance).
    loaded = GATEWAY_MANAGER.load_plugin("whatsapp", config)
    if not loaded:
        raise HTTPException(
            status_code=500, detail="Failed to initialize the WhatsApp plugin."
        )

    save_config(RUNTIME.root, config)
    return JSONResponse({"status": "success", "message": "Configuration saved"})


@app.post("/api/gateway/whatsapp/verify")
async def verify_whatsapp_config(request: Request):
    """Check the saved credentials against the WhatsApp Graph API for real."""
    stored = load_config(RUNTIME.root)
    if not stored.get("phone_number_id") or not stored.get("access_token"):
        raise HTTPException(status_code=400, detail="No configuration saved yet.")
    version = stored.get("graph_api_version", "v21.0")
    phone_id = stored["phone_number_id"]
    url = f"https://graph.facebook.com/{version}/{phone_id}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                params={
                    "fields": "display_phone_number,verified_name,quality_rating",
                    "access_token": stored["access_token"],
                },
            )
    except Exception as exc:  # noqa: BLE001
        append_log(
            RUNTIME.root, "verify", f"network error while verifying credentials: {exc}"
        )
        return JSONResponse(
            {"valid": False, "error": f"Network error: {exc}"}, status_code=200
        )

    if response.status_code != 200:
        detail = response.text[:500]
        append_log(
            RUNTIME.root, "verify", f"credential check rejected by Graph API: {detail}"
        )
        return JSONResponse(
            {
                "valid": False,
                "status_code": response.status_code,
                "error": detail,
            },
            status_code=200,
        )

    data = response.json()
    append_log(
        RUNTIME.root,
        "verify",
        f"credentials valid for {data.get('display_phone_number', phone_id)}",
    )
    return JSONResponse({"valid": True, "account": data})


@app.get("/api/gateway/whatsapp/status")
async def get_whatsapp_status():
    """Return the real WhatsApp connection status."""
    stored = load_config(RUNTIME.root)
    plugin = _whatsapp_plugin()
    connected = bool(plugin) and plugin._client is not None
    return JSONResponse(
        {
            "configured": bool(stored.get("phone_number_id")),
            "connected": connected,
            "status": "connected" if connected else "configured" if stored else "not_configured",
            "phone_number_id": stored.get("phone_number_id", ""),
            "verify_token_configured": bool(stored.get("verify_token")),
        }
    )


@app.post("/api/gateway/whatsapp/test")
async def send_whatsapp_test(request: Request):
    """Send a real test message to a recipient via the WhatsApp Cloud API."""
    plugin = _whatsapp_plugin()
    if not plugin:
        raise HTTPException(status_code=400, detail="Save your configuration first.")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    to = str(body.get("to") or "").strip()
    message = str(body.get("message") or "Test message from Substrate").strip()
    if not to:
        raise HTTPException(
            status_code=400,
            detail="A recipient phone number is required (E.164 format, e.g. 15551234567).",
        )
    try:
        result = await plugin.send_text(to, message)
    except Exception as exc:
        append_log(RUNTIME.root, "send", f"send failed to {to}: {exc}")
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc
    append_log(RUNTIME.root, "send", f"test message sent to {to}")
    message_id = "unknown"
    try:
        message_id = result["messages"][0]["id"]
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse(
        {"status": "success", "message": "Test message sent", "message_id": message_id}
    )


@app.get("/api/gateway/whatsapp/logs")
async def get_whatsapp_logs():
    """Return the tail of the real gateway event log."""
    return JSONResponse({"logs": tail_log(RUNTIME.root, limit=200)})


# --- Agent roster & control -------------------------------------------------------
@app.get("/api/agents")
def api_agents() -> dict[str, Any]:
    """Agent roster with cadence, tier, last run, and next-due times."""
    try:
        return agent_status_payload(RUNTIME)
    except AgentConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/agents/run")
def api_agent_run(
    agent_id: str = Form(...),
    directive: str = Form(""),
    force: str = Form("false"),
) -> JSONResponse:
    """Trigger one agent from the roster by id (agent-run equivalent)."""
    try:
        agents = load_agents_config(RUNTIME.root)
    except AgentConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    match = next((agent for agent in agents if agent.id == agent_id), None)
    if match is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent id '{agent_id}'. See /api/agents for the roster.",
        )
    run_id = uuid.uuid4().hex
    _submit(
        run_id,
        run_agent,
        RUNTIME,
        ORCHESTRATOR,
        match,
        directive=directive.strip(),
        force=_parse_bool(force),
    )
    return JSONResponse(
        {
            "ok": True,
            "agent_id": agent_id,
            "run_id": run_id,
            "status_url": f"/api/runs/{run_id}",
        }
    )


# --- Real-time system metrics -------------------------------------------------------
@app.get("/api/system/metrics")
def api_system_metrics() -> dict[str, Any]:
    """Consolidated host + substrate metrics for the Metrics page."""
    snap = _cached_system_metrics()
    runs = RUNTIME.db.list_recent_runs(limit=50)
    metrics = RUNTIME.db.dashboard_metrics()
    snap["network"] = _gather_network_metrics()
    snap["runs"] = {
        "recent_total": len(runs),
        "running": metrics.get("runs_running", 0),
        "success_rate": _calculate_success_rate(runs),
        "repositories": metrics.get("repositories_total", 0),
        "sources": metrics.get("sources_total", 0),
    }
    snap["timestamp"] = datetime.now(UTC).isoformat()
    return snap


# --- Pipelines (consolidated into the panel; legacy /pipelines/* still mounted) -----
@app.get("/api/pipelines")
def api_pipelines(enabled_only: bool = False) -> dict[str, Any]:
    pipelines = PIPELINE_REGISTRY.list(enabled_only=enabled_only)
    return {
        "pipelines": [p.to_dict() for p in pipelines],
        "count": len(pipelines),
        "registry_dir": str(RUNTIME.root / "pipelines"),
    }


# --- Configuration file browser -----------------------------------------------------
@app.get("/api/config/files")
def api_config_files() -> dict[str, Any]:
    return {"files": _config_files_index()}


@app.post("/api/config/files/save")
async def api_config_files_save(request: Request) -> dict[str, Any]:
    """Save an edited workspace config file with YAML validation + atomic write."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body.") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    relative = str(body.get("path") or "")
    content = str(body.get("content") or "")
    if len(content) > CONFIG_FILE_MAX_CHARS:
        raise HTTPException(status_code=413, detail="File content is too large.")
    path = _resolve_config_file(relative)

    # Validate YAML before touching disk so a bad edit never breaks the panel.
    try:
        import yaml

        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=422, detail=f"YAML validation failed: {exc}"
        ) from exc
    if parsed is None and content.strip():
        raise HTTPException(
            status_code=422, detail="YAML validation failed: empty document."
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Write failed: {exc}") from exc

    record_execution(
        RUNTIME,
        run_type="config-edit",
        run_id=None,
        repo_slug=None,
        stage="local",
        command=f"config-edit {relative}",
        status="success",
        exit_code=0,
        stdout=f"Saved {relative} ({len(content)} chars)",
        note="Panel config file edit",
    )
    return {"ok": True, "path": relative, "size": len(content)}


# --- Terminal configuration -----------------------------------------------------------
@app.get("/api/terminal/config")
def api_terminal_config(request: Request) -> dict[str, Any]:
    """Return the ttyd URL compatible with the current panel transport.

    Over plain HTTP the iframe targets http://127.0.0.1:8765 directly. Over
    HTTPS (Tailscale Serve on :10000) the browser would block the mixed-content
    iframe, so the terminal is served via its own Tailscale HTTPS mapping
    (``tailscale serve --https=8765``) on the same hostname.
    """
    scheme = request.url.scheme
    host = request.url.hostname or "127.0.0.1"
    if scheme == "https":
        return {
            "url": f"https://{host}:8765",
            "mode": "tailscale_https",
            "note": "Served over Tailscale HTTPS to avoid mixed content.",
        }
    return {
        "url": "http://127.0.0.1:8765",
        "mode": "loopback_http",
        "note": "Direct loopback HTTP.",
    }


# --- Run detail API -------------------------------------------------------------------
@app.get("/api/runs/{run_id}/events")
def api_run_events(run_id: str, limit: int = 200) -> dict[str, Any]:
    run = RUNTIME.db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "events": RUNTIME.db.list_run_events(run_id, limit=max(1, min(limit, 500))),
    }


@app.post("/api/runs/{run_id}/cancel")
def api_run_cancel(run_id: str) -> dict[str, Any]:
    """Request cancellation of a queued orchestrator task.

    Only queued (not yet started) tasks can be cancelled; an already-running
    thread cannot be interrupted safely.
    """
    run = RUNTIME.db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    with RUN_FUTURES_LOCK:
        future = RUN_FUTURES.get(run_id)
    if future is None or future.done():
        raise HTTPException(status_code=400, detail="Run is not currently executing.")
    cancelled = future.cancel()
    if not cancelled:
        raise HTTPException(
            status_code=400,
            detail="Run is already executing and cannot be cancelled.",
        )
    return {"ok": True, "run_id": run_id}


# Legacy ops panel endpoints and API routes above.
# The root "/" redirects to the legacy dashboard which provides the full
# operational overview (repositories, runs, standards, tooling, integrations).
from starlette.responses import RedirectResponse

# Include dashboard and pipelines routers
dashboard_router = create_dashboard_router(
    templates_dir=RUNTIME.root / "substrate" / "dashboard" / "templates",
    static_dir=RUNTIME.root / "substrate" / "dashboard" / "static",
)
pipelines_router = create_pipelines_router(PIPELINE_REGISTRY, PIPELINE_ENGINE)
app.include_router(dashboard_router)
app.include_router(pipelines_router)

# iPhone webapp panel extensions (automations + live system stream). Additive.
from .iphone_panel import router as iphone_panel_router

app.include_router(iphone_panel_router)


@app.get("/")
def root_redirect(request: Request):
    """Redirect the root URL to the modern control panel."""
    return RedirectResponse(url="/panel", status_code=302)

