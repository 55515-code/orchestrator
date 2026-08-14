#!/usr/bin/env python3
"""Test script for the Substrate Gateway WhatsApp integration.

This script verifies that the gateway is properly configured and can
communicate with the WhatsApp Cloud API.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add substrate to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from substrate.gateway import GatewayManager, MessageRouter


async def test_gateway_initialization():
    """Test that the gateway initializes correctly."""
    print("Testing gateway initialization...")
    
    manager = GatewayManager()
    
    # Load configuration from environment
    config = {
        "enabled": True,
        "plugins": {
            "whatsapp": {
                "enabled": True,
                "config": {
                    "phone_number_id": os.getenv("WHATSAPP_PHONE_NUMBER_ID", "test-phone-id"),
                    "access_token": os.getenv("WHATSAPP_ACCESS_TOKEN", "test-token"),
                    "app_secret": os.getenv("WHATSAPP_APP_SECRET", "test-secret"),
                    "verify_token": os.getenv("WHATSAPP_VERIFY_TOKEN", "test-verify"),
                    "webhook_url": os.getenv("WHATSAPP_WEBHOOK_URL", "https://example.com/webhook"),
                }
            }
        }
    }
    
    manager.initialize(config)
    
    # Check that WhatsApp plugin is loaded
    plugins = manager.list_plugins()
    assert len(plugins) == 1, f"Expected 1 plugin, got {len(plugins)}"
    
    whatsapp_plugin = plugins[0]
    assert whatsapp_plugin.id == "whatsapp", f"Expected id 'whatsapp', got {whatsapp_plugin.id}"
    assert whatsapp_plugin.enabled, "WhatsApp plugin should be enabled"
    assert whatsapp_plugin.initialized, "WhatsApp plugin should be initialized"
    
    print("✓ Gateway initialization successful")
    return manager


async def test_message_router(manager):
    """Test the message router."""
    print("\nTesting message router...")
    
    router = MessageRouter(manager)
    
    # Test command handlers
    assert "help" in router._handlers, "help command should be registered"
    assert "status" in router._handlers, "status command should be registered"
    assert "services" in router._handlers, "services command should be registered"
    
    print("✓ Message router initialized successfully")
    return router


async def test_webhook_verification(manager):
    """Test webhook signature verification."""
    print("\nTesting webhook verification...")
    
    plugin = manager.get_plugin("whatsapp")
    
    # Test valid signature
    payload = b'{"test": "data"}'
    import hashlib
    import hmac
    
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "test-secret")
    expected_signature = "sha256=" + hmac.new(
        app_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    is_valid = plugin.verify_webhook_signature(payload, expected_signature)
    assert is_valid, "Valid signature should pass verification"
    
    # Test invalid signature
    is_invalid = plugin.verify_webhook_signature(payload, "sha256=invalid")
    assert not is_invalid, "Invalid signature should fail verification"
    
    print("✓ Webhook verification working correctly")


async def test_message_parsing(manager):
    """Test inbound message parsing."""
    print("\nTesting message parsing...")
    
    plugin = manager.get_plugin("whatsapp")
    
    # Test text message parsing
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messages": [{
                        "from": "1234567890",
                        "id": "wamid.test",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {"body": "Hello, Kilo!"}
                    }],
                    "contacts": [{
                        "wa_id": "1234567890",
                        "profile": {"name": "Test User"}
                    }]
                }
            }]
        }]
    }
    
    messages = plugin.parse_inbound(payload)
    assert len(messages) == 1, f"Expected 1 message, got {len(messages)}"
    
    message = messages[0]
    assert message.service_id == "whatsapp", f"Expected service_id 'whatsapp', got {message.service_id}"
    assert message.user_id == "1234567890", f"Expected user_id '1234567890', got {message.user_id}"
    assert message.message_type == "text", f"Expected message_type 'text', got {message.message_type}"
    assert message.text == "Hello, Kilo!", f"Expected text 'Hello, Kilo!', got {message.text}"
    
    print("✓ Message parsing working correctly")


async def test_command_routing(router):
    """Test command routing."""
    print("\nTesting command routing...")
    
    from substrate.gateway.models import InboundMessage
    
    # Create a test command message
    message = InboundMessage(
        service_id="whatsapp",
        user_id="1234567890",
        message_type="text",
        content={"body": "/help"},
        timestamp="1234567890",
        message_id="wamid.test",
        metadata={}
    )
    
    # Process the command
    response = await router.process_inbound(message)
    
    assert response is not None, "Command should return a response"
    assert "Available commands" in response, "Help response should list commands"
    
    print("✓ Command routing working correctly")


async def test_outbound_message_formatting(manager):
    """Test outbound message formatting."""
    print("\nTesting outbound message formatting...")
    
    plugin = manager.get_plugin("whatsapp")
    
    from substrate.gateway.models import OutboundMessage
    
    # Test text message formatting
    message = OutboundMessage.text("1234567890", "Hello from Kilo!")
    formatted = plugin.format_outbound(message)
    
    assert formatted["messaging_product"] == "whatsapp", "Should use WhatsApp messaging product"
    assert formatted["recipient_type"] == "individual", "Should be individual recipient"
    assert formatted["to"] == "1234567890", "Should have correct recipient"
    assert formatted["type"] == "text", "Should be text message"
    assert formatted["text"]["body"] == "Hello from Kilo!", "Should have correct message body"
    
    print("✓ Outbound message formatting working correctly")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Substrate Gateway WhatsApp Integration Test Suite")
    print("=" * 60)
    
    try:
        # Test 1: Gateway initialization
        manager = await test_gateway_initialization()
        
        # Test 2: Message router
        router = await test_message_router(manager)
        
        # Test 3: Webhook verification
        await test_webhook_verification(manager)
        
        # Test 4: Message parsing
        await test_message_parsing(manager)
        
        # Test 5: Command routing
        await test_command_routing(router)
        
        # Test 6: Outbound message formatting
        await test_outbound_message_formatting(manager)
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Set up your Meta Business Account (see docs/WHATSAPP_GATEWAY_SETUP.md)")
        print("2. Configure environment variables in .env file")
        print("3. Start the server: uv run python scripts/substrate_cli.py serve")
        print("4. Test with a real WhatsApp message")
        
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
