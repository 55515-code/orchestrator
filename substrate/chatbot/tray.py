"""System tray desktop integration for the substrate chatbot.

Provides a pystray tray icon that hosts the chatbot HTTP server and exposes
menu actions: open the chat UI, start a new chat, view status, view substrate
agent status, open the ops panel, and quit.
"""

from __future__ import annotations

import io
import logging
import threading
import webbrowser
from typing import Any

from .config import ChatbotConfig

logger = logging.getLogger(__name__)


def _make_icon_image() -> "Any":
    """Generate a simple chat-bubble tray icon using Pillow."""
    from PIL import Image, ImageDraw

    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=14, fill=(74, 144, 217, 255))
    draw.rounded_rectangle(
        (12, 16, size - 12, size - 18), radius=8, fill=(255, 255, 255, 255)
    )
    draw.polygon(
        [(size - 22, size - 18), (size - 14, size - 6), (size - 14, size - 18)],
        fill=(255, 255, 255, 255),
    )
    return image


def _run_server(config: ChatbotConfig) -> None:
    import uvicorn

    from .app import create_app

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="warning",
    )


class ChatbotTray:
    def __init__(self, config: ChatbotConfig | None = None) -> None:
        self.config = config or ChatbotConfig.load()
        self.server_thread: threading.Thread | None = None
        self._paused = False

    # -- server lifecycle -----------------------------------------------

    def ensure_server(self) -> bool:
        if self.server_thread is not None and self.server_thread.is_alive():
            return True
        self.server_thread = threading.Thread(
            target=_run_server, args=(self.config,), name="chatbot-server", daemon=True
        )
        self.server_thread.start()
        return True

    def _chat_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}/"

    # -- menu actions ---------------------------------------------------

    def open_chat(self) -> None:
        webbrowser.open(self._chat_url())

    def new_chat(self) -> None:
        import json
        import urllib.request

        try:
            request = urllib.request.Request(
                self._chat_url() + "api/sessions",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                session_id = json.loads(response.read().decode("utf-8"))["session_id"]
            webbrowser.open(f"{self._chat_url()}?session={session_id}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("new chat failed: %s", exc)
            webbrowser.open(self._chat_url())

    def status_text(self) -> str:
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(
                self._chat_url() + "api/status", timeout=10
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            busy = payload.get("busy")
            state = "busy" if busy else "idle"
            return f"Chatbot: {state}"
        except Exception as exc:  # noqa: BLE001
            return f"Chatbot: unreachable ({type(exc).__name__})"

    def show_agent_status(self) -> str:
        import subprocess

        try:
            completed = subprocess.run(
                [
                    "uv",
                    "run",
                    "python",
                    "scripts/substrate_cli.py",
                    "agent-status",
                ],
                cwd=self.config.workspace,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            return completed.stdout[-800:] or "no output"
        except Exception as exc:  # noqa: BLE001
            return f"agent-status failed: {exc}"

    def open_panel(self) -> None:
        webbrowser.open("http://127.0.0.1:8090/")

    def toggle_paused(self, icon: "Any") -> None:
        self._paused = not self._paused
        if self._paused:
            icon.notify("Chatbot paused: new tasks will be queued", "Substrate Chat")
        else:
            icon.notify("Chatbot resumed", "Substrate Chat")
        self._refresh_menu(icon)

    def quit(self, icon: "Any") -> None:
        icon.stop()

    def _refresh_menu(self, icon: "Any") -> None:
        try:
            icon.update_menu()
        except Exception:  # noqa: BLE001
            pass

    # -- tray -----------------------------------------------------------

    def run(self) -> None:
        import pystray
        from pystray import Menu, MenuItem

        self.ensure_server()

        menu = Menu(
            MenuItem("Open Chat", lambda icon, item: self.open_chat(), default=True),
            MenuItem("New Chat", lambda icon, item: self.new_chat()),
            MenuItem("Status", lambda icon, item: self._notify_status(icon)),
            MenuItem("Agent Status", lambda icon, item: self._notify_agent_status(icon)),
            MenuItem("Open Ops Panel", lambda icon, item: self.open_panel()),
            Menu.SEPARATOR,
            MenuItem(
                "Pause / Resume",
                lambda icon, item: self.toggle_paused(icon),
                checked=lambda item: self._paused,
            ),
            Menu.SEPARATOR,
            MenuItem("Quit", lambda icon, item: self.quit(icon)),
        )
        icon = pystray.Icon(
            "substrate-chatbot",
            icon=_make_icon_image(),
            title="Substrate Chat",
            menu=menu,
        )
        icon.run()

    def _notify_status(self, icon: "Any") -> None:
        icon.notify(self.status_text(), "Substrate Chat")

    def _notify_agent_status(self, icon: "Any") -> None:
        text = self.show_agent_status()
        icon.notify(text[:200] or "no agent output", "Substrate Agent Status")
