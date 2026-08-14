"""FastAPI application exposing the desktop chatbot chat UI and API."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .agent import DONE_MARKER, KiloAgent
from .config import ChatbotConfig
from .store import ChatMessage, ChatStore

STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class SessionCreateRequest(BaseModel):
    session_id: str | None = None


class ChatbotApp:
    """Wires the Kilo agent and chat store into a FastAPI app."""

    def __init__(
        self,
        config: ChatbotConfig | None = None,
        store: ChatStore | None = None,
        agent: KiloAgent | None = None,
    ) -> None:
        self.config = config or ChatbotConfig.load()
        self.store = store or ChatStore()
        self._tasks: dict[str, Any] = {}
        self._assistant_buffers: dict[str, str] = {}
        self._lock = threading.Lock()
        self.agent = agent or KiloAgent(self.config, on_message=self._on_message)
        self.app = self._build_app()

    # -- callbacks ------------------------------------------------------

    def _on_message(self, task_id: str, session_id: str, text: str) -> None:
        with self._lock:
            previous = self._assistant_buffers.get(task_id, "")
            merged = previous + ("\n" if previous else "") + text
            self.store.update_assistant_message(session_id, task_id, merged)
            self._assistant_buffers[task_id] = merged

    def _task(self, task_id: str) -> Any:
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Unknown task: {task_id}")
        return task

    # -- routes ---------------------------------------------------------

    def attach(self, app: FastAPI) -> None:
        """Register chatbot routes on an existing FastAPI app (e.g. the panel)."""
        self._register_routes(app, bootstrap_auth=True)

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Substrate Chatbot", version="1.0.0")
        self._register_routes(app)
        self._register_index(app, root_path="/")
        return app

    def _register_index(self, app: FastAPI, *, root_path: str) -> None:
        @app.get(root_path, response_class=HTMLResponse)
        def index() -> str:
            html_path = STATIC_DIR / "index.html"
            return html_path.read_text(encoding="utf-8")

    def _register_routes(self, app: FastAPI, *, bootstrap_auth: bool = False) -> None:
        @app.get("/api/chatbot", response_class=HTMLResponse)
        def index() -> str:
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            if bootstrap_auth:
                # The panel's same-origin bootstrap injects the bearer token
                # into fetch so the embedded chat UI can call the state-changing
                # /api/chat, /api/sessions, and /api/cancel endpoints.
                bootstrap = '<script src="/__panel_auth_bootstrap__.js"></script>'
                if bootstrap not in html and "</head>" in html:
                    html = html.replace("</head>", f"{bootstrap}</head>", 1)
            return html

        @app.get("/api/status")
        def status() -> dict[str, Any]:
            return {
                "ok": True,
                "busy": self.agent.busy,
                "agent": self.agent.status(),
                "workspace": str(Path(self.config.workspace).expanduser()),
                "model": self.config.model,
                "agent_name": self.config.agent,
            }

        @app.get("/api/sessions")
        def list_sessions() -> dict[str, Any]:
            return {"sessions": self.store.list_sessions()}

        @app.post("/api/sessions")
        def create_session(request: SessionCreateRequest) -> dict[str, Any]:
            session_id = request.session_id or self.store.new_session()
            return {"session_id": session_id}

        @app.get("/api/sessions/{session_id}")
        def get_session(session_id: str) -> dict[str, Any]:
            messages = self.store.read_session(session_id)
            if not messages and not self.store.session_exists(session_id):
                raise HTTPException(status_code=404, detail="Session not found")
            return {
                "session_id": session_id,
                "messages": [message.to_dict() for message in messages],
            }

        @app.delete("/api/sessions/{session_id}")
        def delete_session(session_id: str) -> dict[str, Any]:
            deleted = self.store.delete_session(session_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"deleted": session_id}

        @app.post("/api/chat")
        def chat(request: ChatRequest) -> dict[str, Any]:
            session_id = request.session_id or self.store.new_session()
            if not self.store.session_exists(session_id):
                raise HTTPException(status_code=404, detail="Session not found")
            task = self.agent.submit(session_id, request.message)
            self.store.append_message(
                session_id,
                ChatMessage(
                    role="user",
                    content=request.message,
                    task_id=task.task_id,
                    ts=_utc_iso(),
                ),
            )
            with self._lock:
                self._tasks[task.task_id] = task
            return {"task_id": task.task_id, "session_id": session_id, "status": task.status}

        @app.post("/api/cancel")
        def cancel() -> dict[str, Any]:
            cancelled = self.agent.cancel()
            return {"cancelled": cancelled}

        @app.get("/api/stream/{task_id}")
        def stream(task_id: str) -> StreamingResponse:
            task = self._task(task_id)
            return StreamingResponse(
                self._event_stream(task),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

    def _event_stream(self, task: Any):
        """Generator that relays a task's event queue to the SSE stream."""
        heartbeat = 0.0
        while True:
            try:
                item = task.events.get(timeout=15.0)
            except Exception:  # noqa: BLE001  (Empty)
                now = time.monotonic()
                if now - heartbeat >= 15.0:
                    heartbeat = now
                    yield ": keepalive\n\n"
                continue
            if item == DONE_MARKER:
                yield "event: done\ndata: {}\n\n"
                break
            if isinstance(item, dict):
                payload = json.dumps(item, ensure_ascii=False)
                event_type = item.get("type") or "event"
                yield f"event: {event_type}\ndata: {payload}\n\n"
            else:
                yield f"data: {item!s}\n\n"


def _utc_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def create_app(
    config: ChatbotConfig | None = None,
    store: ChatStore | None = None,
    agent: KiloAgent | None = None,
) -> FastAPI:
    return ChatbotApp(config=config, store=store, agent=agent).app
