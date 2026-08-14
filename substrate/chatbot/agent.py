"""Kilo agent runner — executes autonomous tasks via the Kilo CLI.

Spawns ``kilo run --auto --format json`` and parses the JSON event stream
into normalized events suitable for a chat UI and SSE streaming.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

from .config import ChatbotConfig

DONE_MARKER = "__done__"
CANCEL_MARKER = "__cancel__"


@dataclass(slots=True)
class AgentTask:
    task_id: str
    session_id: str
    message: str
    status: str = "queued"  # queued | running | done | cancelled | error
    exit_code: int | None = None
    session_id_out: str | None = None
    error: str | None = None
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    events: queue.Queue[dict[str, Any] | str] = field(
        default_factory=queue.Queue
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "message": self.message[:200],
            "status": self.status,
            "exit_code": self.exit_code,
            "session_id_out": self.session_id_out,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def _utc_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("type") or "")


class KiloAgent:
    """Runs autonomous Kilo sessions one at a time with a task queue."""

    def __init__(
        self,
        config: ChatbotConfig,
        on_message: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.config = config
        self.on_message = on_message
        self._queue: queue.Queue[AgentTask] = queue.Queue()
        self._current: AgentTask | None = None
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_session: dict[str, str] = {}

    def submit(
        self, session_id: str, message: str, task_id: str | None = None
    ) -> AgentTask:
        task = AgentTask(
            task_id=task_id or uuid.uuid4().hex,
            session_id=session_id,
            message=message,
            created_at=_utc_iso(),
        )
        self._queue.put(task)
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._worker_loop, name="kilo-agent-worker", daemon=True
                )
                self._thread.start()
        return task

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._current and self._current.status == "running")

    def current_task(self) -> dict[str, Any] | None:
        with self._lock:
            return self._current.to_dict() if self._current else None

    def cancel(self) -> bool:
        process = self._process
        if process is None or process.poll() is not None:
            return False
        process.terminate()
        return True

    def status(self) -> dict[str, Any]:
        with self._lock:
            current = self._current.to_dict() if self._current else None
            queued = self._queue.qsize()
        return {
            "busy": self.busy,
            "current_task": current,
            "queued_tasks": queued,
            "worker_alive": bool(self._thread and self._thread.is_alive()),
        }

    # -- worker ---------------------------------------------------------

    def _worker_loop(self) -> None:
        while True:
            task = self._queue.get()
            if task is None:
                break
            self._run_task(task)

    def _run_task(self, task: AgentTask) -> None:
        with self._lock:
            self._current = task
        task.status = "running"
        task.started_at = _utc_iso()
        task.events.put(
            {"type": "status", "text": "starting autonomous Kilo session"}
        )
        process = None
        try:
            process = self._spawn(task)
            self._process = process
            assert process.stdout is not None
            for line in process.stdout:
                if not line or not line.strip():
                    continue
                if self._cancelled(task):
                    break
                raw_event = self._try_parse_json(line.strip())
                if raw_event is not None:
                    session_id = raw_event.get("sessionID")
                    if session_id and task.session_id_out is None:
                        task.session_id_out = str(session_id)
                normalized = self._parse_line(line.strip())
                if normalized is None:
                    continue
                task.events.put(normalized)
                if normalized.get("type") == "text":
                    self._emit_message(task, str(normalized.get("text") or ""))
                if normalized.get("type") == "session" and normalized.get("session_id"):
                    task.session_id_out = str(normalized["session_id"])
            process.wait()
            task.exit_code = process.returncode
        except FileNotFoundError:
            task.error = (
                f"Kilo binary '{self.config.kilo_binary}' not found on PATH. "
                "Install with `npm install -g @kilocode/cli`."
            )
        except subprocess.TimeoutExpired:
            task.error = (
                f"Task timed out after {self.config.task_timeout_seconds} seconds"
            )
            if process is not None:
                process.kill()
        except Exception as exc:  # noqa: BLE001
            task.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._process = None
            if task.error:
                task.status = "error"
                task.events.put(
                    {"type": "error", "error": task.error, "exit_code": task.exit_code}
                )
                self._emit_message(task, f"[error] {task.error}")
            else:
                task.status = "done"
                task.events.put(
                    {
                        "type": "done",
                        "exit_code": task.exit_code,
                        "session_id": task.session_id_out,
                    }
                )
            task.finished_at = _utc_iso()
            task.events.put(DONE_MARKER)
            if task.session_id_out:
                self._last_session[task.session_id] = task.session_id_out
            with self._lock:
                self._current = None

    # -- spawning -------------------------------------------------------

    def _spawn(self, task: AgentTask) -> subprocess.Popen[str]:
        command = [self.config.kilo_binary, "run", "--auto", "--format", "json"]
        if self.config.agent:
            command.extend(["--agent", self.config.agent])
        if self.config.model:
            command.extend(["--model", self.config.model])
        session_id = self._last_session.get(task.session_id)
        if session_id:
            command.extend(["--session", session_id])
        command.extend(["--dir", str(Path(self.config.workspace).expanduser())])
        command.append(task.message)

        env = os.environ.copy()
        env["KILO_NO_TITLE"] = "1"
        if self.config.kilo_config:
            env["KILO_CONFIG"] = str(self.config.kilo_config)

        proxy_base = self._ensure_prefill_proxy()
        if proxy_base:
            # Route the Kilo CLI's upstream API calls through the local
            # prefill-fix proxy so Anthropic-family conversations that end
            # with an assistant message are normalized before they reach
            # the Kilo Gateway / OpenRouter. See substrate/prefill_proxy.py.
            env["KILO_API_URL"] = proxy_base
            env["KILO_OPENROUTER_BASE"] = proxy_base

        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            cwd=str(Path(self.config.workspace).expanduser()),
        )

    def _ensure_prefill_proxy(self) -> str | None:
        """Return the local prefill-fix proxy base URL, starting it if needed.

        Returns None (and logs a warning) when the proxy cannot be started
        or probed, so a proxy outage never blocks chat: the Kilo CLI then
        simply talks to the real upstreams directly.
        """
        if not self.config.prefill_proxy_enabled:
            return None
        base = f"http://127.0.0.1:{self.config.prefill_proxy_port}"
        if _proxy_healthy(base):
            return base
        try:
            from ..prefill_proxy import start_daemon

            start_daemon(
                root=Path(self.config.workspace).expanduser(),
                host="127.0.0.1",
                port=self.config.prefill_proxy_port,
            )
        except Exception as exc:  # noqa: BLE001
            self._log(f"[prefill-proxy] failed to start: {exc}")
            return None
        if _proxy_healthy(base):
            return base
        self._log(
            f"[prefill-proxy] not healthy on {base}; continuing without it"
        )
        return None

    def _cancelled(self, task: AgentTask) -> bool:
        return task.status == "cancelled"

    # -- parsing --------------------------------------------------------

    def _try_parse_json(self, line: str) -> dict[str, Any] | None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        return event if isinstance(event, dict) else None

    def _parse_line(self, line: str) -> dict[str, Any] | None:
        event = self._try_parse_json(line)
        if event is None:
            return None
        event_type = _event_type(event)
        part = event.get("part") or {}
        if not isinstance(part, dict):
            part = {}

        if event_type == "text":
            text = str(part.get("text") or "").strip()
            if not text:
                return None
            return {"type": "text", "text": text}

        if event_type == "tool_use":
            return {
                "type": "tool_call",
                "tool": str(part.get("tool") or "tool"),
                "call_id": str(part.get("callID") or ""),
            }

        if event_type == "step_start":
            return {"type": "step", "subtype": "start"}

        if event_type == "step_finish":
            model = part.get("model") or {}
            return {
                "type": "model",
                "reason": str(part.get("reason") or "stop"),
                "provider": str(model.get("providerID") or ""),
                "model": str(model.get("modelID") or ""),
            }

        if event_type in {"session.idle", "session_idle"}:
            session_id = str(event.get("sessionID") or "")
            return {"type": "session", "session_id": session_id}

        if event_type in {"session.error", "error"}:
            return {
                "type": "error",
                "error": str(part.get("text") or part.get("error") or ""),
            }

        return {
            "type": "event",
            "source_type": event_type,
            "detail": str(part.get("text") or part.get("tool") or "")[:120],
        }

    def _emit_message(self, task: AgentTask, text: str) -> None:
        if self.on_message is not None:
            try:
                self.on_message(task.task_id, task.session_id, text)
            except Exception:  # noqa: BLE001
                pass


def parse_command_display(command: list[str]) -> str:
    """Human-readable rendering of a kilo command for logging/debug."""
    return " ".join(shlex.quote(part) for part in command)
