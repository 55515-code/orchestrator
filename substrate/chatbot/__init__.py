"""Desktop chatbot — chat interface with autonomous Kilo agency.

A FastAPI service plus a pystray desktop integration that lets the user chat
with the Kilo agent from the desktop panel. Kilo runs in autonomous mode
(``--auto``) so tasks execute without manual prompts, bounded by the user's
existing permission configuration.
"""

from .agent import AgentTask, KiloAgent
from .app import ChatbotApp, create_app
from .config import ChatbotConfig, state_dir, workspace_root
from .store import ChatMessage, ChatStore

__all__ = [
    "AgentTask",
    "ChatMessage",
    "ChatStore",
    "ChatbotApp",
    "ChatbotConfig",
    "KiloAgent",
    "create_app",
    "state_dir",
    "workspace_root",
]
