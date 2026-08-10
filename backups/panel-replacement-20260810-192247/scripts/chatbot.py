#!/usr/bin/env python3
"""Substrate desktop chatbot launcher.

Commands:
  serve   — run the chat HTTP server only (headless).
  tray    — run the server plus a system tray icon (desktop app).
  open    — start the server (if needed) and open the chat UI in the browser.
  status  — print the chatbot server status as JSON.
  new     — create a new chat session and print its id.

Config file: ~/.config/kilo/chatbot.json (see SUBSTRATE_CHATBOT_CONFIG to override).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _config() -> dict:
    from substrate.chatbot.config import ChatbotConfig

    return ChatbotConfig.load()


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from substrate.chatbot.app import create_app
    from substrate.chatbot.config import ChatbotConfig

    config = ChatbotConfig.load()
    env_port = os.environ.get("CHATBOT_PORT")
    if env_port:
        config.port = int(env_port)
    env_host = os.environ.get("CHATBOT_HOST")
    if env_host:
        config.host = env_host
    if args.port:
        config.port = args.port
    if args.host:
        config.host = args.host
    app = create_app(config)
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info" if args.verbose else "warning",
    )
    return 0


def cmd_tray(_args: argparse.Namespace) -> int:
    from substrate.chatbot.config import ChatbotConfig
    from substrate.chatbot.tray import ChatbotTray

    config = ChatbotConfig.load()
    ChatbotTray(config).run()
    return 0


def cmd_open(_args: argparse.Namespace) -> int:
    import time

    from substrate.chatbot.config import ChatbotConfig

    config = ChatbotConfig.load()
    url = f"http://{config.host}:{config.port}/"
    for _attempt in range(30):
        try:
            with urllib.request.urlopen(url, timeout=2):
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    else:
        print(f"chatbot server not reachable at {url} — start it with `chatbot.py serve` or `tray`.", file=sys.stderr)
        return 1
    webbrowser.open(url)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    from substrate.chatbot.config import ChatbotConfig

    config = ChatbotConfig.load()
    url = f"http://{config.host}:{config.port}/api/status"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def cmd_new(_args: argparse.Namespace) -> int:
    from substrate.chatbot.config import ChatbotConfig

    config = ChatbotConfig.load()
    url = f"http://{config.host}:{config.port}/api/sessions"
    try:
        request = urllib.request.Request(
            url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"new session failed: {exc}", file=sys.stderr)
        return 1
    print(payload.get("session_id", ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chatbot", description="Substrate desktop chatbot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Run the chat HTTP server only.")
    serve_parser.add_argument("--host", default=None)
    serve_parser.add_argument("--port", type=int, default=None)
    serve_parser.add_argument("--verbose", action="store_true")

    subparsers.add_parser("tray", help="Run server plus system tray icon (desktop app).")
    subparsers.add_parser("open", help="Open the chat UI in the default browser.")
    subparsers.add_parser("status", help="Print the chatbot server status as JSON.")
    subparsers.add_parser("new", help="Create a new chat session.")

    args = parser.parse_args(argv)
    handlers = {
        "serve": cmd_serve,
        "tray": cmd_tray,
        "open": cmd_open,
        "status": cmd_status,
        "new": cmd_new,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
