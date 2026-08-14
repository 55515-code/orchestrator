"""Gateway message router — handles message routing and conversation management."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .manager import GatewayManager
from .models import Conversation, InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes messages between external services and Substrate handlers."""
    
    def __init__(self, gateway_manager: GatewayManager):
        """Initialize the message router.
        
        Args:
            gateway_manager: Gateway plugin manager instance.
        """
        self.gateway_manager = gateway_manager
        self._conversations: dict[str, Conversation] = {}
        self._handlers: dict[str, Callable] = {}
        
        # Register default handlers
        self._register_default_handlers()
    
    def _register_default_handlers(self) -> None:
        """Register default message handlers."""
        self._handlers["help"] = self._handle_help
        self._handlers["status"] = self._handle_status
        self._handlers["services"] = self._handle_services
    
    def register_handler(self, command: str, handler: Callable) -> None:
        """Register a custom message handler.
        
        Args:
            command: Command name (without leading /).
            handler: Async handler function(message: InboundMessage) -> str.
        """
        self._handlers[command] = handler
        logger.info(f"Registered handler for command: {command}")
    
    async def process_inbound(self, message: InboundMessage) -> str | None:
        """Process an inbound message and route to appropriate handler.
        
        Args:
            message: Inbound message from external service.
            
        Returns:
            Response text or None if no response needed.
        """
        logger.info(f"Processing inbound message from {message.user_id} via {message.service_id}")
        
        # Get or create conversation
        conversation = self._get_or_create_conversation(message.service_id, message.user_id)
        
        # Route message based on content
        if message.is_command:
            response = await self._handle_command(message)
        else:
            response = await self._handle_chat(message, conversation)
        
        # Update conversation
        conversation.update_timestamp()
        
        return response
    
    async def _handle_command(self, message: InboundMessage) -> str:
        """Handle a command message.
        
        Args:
            message: Inbound command message.
            
        Returns:
            Command response text.
        """
        command, args = message.get_command()
        
        logger.info(f"Handling command: {command} with args: {args}")
        
        # Look up handler
        handler = self._handlers.get(command)
        
        if not handler:
            return f"Unknown command: /{command}\n\nType /help for available commands."
        
        try:
            # Call handler
            result = handler(message, args)
            
            # Handle async handlers
            if hasattr(result, "__await__"):
                result = await result
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling command {command}: {e}")
            return f"Error executing command: {e!s}"
    
    async def _handle_chat(self, message: InboundMessage, conversation: Conversation) -> str:
        """Handle a regular chat message.
        
        Args:
            message: Inbound chat message.
            conversation: Conversation context.
            
        Returns:
            Chat response text.
        """
        # For now, return a simple acknowledgment
        # In production, this would route to Kilo Code or other handlers
        
        text = message.text
        
        if not text:
            return "I received your message but couldn't read the text content."
        
        # Simple echo for demonstration
        # In production, this would integrate with Kilo Code
        return f"Received: {text}\n\nNote: Full Kilo Code integration requires additional setup."
    
    async def send_outbound(
        self,
        service_id: str,
        user_id: str,
        text: str,
        **metadata
    ) -> dict[str, Any]:
        """Send an outbound message to an external service.
        
        Args:
            service_id: Target service identifier.
            user_id: Target user identifier.
            text: Message text.
            **metadata: Additional message metadata.
            
        Returns:
            Service API response.
        """
        # Get plugin
        plugin = self.gateway_manager.get_plugin(service_id)
        
        if not plugin:
            raise ValueError(f"Service not found: {service_id}")
        
        # Create outbound message
        message = OutboundMessage.text(user_id, text, **metadata)
        
        # Send via plugin
        result = await plugin.send(message)
        
        logger.info(f"Sent message to {user_id} via {service_id}")
        
        return result
    
    def _get_or_create_conversation(
        self,
        service_id: str,
        user_id: str
    ) -> Conversation:
        """Get or create a conversation context.
        
        Args:
            service_id: Service identifier.
            user_id: User identifier.
            
        Returns:
            Conversation instance.
        """
        key = f"{service_id}:{user_id}"
        
        if key not in self._conversations:
            conversation = Conversation.create(service_id, user_id)
            self._conversations[key] = conversation
            logger.info(f"Created new conversation: {key}")
        
        return self._conversations[key]
    
    def get_conversation(self, service_id: str, user_id: str) -> Conversation | None:
        """Get a conversation by service and user ID.
        
        Args:
            service_id: Service identifier.
            user_id: User identifier.
            
        Returns:
            Conversation instance or None.
        """
        key = f"{service_id}:{user_id}"
        return self._conversations.get(key)
    
    def list_conversations(self) -> list[Conversation]:
        """List all active conversations.
        
        Returns:
            List of conversation instances.
        """
        return list(self._conversations.values())
    
    # Default command handlers
    
    def _handle_help(self, message: InboundMessage, args: list[str]) -> str:
        """Handle /help command."""
        commands = sorted(self._handlers.keys())
        
        help_text = "Available commands:\n\n"
        for cmd in commands:
            help_text += f"/{cmd}\n"
        
        help_text += "\nType / followed by a command name to execute it."
        
        return help_text
    
    def _handle_status(self, message: InboundMessage, args: list[str]) -> str:
        """Handle /status command."""
        plugins = self.gateway_manager.list_plugins()
        
        status_text = "Gateway Status:\n\n"
        status_text += f"Total plugins: {len(plugins)}\n"
        status_text += f"Enabled plugins: {len(self.gateway_manager.get_enabled_plugins())}\n\n"
        
        status_text += "Services:\n"
        for plugin in plugins:
            status = "✓" if plugin.enabled and plugin.initialized else "✗"
            status_text += f"{status} {plugin.name} v{plugin.version}\n"
        
        return status_text
    
    def _handle_services(self, message: InboundMessage, args: list[str]) -> str:
        """Handle /services command."""
        plugins = self.gateway_manager.get_enabled_plugins()
        
        if not plugins:
            return "No services are currently enabled."
        
        services_text = "Available services:\n\n"
        for plugin in plugins:
            services_text += f"• {plugin.name}\n"
            services_text += f"  Capabilities: {', '.join(plugin.capabilities)}\n"
            services_text += f"  Webhook: {plugin.webhook_url}\n\n"
        
        return services_text
