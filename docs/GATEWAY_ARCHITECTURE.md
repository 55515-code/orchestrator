# Substrate Gateway Architecture Design

## Overview

The Substrate Gateway is a pluggable API layer that enables third-party services to connect to the Local Agent Substrate framework. It provides a modular, extensible architecture where services can be onboarded as plugins, each handling their specific protocol and message format.

**Primary Goals:**
- Provide a unified API interface for external services
- Enable modular plugin architecture for easy service onboarding
- Support real-time bidirectional communication
- Maintain security through authentication and webhook validation
- Integrate seamlessly with existing Substrate orchestration

**First Integration:** WhatsApp Cloud API
- Enable users to chat with Kilo through WhatsApp
- Handle webhook verification and message routing
- Support text, media, and interactive messages
- Maintain conversation context and history

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
│  (WhatsApp, Telegram, Slack, Discord, Custom APIs, etc.)    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Substrate Gateway                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API Router (FastAPI)                     │  │
│  │  /gateway/{service_id}/webhook                        │  │
│  │  /gateway/{service_id}/send                           │  │
│  │  /gateway/{service_id}/status                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Plugin Manager                             │  │
│  │  - Plugin Discovery                                   │  │
│  │  - Lifecycle Management                               │  │
│  │  - Configuration Loading                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Plugin Registry                          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐    │  │
│  │  │ WhatsApp   │  │ Telegram   │  │  Slack     │    │  │
│  │  │  Plugin    │  │  Plugin    │  │  Plugin    │    │  │
│  │  └────────────┘  └────────────┘  └────────────┘    │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Message Router                              │  │
│  │  - Inbound Message Processing                         │  │
│  │  - Outbound Message Delivery                          │  │
│  │  - Conversation Context Management                    │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Substrate Core                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Orchestrator                             │  │
│  │  - Task Execution                                     │  │
│  │  - Kilo Code Integration                              │  │
│  │  - Learning Index                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Database (SQLite)                        │  │
│  │  - Conversation History                             │  │
│  │  - Message Logs                                      │  │
│  │  - Plugin State                                      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. API Router
- **Technology:** FastAPI (existing Substrate web framework)
- **Endpoints:**
  - `POST /gateway/{service_id}/webhook` - Receive inbound messages
  - `GET /gateway/{service_id}/webhook` - Webhook verification (service-specific)
  - `POST /gateway/{service_id}/send` - Send outbound messages
  - `GET /gateway/{service_id}/status` - Service health and status
  - `GET /gateway/services` - List all registered services
- **Authentication:** Bearer token in Authorization header
- **Rate Limiting:** Configurable per service (default: 60 req/min)

#### 2. Plugin Manager
- **Responsibilities:**
  - Discover plugins from `substrate/gateway/plugins/` directory
  - Load plugin configurations from `workspace.yaml`
  - Manage plugin lifecycle (init, start, stop)
  - Provide plugin registry for message routing
- **Plugin Discovery:**
  - Scan `substrate/gateway/plugins/` for Python modules
  - Each plugin must implement `GatewayPlugin` protocol
  - Plugins register themselves via `register_plugin()` function

#### 3. Plugin Registry
- **Storage:** In-memory dictionary with plugin metadata
- **Plugin Metadata:**
  ```python
  {
      "id": "whatsapp",
      "name": "WhatsApp Cloud API",
      "version": "1.0.0",
      "enabled": True,
      "config": {...},
      "instance": <WhatsAppPlugin>,
      "webhook_url": "/gateway/whatsapp/webhook",
      "capabilities": ["text", "media", "interactive"]
  }
  ```

#### 4. Message Router
- **Inbound Flow:**
  1. Receive webhook from external service
  2. Validate webhook signature (service-specific)
  3. Parse message into standardized format
  4. Route to appropriate handler (Kilo Code, task executor, etc.)
  5. Store conversation context in database
  6. Return acknowledgment to service

- **Outbound Flow:**
  1. Receive message from Substrate core
  2. Look up target service and user
  3. Format message for service protocol
  4. Send via service API
  5. Log delivery status
  6. Return confirmation

