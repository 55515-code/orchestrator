"""Local rewrite proxy that fixes Anthropic "assistant message prefill" 400s.

Background
----------
The desktop chatbot (and any ``kilo run`` flow) sends conversation history
through the Kilo Gateway (``https://api.kilo.ai/api/gateway``) and, for
direct-OpenRouter setups, ``https://openrouter.ai/api/v1``. Agentic
conversations can end with an ``assistant`` message (a tool call that was
never followed by its result, an interrupted turn, a resume-with-history
flow). Anthropic-family models reject that shape on *every* provider route
(Anthropic direct, Bedrock, Vertex, Claude AWS) before routing can help,
which is why the failure repeats across all 7 provider attempts.

This proxy sits in front of those upstreams and rewrites the ``messages``
array of chat requests *before* they are forwarded, so the fix applies
regardless of provider route or credential type. It is interposed without
any TLS interception: the Kilo CLI's upstream base URL is pointed at this
proxy via plain ``http://127.0.0.1:<port>`` (``KILO_API_URL`` and
``KILO_OPENROUTER_BASE``), and the proxy itself opens the TLS connection to
the real upstream.

Routing (by request path, matching the Kilo CLI's known endpoints):

- ``/api/gateway/*``            -> https://api.kilo.ai  (Kilo Gateway)
- ``/api/v1/*``                 -> https://openrouter.ai (OpenRouter)
- anything else                 -> https://api.kilo.ai  (auth/models/etc.)

Every request is relayed as-is except chat payloads that (a) are JSON with
a ``messages`` array and (b) name an Anthropic-family model; those are
normalized by :mod:`substrate.chat_compat`. SSE streaming responses pass
through untouched.

No API keys are logged. On failure the proxy returns a 502 with a
diagnostic body and never re-sends credentials anywhere other than the
configured upstream.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .chat_compat import normalize_request_payload

logger = logging.getLogger("substrate.prefill_proxy")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8477
DEFAULT_PID_FILE = "state/prefill-proxy.pid"
DEFAULT_LOG_FILE = "state/prefill-proxy.log"

GATEWAY_UPSTREAM = ("api.kilo.ai", 443)
OPENROUTER_UPSTREAM = ("openrouter.ai", 443)

# Headers that must not be forwarded between the two connections.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
# Response headers we recompute ourselves (we always use close-delimited
# bodies so streaming works without chunked transfer-encoding).
_RESPONSE_HEADERS_TO_DROP = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "content-length",
}

PLACEHOLDER_USER_TURN = "Continue."


def route_upstream(path: str) -> tuple[str, int]:
    """Map a request path to its upstream (host, port)."""
    if path.startswith("/api/gateway"):
        return GATEWAY_UPSTREAM
    if path.startswith("/api/v1/"):
        return OPENROUTER_UPSTREAM
    return GATEWAY_UPSTREAM


class PrefillProxy:
    """Rewrite proxy with a small amount of process-local telemetry."""

    def __init__(self, *, mode: str = "strip", placeholder: str = PLACEHOLDER_USER_TURN) -> None:
        self.mode = mode
        self.placeholder = placeholder
        self._lock = threading.Lock()
        self.rewritten_requests = 0
        self.relayed_requests = 0
        self.failed_requests = 0
        self.last_rewrite_reason: str | None = None
        self.started_at = time.time()

    def normalize(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
        with self._lock:
            self.rewritten_requests += 1
        normalized, changed, reason = normalize_request_payload(
            payload,
            mode=self.mode,
            placeholder=self.placeholder,
        )
        if changed:
            with self._lock:
                self.last_rewrite_reason = reason
        return normalized, changed, reason

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "placeholder": self.placeholder,
                "relayed_requests": self.relayed_requests,
                "rewritten_requests": self.rewritten_requests,
                "failed_requests": self.failed_requests,
                "last_rewrite_reason": self.last_rewrite_reason,
                "uptime_seconds": round(time.time() - self.started_at, 1),
            }


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "KiloPrefillProxy/1.0"

    # Bound on how large a request body we will buffer for rewriting.
    MAX_REWRITE_BODY = 64 * 1024 * 1024

    @property
    def proxy(self) -> PrefillProxy:
        return self.server.proxy  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path.rstrip("/") in ("/__status", "/__health"):
            self._send_status()
            return
        self._relay()

    def do_POST(self) -> None:  # noqa: N802
        self._relay()

    def do_PUT(self) -> None:  # noqa: N802
        self._relay()

    def do_PATCH(self) -> None:  # noqa: N802
        self._relay()

    def do_DELETE(self) -> None:  # noqa: N802
        self._relay()

    def _send_status(self) -> None:
        body = json.dumps(
            {"ok": True, "service": "kilo-prefill-proxy", "stats": self.proxy.stats()}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = self.headers.get("Content-Length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                size = 0
            if size > self.MAX_REWRITE_BODY:
                raise RuntimeError(f"request body too large to buffer ({size} bytes)")
            return self.rfile.read(size)
        return b""

    def _relay(self) -> None:
        host, port = route_upstream(self.path)
        try:
            body = self._read_body()
        except Exception as exc:  # noqa: BLE001
            return self._send_error(400, f"failed reading request body: {exc}")

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP_BY_HOP
        }
        # Never forward the host header of the proxy itself.
        headers.pop("Host", None)
        headers["Host"] = host

        rewrite_reason = ""
        if body and "application/json" in (headers.get("Content-Type") or "").lower():
            try:
                payload = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
                try:
                    normalized, changed, reason = self.proxy.normalize(payload)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("payload normalization failed")
                    return self._send_error(
                        502, f"internal payload normalization failure: {exc}"
                    )
                if changed:
                    rewrite_reason = reason
                    body = json.dumps(normalized, ensure_ascii=False).encode("utf-8")
                    headers["Content-Length"] = str(len(body))

        try:
            self._forward(host, port, headers, body)
        except Exception as exc:  # noqa: BLE001
            logger.exception("upstream relay to %s failed", host)
            with self.proxy._lock:
                self.proxy.failed_requests += 1
            return self._send_error(502, f"upstream relay failed: {exc}")

        if rewrite_reason:
            logger.info("rewrote chat payload for %s: %s", self.path, rewrite_reason)
        with self.proxy._lock:
            self.proxy.relayed_requests += 1

    def _forward(
        self,
        host: str,
        port: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        conn = http.client.HTTPSConnection(host, port, timeout=300)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
        except Exception:
            conn.close()
            raise

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() in _RESPONSE_HEADERS_TO_DROP:
                continue
            self.send_header(key, value)
        self.send_header("Connection", "close")
        self.end_headers()

        try:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            conn.close()

    def _send_error(self, status: int, message: str) -> None:
        body = json.dumps(
            {
                "error": {
                    "type": "kilo_prefill_proxy_error",
                    "message": message,
                    "hint": (
                        "The local prefill-fix proxy could not relay the request. "
                        "Check that the upstream is reachable and that the proxy "
                        "process is healthy."
                    ),
                }
            }
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


class PrefillProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], proxy: PrefillProxy) -> None:
        self.proxy = proxy
        super().__init__(addr, ProxyHandler)


def serve_forever(*, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, mode: str = "strip") -> None:
    """Run the proxy in the foreground (blocking)."""
    proxy = PrefillProxy(mode=mode)
    server = PrefillProxyServer((host, port), proxy)
    logger.info("kilo prefill-fix proxy listening on http://%s:%d (mode=%s)", host, port, mode)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def _daemon_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def start_daemon(
    *,
    root: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    mode: str = "strip",
    pid_file: str = DEFAULT_PID_FILE,
    log_file: str = DEFAULT_LOG_FILE,
) -> dict[str, Any]:
    """Launch the proxy as a detached background process."""
    pid_path = root / pid_file
    if pid_path.exists():
        pid = _read_pid(pid_path)
        if pid and _pid_alive(pid):
            return {"started": False, "pid": pid, "reason": "already running"}

    log_path = root / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    code = (
        "from substrate.prefill_proxy import serve_forever;"
        f"serve_forever(host={host!r}, port={port!r}, mode={mode!r})"
    )
    log_handle = open(log_path, "ab", buffering=0)
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=str(root),
        env=_daemon_env(),
        start_new_session=True,
    )
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _probe(host, port):
            return {
                "started": True,
                "pid": process.pid,
                "log_file": str(log_path),
                "pid_file": str(pid_path),
            }
        if process.poll() is not None:
            raise RuntimeError(
                "prefill proxy exited immediately; see log at "
                f"{log_path}"
            )
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError(f"prefill proxy did not become ready on {host}:{port}")


def stop_daemon(*, root: Path, pid_file: str = DEFAULT_PID_FILE) -> dict[str, Any]:
    pid_path = root / pid_file
    if not pid_path.exists():
        return {"stopped": False, "reason": "no pid file"}
    pid = _read_pid(pid_path)
    if not pid or not _pid_alive(pid):
        pid_path.unlink(missing_ok=True)
        return {"stopped": False, "reason": "not running"}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.2)
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    pid_path.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid}


def status_daemon(
    *,
    root: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    pid_file: str = DEFAULT_PID_FILE,
) -> dict[str, Any]:
    pid_path = root / pid_file
    pid = _read_pid(pid_path) if pid_path.exists() else None
    alive = bool(pid and _pid_alive(pid))
    stats: dict[str, Any] | None = None
    if alive:
        try:
            stats = _probe(host, port, include_stats=True)
        except Exception:  # noqa: BLE001
            stats = None
    return {
        "running": alive,
        "pid": pid,
        "host": host,
        "port": port,
        "stats": stats,
    }


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _probe(host: str, port: int, include_stats: bool = False) -> Any:
    """Return True (or the stats dict) when the proxy answers on host:port."""
    conn = http.client.HTTPConnection(host, port, timeout=3)
    try:
        conn.request("GET", "/__status")
        response = conn.getresponse()
        body = response.read()
        if response.status != 200:
            return None if not include_stats else None
        if not include_stats:
            return True
        return json.loads(body.decode("utf-8")).get("stats")
    finally:
        conn.close()


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
