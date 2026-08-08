from __future__ import annotations

import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from substrate.chatbot.agent import DONE_MARKER, KiloAgent
from substrate.chatbot.app import ChatbotApp
from substrate.chatbot.config import ChatbotConfig
from substrate.chatbot.store import ChatMessage, ChatStore


def _drain(task) -> list[dict]:
    events: list[dict] = []
    while True:
        try:
            item = task.events.get(timeout=20.0)
        except queue.Empty:
            break
        if item == DONE_MARKER:
            break
        if isinstance(item, dict):
            events.append(item)
    return events


class FakeProcess:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.stdout = iter(lines)
        self.returncode = 0

    def wait(self) -> int:
        return 0

    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None


def _config(tmp: Path) -> ChatbotConfig:
    return ChatbotConfig(
        host="127.0.0.1",
        port=0,
        workspace=str(tmp),
        kilo_binary="kilo",
        agent=None,
        model=None,
        kilo_config=None,
        task_timeout_seconds=30,
    )


class ChatStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "state" / "chatbot"
        self.store = ChatStore(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_session_lifecycle(self) -> None:
        session_id = self.store.new_session()
        self.assertTrue(self.store.session_exists(session_id))
        self.store.append_message(
            session_id, ChatMessage(role="user", content="hello", ts="t1", task_id="task-1")
        )
        self.store.append_message(
            session_id, ChatMessage(role="assistant", content="hi", ts="t2", task_id="task-1")
        )
        messages = self.store.read_session(session_id)
        self.assertEqual(2, len(messages))
        self.assertEqual("user", messages[0].role)
        self.assertEqual("hello", messages[0].content)
        self.assertEqual("task-1", messages[0].task_id)

        sessions = self.store.list_sessions()
        self.assertEqual(1, len(sessions))
        self.assertEqual(session_id, sessions[0]["id"])
        self.assertTrue(sessions[0]["title"].startswith("hello"))

        self.assertTrue(self.store.delete_session(session_id))
        self.assertFalse(self.store.session_exists(session_id))
        self.assertFalse(self.store.delete_session(session_id))

    def test_update_assistant_message_matches_task(self) -> None:
        session_id = self.store.new_session()
        self.store.append_message(
            session_id, ChatMessage(role="user", content="q1", ts="t1", task_id="t1")
        )
        self.store.append_message(
            session_id, ChatMessage(role="assistant", content="a1", ts="t2", task_id="t1")
        )
        self.store.append_message(
            session_id, ChatMessage(role="user", content="q2", ts="t3", task_id="t2")
        )
        self.store.update_assistant_message(session_id, "t2", "a2-part1")
        self.store.update_assistant_message(session_id, "t2", "a2-part1\na2-part2")
        messages = self.store.read_session(session_id)
        self.assertEqual(4, len(messages))
        self.assertEqual("a1", messages[1].content)
        self.assertEqual("a2-part1\na2-part2", messages[3].content)
        self.assertEqual("t2", messages[3].task_id)

    def test_update_assistant_message_appends_when_missing(self) -> None:
        session_id = self.store.new_session()
        self.store.append_message(
            session_id, ChatMessage(role="user", content="q", ts="t1", task_id="t9")
        )
        self.store.update_assistant_message(session_id, "t9", "streamed")
        messages = self.store.read_session(session_id)
        self.assertEqual(2, len(messages))
        self.assertEqual("assistant", messages[-1].role)
        self.assertEqual("streamed", messages[-1].content)

    def test_prune_sessions(self) -> None:
        self.store.new_session()
        self.store.new_session()
        self.store.new_session()
        self.store.new_session()
        removed = self.store.prune_sessions(keep=2)
        self.assertEqual(2, len(removed))
        remaining = self.store.list_sessions()
        self.assertEqual(2, len(remaining))


class AgentParseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.agent = KiloAgent(_config(Path(self._tmp.name)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse_text_event(self) -> None:
        event = self.agent._parse_line(
            '{"type":"text","timestamp":1,"sessionID":"ses_x","part":{"type":"text","text":"hello world"}}'
        )
        assert event is not None
        self.assertEqual("text", event["type"])
        self.assertEqual("hello world", event["text"])

    def test_parse_tool_use(self) -> None:
        event = self.agent._parse_line(
            '{"type":"tool_use","timestamp":1,"sessionID":"ses_x","part":{"type":"tool","tool":"bash","callID":"call-1"}}'
        )
        assert event is not None
        self.assertEqual("tool_call", event["type"])
        self.assertEqual("bash", event["tool"])
        self.assertEqual("call-1", event["call_id"])

    def test_parse_step_finish(self) -> None:
        event = self.agent._parse_line(
            '{"type":"step_finish","timestamp":1,"sessionID":"ses_x","part":{"type":"step-finish","reason":"stop","model":{"providerID":"kilo","modelID":"m"}}}'
        )
        assert event is not None
        self.assertEqual("model", event["type"])
        self.assertEqual("stop", event["reason"])
        self.assertEqual("kilo", event["provider"])
        self.assertEqual("m", event["model"])

    def test_parse_garbage_returns_none(self) -> None:
        self.assertIsNone(self.agent._parse_line("not json at all"))
        self.assertIsNone(self.agent._parse_line(""))
        self.assertIsNone(self.agent._parse_line("[1,2,3]"))

    def test_full_pipeline_with_fake_process(self) -> None:
        lines = [
            '{"type":"step_start","timestamp":1,"sessionID":"ses_abc","part":{"type":"step-start"}}',
            '{"type":"tool_use","timestamp":2,"sessionID":"ses_abc","part":{"type":"tool","tool":"glob","callID":"c1"}}',
            '{"type":"text","timestamp":3,"sessionID":"ses_abc","part":{"type":"text","text":"Found 3 files"}}',
            '{"type":"step_finish","timestamp":4,"sessionID":"ses_abc","part":{"type":"step-finish","reason":"stop","model":{"providerID":"kilo","modelID":"m"}}}',
        ]
        received: list[tuple[str, str, str]] = []

        def on_message(task_id: str, session_id: str, text: str) -> None:
            received.append((task_id, session_id, text))

        agent = KiloAgent(_config(Path(self._tmp.name)), on_message=on_message)
        with patch.object(agent, "_spawn", return_value=FakeProcess(lines)):
            task = agent.submit("chat_test", "count files")
            events = _drain(task)
        types = [event["type"] for event in events]
        self.assertIn("text", types)
        self.assertIn("tool_call", types)
        self.assertIn("model", types)
        self.assertIn("done", types)
        self.assertEqual("done", task.status)
        self.assertEqual(0, task.exit_code)
        self.assertEqual("ses_abc", task.session_id_out)
        self.assertEqual(1, len(received))
        self.assertEqual("chat_test", received[0][1])
        self.assertEqual("Found 3 files", received[0][2])

    def test_fake_process_error_path(self) -> None:
        lines = [
            '{"type":"text","timestamp":1,"sessionID":"ses_err","part":{"type":"text","text":"partial"}}'
        ]
        agent = KiloAgent(_config(Path(self._tmp.name)))
        with patch.object(agent, "_spawn", return_value=FakeProcess(lines)):
            task = agent.submit("chat_test", "trigger")
            _drain(task)
        self.assertEqual("done", task.status)


class ChatbotApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.config = _config(self.root)
        self.store = ChatStore(self.root / "state" / "chatbot")
        self.chatbot = ChatbotApp(config=self.config, store=self.store)
        self.app = self.chatbot.app
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_index_served(self) -> None:
        response = self.client.get("/")
        self.assertEqual(200, response.status_code)
        self.assertIn("Substrate Chat", response.text)

    def test_status_endpoint(self) -> None:
        response = self.client.get("/api/status")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(str(self.root), payload["workspace"])

    def test_session_endpoints(self) -> None:
        created = self.client.post("/api/sessions", json={}).json()
        session_id = created["session_id"]
        listed = self.client.get("/api/sessions").json()
        self.assertTrue(any(s["id"] == session_id for s in listed["sessions"]))
        fetched = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(200, fetched.status_code)
        deleted = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(200, deleted.status_code)
        missing = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(404, missing.status_code)

    def test_chat_requires_session(self) -> None:
        response = self.client.post("/api/chat", json={"message": "hi", "session_id": "nope"})
        self.assertEqual(404, response.status_code)

    def test_chat_streams_events(self) -> None:
        session_id = self.client.post("/api/sessions", json={}).json()["session_id"]
        agent = self.chatbot.agent
        with patch.object(
            agent,
            "_spawn",
            return_value=FakeProcess(
                [
                    '{"type":"text","timestamp":1,"sessionID":"ses_api","part":{"type":"text","text":"streamed reply"}}'
                ]
            ),
        ):
            chat = self.client.post(
                "/api/chat", json={"message": "do it", "session_id": session_id}
            )
            self.assertEqual(200, chat.status_code)
            task_id = chat.json()["task_id"]
            with self.client.stream("GET", f"/api/stream/{task_id}") as stream:
                body = stream.read().decode("utf-8")
            self.assertIn("streamed reply", body)
            self.assertIn("event: done", body)

        messages = self.store.read_session(session_id)
        self.assertEqual(2, len(messages))
        self.assertEqual("user", messages[0].role)
        self.assertEqual("do it", messages[0].content)
        self.assertEqual("assistant", messages[1].role)
        self.assertEqual("streamed reply", messages[1].content)

    def test_stream_unknown_task_404(self) -> None:
        response = self.client.get("/api/stream/nope")
        self.assertEqual(404, response.status_code)


if __name__ == "__main__":
    unittest.main()