#### 5. Conversation Context Manager
- **Storage:** SQLite database (`state/gateway-conversations.db`)
- **Schema:**
  ```sql
  CREATE TABLE conversations (
      id TEXT PRIMARY KEY,
      service_id TEXT NOT NULL,
      user_id TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      metadata_json TEXT
  );
  
  CREATE TABLE messages (
      id TEXT PRIMARY KEY,
      conversation_id TEXT NOT NULL,
      direction TEXT NOT NULL,  -- 'inbound' or 'outbound'
      message_type TEXT NOT NULL,
      content_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (conversation_id) REFERENCES conversations(id)
  );
  ```

## Plugin System Design

### Plugin Protocol

All gateway plugins must implement the `GatewayPlugin` protocol:

```python
from typing import Protocol, Any
from dataclasses import dataclass

@dataclass
class InboundMessage:
    service_id: str
    user_id: str
    message_type: str  # 'text', 'image', 'audio', etc.
    content: dict[str, Any]
    timestamp: str
    metadata: dict[str, Any]

@dataclass
class OutboundMessage:
    user_id: str
    message_type: str
    content: dict[str, Any]
    metadata: dict[str, Any]

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
    
    def verify_webhook(self, request: Request) -> bool:
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
    
    def get_webhook_routes(self) -> list[Route]:
        """Return service-specific webhook routes (e.g., verification)."""
        ...
```

### Plugin Lifecycle

1. **Discovery:** Plugin Manager scans `substrate/gateway/plugins/` directory
2. **Loading:** Import plugin module and validate protocol compliance
3. **Initialization:** Call `initialize()` with configuration from `workspace.yaml`
4. **Registration:** Add to plugin registry with metadata
5. **Activation:** Plugin is ready to receive webhooks and send messages
6. **Deactivation:** Remove from registry on shutdown or config change

### Plugin Configuration

Plugins are configured in `workspace.yaml`:

```yaml
gateway:
  enabled: true
  auth_token: "${GATEWAY_AUTH_TOKEN}"
  rate_limit: 60
  
  plugins:
    whatsapp:
      enabled: true
      config:
        phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
        access_token: "${WHATSAPP_ACCESS_TOKEN}"
        app_secret: "${WHATSAPP_APP_SECRET}"
        verify_token: "${WHATSAPP_VERIFY_TOKEN}"
        webhook_url: "https://your-domain.com/gateway/whatsapp/webhook"
```

## WhatsApp Adapter Design

### Overview

The WhatsApp adapter integrates with Meta's WhatsApp Cloud API to enable bidirectional messaging between WhatsApp users and the Substrate.

### Key Components

#### 1. Webhook Handler
- **Verification Endpoint:** `GET /gateway/whatsapp/webhook`
  - Validates `hub.mode`, `hub.verify_token`, `hub.challenge`
  - Returns challenge string on success
  
- **Message Endpoint:** `POST /gateway/whatsapp/webhook`
  - Validates HMAC-SHA256 signature using app secret
  - Parses webhook payload
  - Extracts messages and status updates
  - Routes to message processor

#### 2. Message Parser
- **Inbound Messages:**
  - Text messages: Extract body text
  - Media messages: Download media, store reference
  - Interactive messages: Parse button/list replies
  - Location messages: Extract coordinates
  - Contact messages: Parse contact cards

- **Message Metadata:**
  - Sender phone number
  - Message ID
  - Timestamp
  - Message type
  - Context (replied message ID)

#### 3. Message Sender
- **API Endpoint:** `POST https://graph.facebook.com/v21.0/{phone_number_id}/messages`
- **Message Types:**
  - Text: Simple text messages
  - Media: Images, documents, audio, video
  - Templates: Pre-approved message templates
  - Interactive: Buttons, lists, CTAs

- **Rate Limits:**
  - 80 messages/second (standard tier)
  - 1000 messages/second (high volume tier)
  - Implement exponential backoff on rate limit errors

#### 4. Conversation Management
- **Context Window:** 24-hour customer service window (free messaging)
- **Template Messages:** Required outside 24-hour window
- **Conversation Tracking:**
  - Store conversation ID per user
  - Track last message timestamp
  - Manage message history

### WhatsApp-Specific Features

