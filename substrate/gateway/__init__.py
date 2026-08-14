"""Substrate Gateway — pluggable API layer for third-party service integration.

Provides a modular architecture where external services (WhatsApp, Telegram,
Slack, etc.) can connect to the Substrate as plugins. Each plugin handles
its own protocol, authentication, and message formatting while the gateway
provides unified routing, authentication, and conversation management.
"""

from __future__ import annotations

from .manager import GatewayManager
from .models import GatewayPlugin, InboundMessage, OutboundMessage
from .router import MessageRouter

__all__ = [
    "GatewayManager",
    "GatewayPlugin",
    "InboundMessage",
    "MessageRouter",
    "OutboundMessage",
]
