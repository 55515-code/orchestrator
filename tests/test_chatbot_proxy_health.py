#!/usr/bin/env python3
"""Regression tests for the chatbot's prefill-proxy health probe.

Background
----------
`substrate/chatbot/agent.py` called `_proxy_healthy(base)` in
`_ensure_prefill_proxy()`, but the function was never defined. Because
`ChatbotConfig.prefill_proxy_enabled` defaults to True, every chat task hit an
unconditional `NameError`. Ruff's F821 surfaced it once the lint gate was
repaired; no test covered the path.

These tests pin both halves of the contract:
  1. the symbol exists and is importable, and
  2. it degrades to False on any failure rather than propagating an exception,
     because a proxy outage must never block chat.
"""

from __future__ import annotations

import http.server
import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from substrate.chatbot.agent import _proxy_healthy  # noqa: E402


@contextmanager
def _stub_server(handler_cls):
    """Run a throwaway HTTP server on an ephemeral port."""
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _make_handler(status: int, body: bytes, expect_path: str = "/__health"):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") != expect_path.rstrip("/"):
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):  # silence test noise
            return

    return Handler


def test_symbol_exists():
    """The original bug was a missing symbol; assert it is defined and callable."""
    assert callable(_proxy_healthy)


def test_healthy_proxy_returns_true():
    body = json.dumps({"ok": True, "service": "kilo-prefill-proxy"}).encode()
    with _stub_server(_make_handler(200, body)) as base:
        assert _proxy_healthy(base) is True


def test_probes_the_health_path():
    """A 404 on /__health (server only serves /other) must read as unhealthy."""
    body = json.dumps({"ok": True}).encode()
    with _stub_server(_make_handler(200, body, expect_path="/other")) as base:
        assert _proxy_healthy(base) is False


def test_ok_false_returns_false():
    body = json.dumps({"ok": False, "detail": "degraded"}).encode()
    with _stub_server(_make_handler(200, body)) as base:
        assert _proxy_healthy(base) is False


def test_non_200_returns_false():
    with _stub_server(_make_handler(503, b"{}")) as base:
        assert _proxy_healthy(base) is False


def test_unparseable_body_returns_false():
    with _stub_server(_make_handler(200, b"not json")) as base:
        assert _proxy_healthy(base) is False


def test_connection_refused_returns_false_without_raising():
    """The critical property: an absent proxy degrades, it does not raise."""
    assert _proxy_healthy("http://127.0.0.1:1") is False


def test_trailing_slash_is_tolerated():
    body = json.dumps({"ok": True}).encode()
    with _stub_server(_make_handler(200, body)) as base:
        assert _proxy_healthy(base + "/") is True
