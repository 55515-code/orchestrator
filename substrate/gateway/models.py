"""Gateway data models and plugin protocol definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class InboundMessage:
    """Standardized inbound message from external service."""
    
    service_id: str
    user_id: str
    message_type: str  # 'text', 'image', 'audio', 'video', 'document', 'location', 'interactive'
    content: dict[str, Any]
    timestamp: str
    message_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def text(self) -> str:
        """Extract text content from message."""
        if self.message_type == 'text':
            return self.content.get('body', '')
        return ''
    
    @property
    def is_command(self) -> bool:
        """Check if message is a command (starts with /)."""
        return self.text.startswith('/')
    
    def get_command(self) -> tuple[str, list[str]]:
        """Parse command and arguments from text."""
        if not self.is_command:
            return '', []
        
        parts = self.text.split()
        command = parts[0][1:]  # Remove leading /
        args = parts[1:] if len(parts) > 1 else []
        return command, args


@dataclass
class OutboundMessage:
    """Standardized outbound message to external service."""
    
    user_id: str
    message_type: str
    content: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def text(cls, user_id: str, text: str, **metadata) -> OutboundMessage:
        """Create a text message."""
        return cls(
            user_id=user_id,
            message_type='text',
            content={'body': text},
            metadata=metadata
        )
    
    @classmethod
    def image(cls, user_id: str, url: str, caption: str = '', **metadata) -> OutboundMessage:
        """Create an image message."""
        return cls(
            user_id=user_id,
            message_type='image',
            content={'url': url, 'caption': caption},
            metadata=metadata
        )


@runtime_checkable
class GatewayPlugin(Protocol):
    """Protocol for gateway service plugins."""
    
    @property
    def service_id(self) -> str:
        """Unique identifier for the service."""
        ...
    
    @property
    def service_name(self) -> str:
        """Human-readable service name."""
        ...
    
    @property
    def version(self) -> str:
        """Plugin version."""
        ...
    
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize plugin with configuration."""
        ...
    
    def verify_webhook(self, request: Any) -> bool:
        """Verify webhook request authenticity."""
        ...
    
    def parse_inbound(self, payload: dict[str, Any]) -> list[InboundMessage]:
        """Parse service-specific payload into standardized messages."""
        ...
    
    def format_outbound(self, message: OutboundMessage) -> dict[str, Any]:
        """Format message for service-specific API."""
        ...
    
    async def send(self, message: OutboundMessage) -> dict[str, Any]:
        """Send message via service API."""
        ...
    
    def get_webhook_routes(self) -> list[Any]:
        """Return service-specific webhook routes."""
        ...


@dataclass
class PluginMetadata:
    """Metadata for a registered plugin."""
    
    id: str
    name: str
    version: str
    enabled: bool
    config: dict[str, Any]
    instance: GatewayPlugin | None
    webhook_url: str
    capabilities: list[str]
    initialized: bool = False
    error: str | None = None


@dataclass
class Conversation:
    """Conversation context for a user."""
    
    id: str
    service_id: str
    user_id: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def create(cls, service_id: str, user_id: str) -> Conversation:
        """Create a new conversation."""
        now = datetime.utcnow().isoformat() + 'Z'
        return cls(
            id=f"{service_id}:{user_id}:{now}",
            service_id=service_id,
            user_id=user_id,
            created_at=now,
            updated_at=now
        )
    
    def update_timestamp(self) -> None:
        """Update the conversation timestamp."""
        self.updated_at = datetime.utcnow().isoformat() + 'Z'
