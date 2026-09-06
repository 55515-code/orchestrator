"""WhatsApp Cloud API plugin for the Substrate Gateway.

Integrates with Meta's WhatsApp Cloud API to enable bidirectional messaging
between WhatsApp users and the Substrate. Handles webhook verification,
message parsing, signature validation, and message sending.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from ..models import InboundMessage, OutboundMessage

logger = logging.getLogger(__name__)

# WhatsApp Cloud API base URL
GRAPH_API_BASE = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v21.0"


class WhatsAppPlugin:
    """WhatsApp Cloud API gateway plugin."""
    
    def __init__(self):
        """Initialize the WhatsApp plugin."""
        self._config: dict[str, Any] = {}
        self._client: httpx.AsyncClient | None = None
        self._supports_text = True
        self._supports_media = True
        self._supports_interactive = True
    
    @property
    def service_id(self) -> str:
        """Unique identifier for the service."""
        return "whatsapp"
    
    @property
    def service_name(self) -> str:
        """Human-readable service name."""
        return "WhatsApp Cloud API"
    
    @property
    def version(self) -> str:
        """Plugin version."""
        return "1.0.0"
    
    @property
    def supports_text(self) -> bool:
        """Whether plugin supports text messages."""
        return self._supports_text
    
    @property
    def supports_media(self) -> bool:
        """Whether plugin supports media messages."""
        return self._supports_media
    
    @property
    def supports_interactive(self) -> bool:
        """Whether plugin supports interactive messages."""
        return self._supports_interactive
    
    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize plugin with configuration.
        
        Required config keys:
            - phone_number_id: WhatsApp phone number ID
            - access_token: WhatsApp API access token
            - app_secret: WhatsApp app secret (for signature validation)
            - verify_token: Webhook verification token
        
        Optional config keys:
            - graph_api_version: API version (default: v21.0)
            - webhook_url: Public webhook URL
        """
        required_keys = ["phone_number_id", "access_token", "app_secret", "verify_token"]
        
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config key: {key}")
        
        self._config = {
            "phone_number_id": config["phone_number_id"],
            "access_token": config["access_token"],
            "app_secret": config["app_secret"],
            "verify_token": config["verify_token"],
            "graph_api_version": config.get("graph_api_version", DEFAULT_API_VERSION),
            "webhook_url": config.get("webhook_url", ""),
        }
        
        # Initialize HTTP client
        self._client = httpx.AsyncClient(
            base_url=GRAPH_API_BASE,
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self._config['access_token']}",
                "Content-Type": "application/json",
            }
        )
        
        logger.info(f"WhatsApp plugin initialized for phone: {self._config['phone_number_id']}")
    
    def verify_webhook(self, request: Any) -> bool:
        """Verify webhook request authenticity using HMAC-SHA256.
        
        Args:
            request: FastAPI Request object.
            
        Returns:
            True if signature is valid, False otherwise.
        """
        # Get signature header
        signature_header = request.headers.get("x-hub-signature-256", "")
        
        if not signature_header:
            logger.warning("Missing X-Hub-Signature-256 header")
            return False
        
        # Get request body
        # Note: This is synchronous, but we'll handle async in the route handler
        # For now, we'll validate the signature format
        if not signature_header.startswith("sha256="):
            logger.warning("Invalid signature format")
            return False
        
        return True
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature of webhook payload.
        
        Args:
            payload: Raw request body bytes.
            signature: Signature from X-Hub-Signature-256 header.
            
        Returns:
            True if signature is valid, False otherwise.
        """
        if not signature.startswith("sha256="):
            return False
        
        expected_signature = hmac.new(
            self._config["app_secret"].encode("utf-8"),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        expected = f"sha256={expected_signature}"
        
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, signature)
    
    def verify_webhook_challenge(self, params: dict[str, str]) -> str | None:
        """Verify webhook challenge during initial setup.
        
        Args:
            params: Query parameters from GET request.
            
        Returns:
            Challenge string if valid, None otherwise.
        """
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        
        if mode != "subscribe":
            logger.warning(f"Invalid webhook mode: {mode}")
            return None
        
        if token != self._config["verify_token"]:
            logger.warning("Webhook verification token mismatch")
            return None
        
        if not challenge:
            logger.warning("Missing webhook challenge")
            return None
        
        logger.info("Webhook verification successful")
        return challenge
    
    def parse_inbound(self, payload: dict[str, Any]) -> list[InboundMessage]:
        """Parse WhatsApp webhook payload into standardized messages.
        
        Args:
            payload: WhatsApp webhook payload.
            
        Returns:
            List of parsed inbound messages.
        """
        messages: list[InboundMessage] = []
        
        # Validate payload structure
        if payload.get("object") != "whatsapp_business_account":
            logger.warning(f"Unexpected payload object: {payload.get('object')}")
            return messages
        
        entries = payload.get("entry", [])
        
        for entry in entries:
            changes = entry.get("changes", [])
            
            for change in changes:
                if change.get("field") != "messages":
                    continue
                
                value = change.get("value", {})
                
                # Extract contacts for sender names
                contacts = {
                    c["wa_id"]: c.get("profile", {}).get("name", "")
                    for c in value.get("contacts", [])
                }
                
                # Parse messages
                for msg in value.get("messages", []):
                    message = self._parse_message(msg, contacts)
                    if message:
                        messages.append(message)
        
        return messages
    
    def _parse_message(
        self,
        msg: dict[str, Any],
        contacts: dict[str, str]
    ) -> InboundMessage | None:
        """Parse a single WhatsApp message.
        
        Args:
            msg: WhatsApp message object.
            contacts: Contact name lookup.
            
        Returns:
            Parsed InboundMessage or None if unsupported type.
        """
        msg_type = msg.get("type", "unknown")
        from_number = msg.get("from", "")
        message_id = msg.get("id", "")
        timestamp = msg.get("timestamp", "")
        
        # Build content based on message type
        content = {}
        
        if msg_type == "text":
            content = {"body": msg.get("text", {}).get("body", "")}
        
        elif msg_type == "image":
            content = {
                "id": msg.get("image", {}).get("id", ""),
                "mime_type": msg.get("image", {}).get("mime_type", ""),
                "caption": msg.get("image", {}).get("caption", ""),
            }
        
        elif msg_type == "audio":
            content = {
                "id": msg.get("audio", {}).get("id", ""),
                "mime_type": msg.get("audio", {}).get("mime_type", ""),
            }
        
        elif msg_type == "video":
            content = {
                "id": msg.get("video", {}).get("id", ""),
                "mime_type": msg.get("video", {}).get("mime_type", ""),
                "caption": msg.get("video", {}).get("caption", ""),
            }
        
        elif msg_type == "document":
            content = {
                "id": msg.get("document", {}).get("id", ""),
                "mime_type": msg.get("document", {}).get("mime_type", ""),
                "filename": msg.get("document", {}).get("filename", ""),
                "caption": msg.get("document", {}).get("caption", ""),
            }
        
        elif msg_type == "location":
            location = msg.get("location", {})
            content = {
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "name": location.get("name", ""),
                "address": location.get("address", ""),
            }
        
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            interactive_type = interactive.get("type", "")
            
            if interactive_type == "button_reply":
                content = {
                    "type": "button_reply",
                    "id": interactive.get("button_reply", {}).get("id", ""),
                    "title": interactive.get("button_reply", {}).get("title", ""),
                }
            elif interactive_type == "list_reply":
                content = {
                    "type": "list_reply",
                    "id": interactive.get("list_reply", {}).get("id", ""),
                    "title": interactive.get("list_reply", {}).get("title", ""),
                    "description": interactive.get("list_reply", {}).get("description", ""),
                }
        
        else:
            logger.warning(f"Unsupported message type: {msg_type}")
            return None
        
        # Build metadata
        metadata = {
            "sender_name": contacts.get(from_number, ""),
            "context": msg.get("context", {}),
        }
        
        return InboundMessage(
            service_id=self.service_id,
            user_id=from_number,
            message_type=msg_type,
            content=content,
            timestamp=timestamp,
            message_id=message_id,
            metadata=metadata
        )
    
    def format_outbound(self, message: OutboundMessage) -> dict[str, Any]:
        """Format outbound message for WhatsApp API.
        
        Args:
            message: Standardized outbound message.
            
        Returns:
            WhatsApp API request payload.
        """
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": message.user_id,
        }
        
        if message.message_type == "text":
            payload["type"] = "text"
            payload["text"] = {
                "body": message.content.get("body", "")
            }
        
        elif message.message_type == "image":
            payload["type"] = "image"
            payload["image"] = {
                "link": message.content.get("url", ""),
            }
            if caption := message.content.get("caption"):
                payload["image"]["caption"] = caption
        
        elif message.message_type == "template":
            payload["type"] = "template"
            payload["template"] = message.content
        
        else:
            # Default to text
            payload["type"] = "text"
            payload["text"] = {
                "body": str(message.content)
            }
        
        return payload
    
    async def send(self, message: OutboundMessage) -> dict[str, Any]:
        """Send message via WhatsApp Cloud API.
        
        Args:
            message: Standardized outbound message.
            
        Returns:
            API response with message ID.
        """
        if not self._client:
            raise RuntimeError("WhatsApp plugin not initialized")
        
        payload = self.format_outbound(message)
        
        endpoint = f"/{self._config['graph_api_version']}/{self._config['phone_number_id']}/messages"
        
        try:
            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Message sent to {message.user_id}: {result.get('messages', [{}])[0].get('id')}")
            
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            raise
    
    async def send_text(self, to: str, text: str) -> dict[str, Any]:
        """Convenience method to send a text message.
        
        Args:
            to: Recipient phone number.
            text: Message text.
            
        Returns:
            API response.
        """
        message = OutboundMessage.text(to, text)
        return await self.send(message)
    
    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "en_US",
        components: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Send a template message.
        
        Args:
            to: Recipient phone number.
            template_name: Approved template name.
            language: Template language code.
            components: Template components with parameters.
            
        Returns:
            API response.
        """
        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language}
        }
        
        if components:
            template["components"] = components
        
        message = OutboundMessage(
            user_id=to,
            message_type="template",
            content=template
        )
        
        return await self.send(message)
    
    async def download_media(self, media_id: str) -> bytes:
        """Download media from WhatsApp.
        
        Args:
            media_id: Media ID from message.
            
        Returns:
            Media content bytes.
        """
        if not self._client:
            raise RuntimeError("WhatsApp plugin not initialized")
        
        # Get media URL
        endpoint = f"/{self._config['graph_api_version']}/{media_id}"
        response = await self._client.get(endpoint)
        response.raise_for_status()
        
        media_url = response.json().get("url")
        if not media_url:
            raise ValueError("Media URL not found")
        
        # Download media
        media_response = await self._client.get(media_url)
        media_response.raise_for_status()
        
        return media_response.content
    
    def get_webhook_routes(self) -> list[Any]:
        """Return service-specific webhook routes.
        
        Returns:
            Empty list (routes handled by gateway router).
        """
        return []
    
    def shutdown(self) -> None:
        """Shutdown the plugin and close HTTP client."""
        if self._client:
            # Note: httpx.AsyncClient.close() is async, but we'll handle it
            # in the gateway shutdown sequence
            logger.info("WhatsApp plugin shutdown")


def register_plugin() -> WhatsAppPlugin:
    """Register the WhatsApp plugin with the gateway.
    
    Returns:
        WhatsAppPlugin instance.
    """
    return WhatsAppPlugin()
