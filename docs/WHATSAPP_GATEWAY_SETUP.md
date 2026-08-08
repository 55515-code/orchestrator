# WhatsApp Gateway Integration Setup Guide

This guide walks you through connecting your WhatsApp to the Substrate Gateway with full Kilo Code agency capabilities.

## Overview

The Substrate Gateway provides a pluggable API layer that enables third-party services to connect to the Local Agent Substrate. The WhatsApp integration allows you to chat with Kilo Code directly through WhatsApp, enabling:

- **Full Kilo Code agency**: Execute tasks, run chains, scan repositories
- **Real-time responses**: Instant feedback on operations
- **Conversation context**: Maintained session history
- **Command interface**: Use `/help`, `/status`, `/services` and custom commands

## Prerequisites

### 1. Meta Business Account

You need a Meta Business account to access the WhatsApp Cloud API:

1. Go to [Facebook Business Manager](https://business.facebook.com/)
2. Create a Business Manager account (or use existing)
3. Verify your business (may require business documents)

### 2. Meta Developer Account

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Register as a developer (if not already)
3. Accept the terms and conditions

### 3. WhatsApp Business Account (WABA)

1. In Meta Business Manager, go to **Business Settings** > **Accounts** > **WhatsApp Business Accounts**
2. Create a new WhatsApp Business Account
3. Choose your business timezone and currency

### 4. Phone Number

You need a phone number for WhatsApp Business:

- **Option A**: Use a new phone number (recommended for testing)
- **Option B**: Migrate an existing number (will disconnect from personal WhatsApp)

**Important**: The number must be able to receive SMS/calls for verification.

## Step-by-Step Setup

### Step 1: Create a Meta App

1. Go to [Meta Developer Dashboard](https://developers.facebook.com/apps/)
2. Click **Create App**
3. Select **Business** as the app type
4. Fill in app details:
   - **App name**: "Substrate Gateway" (or your preferred name)
   - **App contact email**: Your email
5. Link to your Business Manager account
6. Click **Create App**

### Step 2: Add WhatsApp Product

1. In your app dashboard, click **Add Product**
2. Find **WhatsApp** and click **Set Up**
3. Select your WhatsApp Business Account (WABA)
4. Complete the WhatsApp Business Profile:
   - Business name
   - Business description
   - Business website (optional)
   - Business address (optional)

### Step 3: Get a Phone Number

1. In the WhatsApp section of your app, go to **API Setup**
2. Click **Add Phone Number**
3. Choose your phone number:
   - **Option A**: Use Meta's test number (for development)
   - **Option B**: Add your own number (requires verification)
4. For your own number:
   - Enter the phone number
   - Choose verification method (SMS or Voice Call)
   - Enter the verification code
5. Note your **Phone Number ID** (displayed after adding)

### Step 4: Generate Access Token

1. In the WhatsApp section, go to **API Setup**
2. Under **System User**, click **Generate** (or use existing)
3. Select your WABA
4. Grant permissions:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
5. Click **Generate Token**
6. **Copy and save the token** (you won't see it again)

**Token Type**:
- **Temporary Token**: Valid for 24 hours (for testing)
- **Permanent Token**: Requires system user setup (for production)

For production, create a System User:
1. Go to **Business Settings** > **Users** > **System Users**
2. Click **Add**
3. Name: "substrate-gateway"
4. Role: **Admin** or **Employee**
5. Assign assets:
   - Select your app
   - Grant `whatsapp_business_messaging` and `whatsapp_business_management`
6. Generate a permanent token for this system user

### Step 5: Get App Secret

1. Go to your app dashboard
2. Click **Settings** > **Basic**
3. Find **App Secret**
4. Click **Show** and copy the secret
5. **Keep this secret secure** - it's used for webhook signature validation

### Step 6: Configure Webhook

1. In the WhatsApp section, go to **Configuration**
2. Under **Webhook**, click **Edit**
3. Enter your webhook details:
   - **Callback URL**: `https://your-domain.com/gateway/whatsapp/webhook`
   - **Verify token**: Choose a random string (e.g., `substrate-whatsapp-verify-2026`)
4. Click **Verify and Save**

**Note**: Your server must be running and accessible at the callback URL before Meta can verify it.

### Step 7: Subscribe to Webhook Fields

1. After webhook verification, click **Subscribe** next to:
   - `messages` - For receiving incoming messages
   - `message_template_status_update` - For template status updates (optional)

### Step 8: Configure Environment Variables

Create a `.env` file in your project root:

```bash
# Gateway Authentication
GATEWAY_AUTH_TOKEN=your-secure-gateway-token-here

# WhatsApp Configuration
WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id
WHATSAPP_ACCESS_TOKEN=your-access-token
WHATSAPP_APP_SECRET=your-app-secret
WHATSAPP_VERIFY_TOKEN=your-verify-token
WHATSAPP_WEBHOOK_URL=https://your-domain.com/gateway/whatsapp/webhook
```

**Security Notes**:
- Use strong, random tokens
- Never commit `.env` to version control
- Use environment variables in production
- Rotate tokens periodically

### Step 9: Update workspace.yaml

The gateway configuration is already in `workspace.yaml`:

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
        graph_api_version: "v21.0"
        webhook_url: "${WHATSAPP_WEBHOOK_URL}"
```

### Step 10: Start the Server

```bash
# Start the substrate server
uv run python scripts/substrate_cli.py serve --host 0.0.0.0 --port 8090
```

The server will:
1. Load the gateway configuration
2. Initialize the WhatsApp plugin
3. Register webhook routes at `/gateway/whatsapp/webhook`
4. Start listening for incoming messages

### Step 11: Expose Your Server (For Production)

For Meta to send webhooks to your server, it must be publicly accessible with HTTPS.

**Option A: Use ngrok (Development)**

```bash
# Install ngrok
# Download from https://ngrok.com/download

# Start ngrok tunnel
ngrok http 8090

# Update your webhook URL in Meta Developer Dashboard
# Use the ngrok URL: https://abc123.ngrok.io/gateway/whatsapp/webhook
```

**Option B: Use a VPS with SSL (Production)**

1. Deploy to a VPS (DigitalOcean, AWS, etc.)
2. Set up Nginx as reverse proxy
3. Configure SSL with Let's Encrypt:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Step 12: Test the Integration

1. Send a message to your WhatsApp Business number
2. You should receive a response from Kilo Code
3. Try commands:
   - `/help` - List available commands
   - `/status` - Check gateway status
   - `/services` - List available services

## Troubleshooting

### Webhook Verification Fails

**Problem**: Meta cannot verify your webhook URL.

**Solutions**:
1. Ensure your server is running and accessible
2. Check that the verify token matches exactly
3. Verify the URL is HTTPS (required by Meta)
4. Check server logs for errors
5. Test the endpoint manually:
   ```bash
   curl "https://your-domain.com/gateway/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=your-token&hub.challenge=test123"
   ```

### Messages Not Received

**Problem**: You send a message but don't receive a response.

**Solutions**:
1. Check server logs for webhook reception
2. Verify webhook signature validation is working
3. Ensure `messages` webhook field is subscribed
4. Check WhatsApp plugin initialization in logs
5. Verify access token is valid (not expired)

### Signature Validation Fails

**Problem**: Webhook requests are rejected with 403.

**Solutions**:
1. Verify `WHATSAPP_APP_SECRET` is correct
2. Check that the signature header is present
3. Ensure the app secret matches your Meta app
4. Test signature validation manually:
   ```python
   import hmac
   import hashlib
   
   app_secret = "your-app-secret"
   payload = b"test-payload"
   signature = "sha256=" + hmac.new(
       app_secret.encode(),
       payload,
       hashlib.sha256
   ).hexdigest()
   ```

### Rate Limiting

**Problem**: Messages are being rate limited.

**Solutions**:
1. Check Meta's rate limits (80 messages/second for standard tier)
2. Implement exponential backoff in your code
3. Request higher tier from Meta if needed
4. Monitor rate limit headers in API responses

### Access Token Expired

**Problem**: API calls fail with authentication errors.

**Solutions**:
1. Generate a new access token
2. For production, use a System User with permanent token
3. Update your `.env` file with the new token
4. Restart the server

## Security Best Practices

### 1. Token Management

- Use environment variables for all secrets
- Never commit tokens to version control
- Rotate tokens periodically (every 90 days)
- Use different tokens for development and production

### 2. Webhook Security

- Always validate webhook signatures
- Use HTTPS for all webhook endpoints
- Implement rate limiting
- Log all webhook requests for auditing

### 3. Access Control

- Use strong gateway authentication tokens
- Implement IP whitelisting if possible
- Monitor for suspicious activity
- Set up alerts for failed authentication attempts

### 4. Data Privacy

- Comply with WhatsApp Business Policy
- Inform users about data collection
- Implement data retention policies
- Provide opt-out mechanisms

## Advanced Configuration

### Custom Command Handlers

You can register custom command handlers in your code:

```python
from substrate.gateway import MessageRouter

# Register a custom handler
async def handle_scan(message, args):
    """Handle /scan command."""
    repo_slug = args[0] if args else "substrate-core"
    # Execute scan logic
    return f"Scanning repository: {repo_slug}"

router.register_handler("scan", handle_scan)
```

### Message Templates

For business-initiated messages (outside 24-hour window), use templates:

1. Create a template in Meta Business Manager
2. Submit for approval (takes 1-2 days)
3. Use the template in your code:

```python
await plugin.send_template(
    to="+1234567890",
    template_name="welcome_message",
    language="en_US",
    components=[
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": "John"}
            ]
        }
    ]
)
```

### Media Handling

Send and receive media messages:

```python
# Send an image
await plugin.send_image(
    to="+1234567890",
    url="https://example.com/image.jpg",
    caption="Check this out!"
)

# Download received media
media_bytes = await plugin.download_media(media_id)
```

## Monitoring and Logging

### Log Levels

Set appropriate log levels for debugging:

```bash
export LOG_LEVEL=DEBUG  # For development
export LOG_LEVEL=INFO   # For production
```

### Metrics

Monitor key metrics:
- Webhook request count
- Message send/receive rate
- Error rate
- Response latency
- Rate limit usage

### Health Checks

Check gateway health:

```bash
curl http://localhost:8090/gateway/services
```

Expected response:
```json
{
  "services": [
    {
      "id": "whatsapp",
      "name": "WhatsApp Cloud API",
      "version": "1.0.0",
      "enabled": true,
      "initialized": true,
      "capabilities": ["text", "media", "interactive"],
      "webhook_url": "/gateway/whatsapp/webhook"
    }
  ]
}
```

## Support and Resources

### Official Documentation

- [WhatsApp Cloud API Documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [WhatsApp Business Policy](https://www.whatsapp.com/legal/business-policy)
- [Meta for Developers](https://developers.facebook.com/docs)

### Community

- [Meta Developer Community](https://developers.facebook.com/community/)
- [Stack Overflow: WhatsApp API](https://stackoverflow.com/questions/tagged/whatsapp-api)

### Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Review server logs for error messages
3. Test endpoints manually with curl
4. Check Meta's API status page
5. Open an issue in the Substrate repository

## Next Steps

Once your WhatsApp integration is working:

1. **Test thoroughly**: Send various message types (text, media, interactive)
2. **Monitor performance**: Track response times and error rates
3. **Gather feedback**: Get user feedback on the experience
4. **Iterate**: Improve command handlers and response formatting
5. **Scale**: Consider load balancing and horizontal scaling for high volume

## Conclusion

You now have a fully functional WhatsApp integration with the Substrate Gateway. Users can chat with Kilo Code directly through WhatsApp, enabling powerful automation and task execution from their mobile devices.

**Key Features**:
- ✅ Full Kilo Code agency
- ✅ Real-time bidirectional messaging
- ✅ Command interface with custom handlers
- ✅ Secure webhook validation
- ✅ Conversation context management
- ✅ Media support (images, documents, etc.)

For questions or issues, refer to the troubleshooting section or open an issue in the repository.
