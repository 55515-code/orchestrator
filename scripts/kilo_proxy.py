#!/usr/bin/env python3
"""OpenAI-compatible proxy routing chat completions through the Kilo CLI
(cloud-first) with automatic fallback to local Ollama.

Routing (per request):
1. Probe the Kilo CLI (``kilo --version``, timeout-bounded). If healthy, the
   request is executed via ``kilo run --auto --format json``.
2. If Kilo is unhealthy, probe local Ollama (``/api/tags``). If healthy, the
   request is forwarded to Ollama's OpenAI-compatible endpoint.
3. If neither is healthy, return 503 in OpenAI error format.

Endpoints:
- POST /v1/chat/completions  (OpenAI chat completions, incl. SSE streaming)
- GET  /v1/models
- GET  /health

Configuration comes from environment variables (all optional):
- KILO_PROXY_HOST      default 127.0.0.1
- KILO_PROXY_PORT      default 4097
- KILO_BINARY          auto-detected (PATH, then npm-global install)
- KILO_WORKSPACE       default ~/codespace
- KILO_SERVER_PASSWORD default: parsed from ~/.openclaw/openclaw.json
- OLLAMA_BASE_URL      default http://127.0.0.1:11434
- OLLAMA_MODEL         default llama3.1:8b
- KILO_PROXY_LOG       default ~/codespace/memory/kilo-proxy.log
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4097
DEFAULT_WORKSPACE = str(Path.home() / "codespace")
DEFAULT_LOG_FILE = str(Path.home() / "codespace" / "memory" / "kilo-proxy.log")
DEFAULT_OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_MODEL_IDS = ("llama3.1:8b", "qwen2.5-coder:7b")

KILO_BINARY_HINTS = [
    "/home/ahron/.npm-global/lib/node_modules/@kilocode/cli/bin/kilo",
    "/usr/local/bin/kilo",
    "/usr/bin/kilo",
]
KILO_HEALTH_TIMEOUT = 5.0
OLLAMA_HEALTH_TIMEOUT = 2.0
KILO_RUN_TIMEOUT = 600.0
HEALTH_TTL = 3.0
MAX_CONCURRENT_KILO = 2

KILO_MODELS = [
    "kilo-auto/free",
    "kilo/anthropic/claude-opus-5",
    "kilo/openai/gpt-4.1",
    "kilo/google/gemini-pro-latest",
    "kilo/deepseek/deepseek-v4-flash-latest",
]

logger = logging.getLogger("kilo_proxy")


class ProxyBackendError(RuntimeError):
    """Raised when the selected backend fails to produce a response."""


def _utc_timestamp() -> int:
    return int(time.time())


def _openai_error(status: int, err_type: str, message: str, code: str | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"message": message, "type": err_type}}
    if code:
        payload["error"]["code"] = code
    return JSONResponse(status_code=status, content=payload)


def resolve_kilo_binary() -> str:
    found = shutil.which("kilo") or shutil.which("kilo-cli")
    if found:
        return found
    for candidate in KILO_BINARY_HINTS:
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return "kilo"


def resolve_server_password() -> str:
    env_value = os.environ.get("KILO_SERVER_PASSWORD", "").strip()
    if env_value:
        return env_value
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        providers = payload.get("models", {}).get("providers", {})
        api_key = str(providers.get("kilo-proxy", {}).get("apiKey", "")) or str(
            providers.get("kilo", {}).get("apiKey", "")
        )
        if api_key.startswith("kilo:"):
            return api_key.split(":", 1)[1]
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        if isinstance(content, list):
            chunks = []
            for segment in content:
                if isinstance(segment, dict) and segment.get("type") == "text":
                    chunks.append(str(segment.get("text") or ""))
            content = " ".join(chunks)
        text = str(content or "").strip()
        if not text:
            continue
        if role == "system":
            parts.append(f"System: {text}")
        elif role == "assistant":
            parts.append(f"Assistant: {text}")
        else:
            parts.append(f"User: {text}")
    return "\n\n".join(parts).strip()


class Proxy:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        kilo_binary: str,
        workspace: str,
        server_password: str,
        ollama_base: str,
        ollama_model: str,
        log_file: str,
        max_concurrent: int = MAX_CONCURRENT_KILO,
    ) -> None:
        self.host = host
        self.port = port
        self.kilo_binary = kilo_binary
        self.workspace = workspace
        self.server_password = server_password
        self.ollama_base = ollama_base.rstrip("/")
        self.ollama_model = ollama_model
        self.log_file = log_file
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(KILO_RUN_TIMEOUT, connect=OLLAMA_HEALTH_TIMEOUT))
        self.kilo_semaphore = asyncio.Semaphore(max_concurrent)
        self._health_lock = asyncio.Lock()
        self._kilo_health: tuple[bool, float] | None = None
        self._ollama_health: tuple[bool, float] | None = None
        self.started_at = _utc_timestamp()
        self.request_count = 0
        self.kilo_routed = 0
        self.ollama_routed = 0

    @classmethod
    def from_env(cls) -> Proxy:
        return cls(
            host=os.environ.get("KILO_PROXY_HOST", DEFAULT_HOST),
            port=int(os.environ.get("KILO_PROXY_PORT", DEFAULT_PORT)),
            kilo_binary=os.environ.get("KILO_BINARY") or resolve_kilo_binary(),
            workspace=os.environ.get("KILO_WORKSPACE", DEFAULT_WORKSPACE),
            server_password=resolve_server_password(),
            ollama_base=os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE),
            ollama_model=os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            log_file=os.environ.get("KILO_PROXY_LOG", DEFAULT_LOG_FILE),
        )

    async def kilo_healthy(self) -> bool:
        now = time.monotonic()
        async with self._health_lock:
            if self._kilo_health and now - self._kilo_health[1] < HEALTH_TTL:
                return self._kilo_health[0]
        healthy = await self._probe_kilo()
        async with self._health_lock:
            self._kilo_health = (healthy, time.monotonic())
        return healthy

    async def _probe_kilo(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.kilo_binary,
                "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=KILO_HEALTH_TIMEOUT)
            return proc.returncode == 0
        except (TimeoutError, OSError):
            return False

    async def ollama_healthy(self) -> bool:
        now = time.monotonic()
        async with self._health_lock:
            if self._ollama_health and now - self._ollama_health[1] < HEALTH_TTL:
                return self._ollama_health[0]
        healthy = await self._probe_ollama()
        async with self._health_lock:
            self._ollama_health = (healthy, time.monotonic())
        return healthy

    async def _probe_ollama(self) -> bool:
        try:
            response = await self.client.get(f"{self.ollama_base}/api/tags", timeout=OLLAMA_HEALTH_TIMEOUT)
            return response.status_code == 200
        except (TimeoutError, httpx.HTTPError):
            return False

    def is_local_model(self, model: str) -> bool:
        normalized = model.strip().lower()
        if normalized.startswith("ollama/"):
            return True
        return normalized in OLLAMA_MODEL_IDS

    def normalize_kilo_model(self, model: str) -> str:
        normalized = model.strip().lower()
        for prefix in ("kilo-proxy/", "kilo/", "ollama/"):
            normalized = normalized.removeprefix(prefix)
        return normalized

    def normalize_ollama_model(self, model: str) -> str:
        normalized = model.strip().lower()
        for prefix in ("ollama/", "kilo-proxy/", "kilo/"):
            normalized = normalized.removeprefix(prefix)
        if normalized in OLLAMA_MODEL_IDS:
            return normalized
        return self.ollama_model

    async def resolve_route(self, model: str) -> tuple[str | None, bool]:
        kilo_ok = await self.kilo_healthy()
        ollama_ok = await self.ollama_healthy()
        if self.is_local_model(model):
            if ollama_ok:
                return "ollama", True
            if kilo_ok:
                return "kilo", False
            return None, False
        if kilo_ok:
            return "kilo", True
        if ollama_ok:
            return "ollama", False
        return None, False

    async def run_kilo(self, prompt: str, model: str, timeout: float = KILO_RUN_TIMEOUT) -> str:
        command = [
            self.kilo_binary,
            "run",
            "--auto",
            "--format",
            "json",
            "--dir",
            self.workspace,
        ]
        normalized = self.normalize_kilo_model(model)
        # kilo-auto/free is Kilo's default routing alias, not a literal model ID.
        # Omit --model so Kilo uses its configured default (kilo/kilo-auto/free).
        if normalized in KILO_MODELS and normalized != "kilo-auto/free":
            command.extend(["--model", normalized])
        command.append(prompt)

        env = os.environ.copy()
        env["KILO_NO_TITLE"] = "1"

        proc: asyncio.subprocess.Process | None = None

        async def _drain_stderr() -> str:
            assert proc is not None and proc.stderr is not None
            return (await proc.stderr.read()).decode("utf-8", "replace")

        try:
            async with asyncio.timeout(timeout):
                async with self.kilo_semaphore:
                    proc = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env,
                    )
                    stderr_future = asyncio.ensure_future(_drain_stderr())
                    text_parts: list[str] = []
                    session_error: str | None = None
                    assert proc.stdout is not None
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        event_type = str(event.get("type") or "")
                        part = event.get("part") or {}
                        if not isinstance(part, dict):
                            part = {}
                        if event_type == "text":
                            text = str(part.get("text") or "").strip()
                            if text:
                                text_parts.append(text)
                        elif event_type in ("session.error", "error"):
                            session_error = str(part.get("text") or part.get("error") or event_type)
                    return_code = await proc.wait()
                    stderr = await stderr_future
                    if return_code != 0:
                        detail = stderr.strip() or session_error or "no output"
                        raise ProxyBackendError(f"kilo run exited {return_code}: {detail}")
                    if session_error:
                        raise ProxyBackendError(session_error)
                    content = "\n\n".join(text_parts).strip()
                    if not content:
                        raise ProxyBackendError(f"kilo returned an empty response: {stderr.strip() or 'no output'}")
                    return content
        except TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise ProxyBackendError(f"kilo run timed out after {timeout:.0f}s") from None
        except BaseException:
            if proc is not None and proc.returncode is None:
                proc.kill()
            raise

    async def run_ollama(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.normalize_ollama_model(model), "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            response = await self.client.post(
                f"{self.ollama_base}/v1/chat/completions",
                json=payload,
                timeout=KILO_RUN_TIMEOUT,
            )
            if response.status_code != 200:
                raise ProxyBackendError(f"ollama returned HTTP {response.status_code}: {response.text[:500]}")
            return response.json()
        except httpx.HTTPError as exc:
            raise ProxyBackendError(f"ollama request failed: {type(exc).__name__}: {exc}") from None

    def completion_payload(
        self, content: str, model: str, request_id: str, route: str
    ) -> dict[str, Any]:
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": _utc_timestamp(),
            "model": model,
            "provider": route,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def stream_response(self, content: str, model: str, request_id: str) -> StreamingResponse:
        chunk_id = f"chatcmpl-{request_id}"
        created = _utc_timestamp()

        def chunk(payload: dict[str, Any]) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        def generate():
            yield chunk(
                {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
                }
            )
            yield chunk(
                {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "kilo-proxy",
            "uptime_seconds": _utc_timestamp() - self.started_at,
            "requests": self.request_count,
            "kilo_routed": self.kilo_routed,
            "ollama_routed": self.ollama_routed,
            "kilo_binary": self.kilo_binary,
            "kilo_server_password_set": bool(self.server_password),
            "ollama_base": self.ollama_base,
            "ollama_model": self.ollama_model,
            "workspace": self.workspace,
        }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    proxy = Proxy.from_env()
    _app.state.proxy = proxy
    logger.info(
        "kilo-proxy started host=%s port=%d kilo_binary=%s workspace=%s ollama=%s password_set=%s",
        proxy.host,
        proxy.port,
        proxy.kilo_binary,
        proxy.workspace,
        proxy.ollama_base,
        bool(proxy.server_password),
    )
    yield
    await proxy.client.aclose()
    logger.info("kilo-proxy stopped")


app = FastAPI(title="Kilo Proxy", version="1.0.0", lifespan=lifespan)


@app.get("/health", response_model=None)
async def health(request: Request) -> JSONResponse:
    proxy: Proxy = request.app.state.proxy
    kilo_ok = await proxy.kilo_healthy()
    ollama_ok = await proxy.ollama_healthy()
    return JSONResponse(
        status_code=200,
        content={
            **proxy.status(),
            "health": "ok",
            "kilo_healthy": kilo_ok,
            "ollama_healthy": ollama_ok,
            "route": "kilo" if kilo_ok else ("ollama" if ollama_ok else "unavailable"),
        },
    )


@app.get("/v1/models", response_model=None)
async def models(_request: Request) -> JSONResponse:
    entries = []
    for model_id in KILO_MODELS:
        entries.append({"id": model_id, "object": "model", "owned_by": "kilo"})
    for model_id in OLLAMA_MODEL_IDS:
        entries.append({"id": model_id, "object": "model", "owned_by": "ollama"})
    return JSONResponse(status_code=200, content={"object": "list", "data": entries})


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    proxy: Proxy = request.app.state.proxy
    request_id = uuid.uuid4().hex[:12]
    start = time.monotonic()
    proxy.request_count += 1

    try:
        body = await request.json()
    except Exception:
        logger.warning("[%s] invalid JSON body", request_id)
        return _openai_error(400, "invalid_request_error", "Request body must be valid JSON")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        logger.warning("[%s] missing messages", request_id)
        return _openai_error(400, "invalid_request_error", "Request body must include a non-empty 'messages' array")

    requested_model = str(body.get("model") or "kilo-auto/free")
    stream = bool(body.get("stream", False))
    max_tokens = body.get("max_tokens")
    temperature = body.get("temperature")
    prompt = messages_to_prompt(messages)
    if not prompt:
        logger.warning("[%s] empty prompt", request_id)
        return _openai_error(400, "invalid_request_error", "Messages contain no usable text content")

    route, cloud_first = await proxy.resolve_route(requested_model)
    if route is None:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "[%s] route=none model=%s status=503 duration_ms=%d (kilo and ollama both down)",
            request_id,
            requested_model,
            duration_ms,
        )
        return _openai_error(
            503,
            "service_unavailable",
            "Both Kilo and Ollama are unavailable. Kilo CLI and Ollama (127.0.0.1:11434) must be reachable.",
            code="backends_unavailable",
        )

    error_message = ""
    try:
        if route == "kilo":
            proxy.kilo_routed += 1
            content = await proxy.run_kilo(prompt, requested_model)
        else:
            proxy.ollama_routed += 1
            ollama_response = await proxy.run_ollama(messages, requested_model, max_tokens, temperature)
            content = ""
            choices = ollama_response.get("choices") or []
            if choices:
                content = str(choices[0].get("message", {}).get("content") or "")
            if not content:
                raise ProxyBackendError("ollama returned an empty response")
    except ProxyBackendError as exc:
        error_message = str(exc)
        logger.warning(
            "[%s] route=%s model=%s backend_error=%s",
            request_id,
            route,
            requested_model,
            error_message,
        )
        if route == "kilo" and cloud_first:
            fallback_ok = await proxy.ollama_healthy()
            if not fallback_ok:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.error(
                    "[%s] route=kilo->fail model=%s status=503 duration_ms=%d error=%s",
                    request_id,
                    requested_model,
                    duration_ms,
                    error_message,
                )
                return _openai_error(
                    503,
                    "upstream_error",
                    f"Kilo failed and Ollama fallback is unavailable: {error_message}",
                    code="upstream_error",
                )
            try:
                proxy.ollama_routed += 1
                ollama_response = await proxy.run_ollama(messages, requested_model, max_tokens, temperature)
                content = ""
                choices = ollama_response.get("choices") or []
                if choices:
                    content = str(choices[0].get("message", {}).get("content") or "")
                if not content:
                    raise ProxyBackendError("ollama fallback returned an empty response")
                route = "ollama"
            except ProxyBackendError as fallback_error:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.error(
                    "[%s] route=kilo->ollama model=%s status=500 duration_ms=%d kilo_error=%s ollama_error=%s",
                    request_id,
                    requested_model,
                    duration_ms,
                    error_message,
                    str(fallback_error),
                )
                return _openai_error(
                    500,
                    "upstream_error",
                    f"Kilo failed ({error_message}) and Ollama fallback also failed: {fallback_error}",
                    code="upstream_error",
                )
        else:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "[%s] route=%s model=%s status=500 duration_ms=%d error=%s",
                request_id,
                route,
                requested_model,
                duration_ms,
                error_message,
            )
            return _openai_error(500, "upstream_error", error_message, code="upstream_error")
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "[%s] route=%s model=%s status=500 duration_ms=%d error=%s",
            request_id,
            route,
            requested_model,
            duration_ms,
            f"{type(exc).__name__}: {exc}",
        )
        return _openai_error(500, "internal_error", f"{type(exc).__name__}: {exc}", code="internal_error")

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "[%s] route=%s model=%s status=200 duration_ms=%d",
        request_id,
        route,
        requested_model,
        duration_ms,
    )
    if stream:
        return proxy.stream_response(content, requested_model, request_id)
    return JSONResponse(status_code=200, content=proxy.completion_payload(content, requested_model, request_id, route))


def main() -> None:
    proxy = Proxy.from_env()
    log_path = Path(proxy.log_file).expanduser()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.addHandler(stream)

    if not Path(proxy.kilo_binary).is_file():
        logger.warning("kilo binary not found at '%s'; cloud routing will fail until it is installed", proxy.kilo_binary)
    logger.info("configured kilo=%s ollama=%s workspace=%s log=%s", proxy.kilo_binary, proxy.ollama_base, proxy.workspace, log_path)

    uvicorn.run(app, host=proxy.host, port=proxy.port, log_level="warning")


if __name__ == "__main__":
    main()
