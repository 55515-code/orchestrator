"""Desktop chatbot — chat interface with autonomous Kilo agency.

A FastAPI service plus a pystray desktop integration that lets the user chat
with the Kilo agent from the desktop panel. Kilo runs in autonomous mode
(``--auto``) so tasks execute without manual prompts, bounded by the user's
existing permission configuration.
"""

from .app import ChatbotApp, create_app
from .agent import KiloAgent, AgentTask
from .config import ChatbotConfig, state_dir, workspace_root
from .store import ChatStore, ChatMessage

__all__ = [
    "AgentTask",
    "ChatbotApp",
    "ChatbotConfig",
    "ChatMessage",
    "ChatStore",
    "KiloAgent",
    "create_app",
    "state_dir",
    "workspace_root",
]
