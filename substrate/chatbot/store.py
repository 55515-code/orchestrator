"""Persistent chat session store for the substrate desktop chatbot."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import state_dir


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    ts: str
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "ts": self.ts,
            "task_id": self.task_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ChatMessage:
        return cls(
            role=str(raw.get("role") or "assistant"),
            content=str(raw.get("content") or ""),
            ts=str(raw.get("ts") or _utc_iso()),
            task_id=str(raw.get("task_id") or ""),
        )


class ChatStore:
    """JSONL-backed conversation history with an in-memory task registry."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or state_dir()
        self.sessions_dir = self.root / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.jsonl"

    def session_exists(self, session_id: str) -> bool:
        return self._session_path(session_id).exists()

    def new_session(self) -> str:
        session_id = f"chat_{uuid.uuid4().hex[:12]}"
        self._session_path(session_id).touch()
        return session_id

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for path in sorted(self.sessions_dir.glob("*.jsonl"), reverse=True):
            messages = self.read_session(path.stem)
            title = ""
            for message in messages:
                if message.role == "user" and message.content.strip():
                    title = message.content.strip().splitlines()[0][:60]
                    break
            sessions.append(
                {
                    "id": path.stem,
                    "title": title or "Untitled chat",
                    "message_count": len(messages),
                    "updated_at": messages[-1].ts if messages else None,
                }
            )
        return sessions

    def read_session(self, session_id: str) -> list[ChatMessage]:
        path = self._session_path(session_id)
        if not path.exists():
            return []
        messages: list[ChatMessage] = []
        with self._lock, path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(raw, dict):
                    messages.append(ChatMessage.from_dict(raw))
        return messages

    def append_message(self, session_id: str, message: ChatMessage) -> None:
        path = self._session_path(session_id)
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")

    def update_assistant_message(
        self, session_id: str, task_id: str, content: str
    ) -> None:
        """Replace the assistant message for a task, appending if not present."""
        messages = self.read_session(session_id)
        updated = False
        for message in reversed(messages):
            if message.role == "assistant" and message.task_id == task_id:
                message.content = content
                message.ts = _utc_iso()
                updated = True
                break
        if not updated:
            messages.append(
                ChatMessage(
                    role="assistant", content=content, task_id=task_id, ts=_utc_iso()
                )
            )
        path = self._session_path(session_id)
        with self._lock, path.open("w", encoding="utf-8") as handle:
            for message in messages:
                handle.write(json.dumps(message.to_dict(), ensure_ascii=False) + "\n")

    def delete_session(self, session_id: str) -> bool:
        path = self._session_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def prune_sessions(self, keep: int = 50) -> list[str]:
        sessions = [path.stem for path in self.sessions_dir.glob("*.jsonl")]
        sessions.sort(
            key=lambda session_id: self._session_path(session_id).stat().st_mtime,
            reverse=True,
        )
        removed: list[str] = []
        for session_id in sessions[keep:]:
            if self.delete_session(session_id):
                removed.append(session_id)
        return removed