#### Webhook Signature Validation
```python
import hmac
import hashlib

def verify_signature(app_secret: str, payload: bytes, signature: str) -> bool:
    expected = hmac.new(
        app_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

#### Message Template Management
- Templates must be pre-approved by Meta
- Template categories: Marketing, Utility, Authentication
- Template components: Header, Body, Footer, Buttons
- Dynamic variables: `{{1}}`, `{{2}}`, etc.

#### Media Handling
- Upload media via `/media` endpoint
- Store media ID for reuse
- Download media from webhook payload
- Supported types: image, audio, video, document, sticker

## Authentication Design

### Gateway Authentication

**Method:** Bearer Token
- Token stored in `workspace.yaml` as `gateway.auth_token`
- Can be set via environment variable: `GATEWAY_AUTH_TOKEN`
- Required for all `/gateway/*` endpoints except webhook verification

**Implementation:**
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_gateway_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    token = credentials.credentials
    expected_token = RUNTIME.workspace.gateway.auth_token
    
    if token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid gateway token"
        )
    
    return token
```

### Webhook Authentication

**WhatsApp:** HMAC-SHA256 signature validation
- Meta signs each webhook with app secret
- Validate signature before processing payload
- Reject requests with invalid signatures

**Other Services:** Service-specific validation
- Telegram: Secret token in webhook URL
- Slack: Signing secret verification
- Discord: Ed25519 signature validation

## Message Routing Design

### Inbound Message Flow

```
1. External Service → Gateway Webhook
   ↓
2. Webhook Verification (signature validation)
   ↓
3. Plugin.parse_inbound() → Standardized Messages
   ↓
4. Message Router.process_inbound()
   ↓
5. Store in conversation database
   ↓
6. Route to handler:
   - If contains "/task" → Task Executor
   - If contains "/scan" → Repository Scanner
   - Otherwise → Kilo Code Chat
   ↓
7. Generate response
   ↓
8. Message Router.send_outbound()
   ↓
9. Plugin.format_outbound() → Service-specific format
   ↓
10. Plugin.send() → External Service API
    ↓
11. Log delivery status
```

### Outbound Message Flow

```
1. Substrate Core → Message Router.send_outbound()
   ↓
2. Look up service and user context
   ↓
3. Plugin.format_outbound() → Service-specific format
   ↓
4. Plugin.send() → External Service API
   ↓
5. Log delivery status
   ↓
6. Return confirmation
```

### Handler Routing

Messages are routed based on content patterns:

```python
def route_message(message: InboundMessage) -> str:
    content = message.content.get('text', '').lower()
    
    if content.startswith('/task'):
        return 'task_executor'
    elif content.startswith('/scan'):
        return 'repository_scanner'
    elif content.startswith('/help'):
        return 'help_handler'
    else:
        return 'kilo_code_chat'
```

## Configuration Design

### workspace.yaml Structure

```yaml
gateway:
  enabled: true
  auth_token: "${GATEWAY_AUTH_TOKEN}"
  rate_limit: 60  # requests per minute
  
  plugins:
    whatsapp:
      enabled: true
      config:
        phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
        access_token: "${WHATSAPP_ACCESS_TOKEN}"
        app_secret: "${WHATSAPP_APP_SECRET}"
        verify_token: "${WHATSAPP_VERIFY_TOKEN}"
        webhook_url: "https://your-domain.com/gateway/whatsapp/webhook"
        graph_api_version: "v21.0"
        
    telegram:
      enabled: false
      config:
        bot_token: "${TELEGRAM_BOT_TOKEN}"
        webhook_url: "https://your-domain.com/gateway/telegram/webhook"
```

### Environment Variables

```bash
# Gateway
GATEWAY_AUTH_TOKEN=your-secure-token-here

# WhatsApp
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
WHATSAPP_ACCESS_TOKEN=your-access-token
WHATSAPP_APP_SECRET=your-app-secret
WHATSAPP_VERIFY_TOKEN=your-verify-token
```

## Deployment Considerations

### Public Access Requirements

1. **Domain:** Public domain with HTTPS
   - Required for WhatsApp webhook verification
   - SSL certificate (Let's Encrypt or similar)
   
2. **Reverse Proxy:** Nginx or Caddy
   - Handle SSL termination
   - Rate limiting
   - Request logging
   
3. **Firewall Rules:**
   - Allow inbound HTTPS (443)
   - Allow outbound to Meta APIs (graph.facebook.com)

### Scaling Considerations

1. **Horizontal Scaling:**
   - Gateway is stateless (state in SQLite)
   - Can run multiple instances behind load balancer
   - Use Redis for conversation state if needed

2. **Vertical Scaling:**
   - Increase worker threads for concurrent webhook handling
   - Optimize SQLite with WAL mode (already configured)

3. **Rate Limiting:**
   - Implement per-service rate limits
   - Use token bucket algorithm
   - Return 429 Too Many Requests when exceeded

### Monitoring

1. **Metrics:**
   - Webhook request count
   - Message send/receive count
   - Error rate per service
   - Response latency

2. **Logging:**
   - Structured JSON logs
   - Include service_id, user_id, message_id
   - Log webhook payloads (redacted for security)

3. **Alerts:**
   - Webhook validation failures
   - Message send failures
   - Rate limit exceeded
   - Plugin initialization errors

## Security Considerations

### Webhook Security

1. **Signature Validation:**
   - Always validate webhook signatures
   - Use constant-time comparison (hmac.compare_digest)
   - Reject requests with missing/invalid signatures

2. **Payload Validation:**
   - Validate payload structure before processing
   - Sanitize user input
   - Limit payload size (default: 1MB)

### Token Security

1. **Storage:**
   - Store tokens in environment variables
   - Never commit tokens to version control
   - Use secrets management (e.g., HashiCorp Vault)

2. **Rotation:**
   - Support token rotation without downtime
   - Accept both old and new tokens during rotation
   - Log token usage for audit

### Rate Limiting

1. **Per-Service Limits:**
   - Prevent abuse from single service
   - Configurable per service
   - Return 429 with Retry-After header

2. **Global Limits:**
   - Protect gateway from overload
   - Prioritize critical services
   - Implement backpressure

## Testing Strategy

### Unit Tests

1. **Plugin Tests:**
   - Test plugin initialization
   - Test message parsing
   - Test message formatting
   - Test webhook verification

2. **Router Tests:**
   - Test message routing logic
   - Test handler selection
   - Test error handling

3. **Authentication Tests:**
   - Test token validation
   - Test webhook signature validation
   - Test unauthorized access

### Integration Tests

1. **End-to-End Flow:**
   - Send test message via webhook
   - Verify message processing
   - Verify response delivery

2. **Service Integration:**
   - Test WhatsApp webhook verification
   - Test WhatsApp message sending
   - Test error scenarios

### Load Tests

1. **Webhook Throughput:**
   - Simulate concurrent webhook requests
   - Measure response latency
   - Identify bottlenecks

2. **Message Sending:**
   - Simulate high-volume message sending
   - Test rate limiting
   - Verify delivery status tracking

## Future Enhancements

### Phase 2: Additional Services

1. **Telegram Integration:**
   - Bot API integration
   - Inline keyboards
   - Media handling

2. **Slack Integration:**
   - Slack App integration
   - Slash commands
   - Interactive messages

3. **Discord Integration:**
   - Discord Bot integration
   - Slash commands
   - Embed messages

### Phase 3: Advanced Features

1. **Conversation Analytics:**
   - Message volume tracking
   - Response time metrics
   - User engagement stats

2. **Multi-Tenant Support:**
   - Multiple Substrate instances
   - Per-tenant configuration
   - Resource isolation

3. **Plugin Marketplace:**
   - Community-contributed plugins
   - Plugin versioning
   - Dependency management

4. **Advanced Routing:**
   - Content-based routing rules
   - Conditional handlers
   - Plugin chaining

## Conclusion

The Substrate Gateway provides a robust, extensible foundation for integrating external services with the Local Agent Substrate. The plugin architecture enables easy onboarding of new services, while the standardized message format ensures consistent handling across all integrations.

The WhatsApp adapter serves as the reference implementation, demonstrating best practices for webhook handling, message routing, and conversation management. Future phases will expand support to additional services and advanced features.

**Next Steps:**
1. Implement gateway module structure
2. Implement plugin system
3. Implement WhatsApp adapter
4. Add authentication and webhook handling
5. Update configuration files
6. Add tests
7. Deploy and test end-to-end
