# Substrate Deploy System - Quick Start Guide

This guide will help you get the Substrate Deploy System up and running in under 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.12+ (for agent installation)
- At least 512MB RAM and 1GB disk space

## Step 1: Start the Control Panel

From the project root directory:

```bash
./scripts/launch.sh start
```

You should see output like:
```
[INFO] Starting Substrate Deploy Control Panel...
[INFO] Control Panel started successfully!
[INFO] Access the dashboard at: http://localhost:8080
```

Open your browser and navigate to http://localhost:8080

## Step 2: Register Your First Agent

```bash
./scripts/launch.sh register-agent my-first-agent
```

Save the output:
```
Agent ID: abc123-def456-ghi789
API Key: xyz789-uvw456-rst123
```

## Step 3: Install Agent on Target Machine

On the target machine where you want to deploy applications:

```bash
# Clone or copy the agent directory
scp -r deploy-system/agent user@target-machine:/opt/

# SSH into the target machine
ssh user@target-machine

# Install dependencies
cd /opt/agent
pip install -r requirements.txt

# Start the agent
python agent.py --control-panel-url http://CONTROL_PANEL_IP:8080
```

The agent will automatically:
- Register itself with the control panel
- Start sending heartbeats every 30 seconds
- Be ready to receive deployments

## Step 4: Verify Agent is Online

Go back to the control panel dashboard (http://localhost:8080) and refresh the page.

You should see your agent listed with status "online" (green dot).

## Step 5: Deploy Your First Application

Prepare your application files:
1. Create a tarball of your application: `tar -czf app.tar.gz your-app/`
2. Host it on an HTTP server (e.g., AWS S3, GitHub releases, or any web server)

Deploy via the dashboard:
1. Click "Deploy" button next to your agent
2. Enter version: `1.0.0`
3. Enter files URL: `https://your-server.com/app.tar.gz`
4. Click "Deploy"

Or via CLI:
```bash
./scripts/launch.sh deploy <agent-id> 1.0.0 https://your-server.com/app.tar.gz
```

## Step 6: Monitor Deployment

The dashboard will show:
- Deployment status (pending → deploying → success/failed)
- Deployment logs
- Agent status updates

## Common Commands

```bash
# Start control panel
./scripts/launch.sh start

# Stop control panel
./scripts/launch.sh stop

# View logs
./scripts/launch.sh logs

# Check status
./scripts/launch.sh status

# Register new agent
./scripts/launch.sh register-agent <name>

# Deploy to agent
./scripts/launch.sh deploy <agent-id> <version> <files-url>

# Build Docker image
./scripts/launch.sh build
```

## Next Steps

1. **Register more agents**: Deploy agents on multiple machines
2. **Set up monitoring**: Configure Prometheus to scrape metrics
3. **Enable HTTPS**: Set up a reverse proxy with SSL/TLS
4. **Automate deployments**: Integrate with CI/CD pipelines
5. **Scale horizontally**: Use load balancers for multiple control panels

## Troubleshooting

### Agent shows as "offline"

- Check agent is running: `ps aux | grep agent.py`
- Verify network connectivity: `curl http://CONTROL_PANEL:8080/health`
- Check agent logs: `~/.substrate-agent/logs/agent-*.log`

### Cannot access dashboard

- Verify Docker is running: `docker ps`
- Check port 8080 is not in use: `netstat -tulpn | grep 8080`
- Try accessing via IP instead of localhost

### Deployment fails

- Verify files URL is accessible from agent machine
- Check tarball format is correct
- Review deployment logs in dashboard
- Check agent logs for errors

## Production Deployment

For production use:

1. **Set strong SECRET_KEY**:
   ```bash
   export SECRET_KEY=$(openssl rand -hex 32)
   ```

2. **Enable HTTPS**:
   - Use nginx/caddy as reverse proxy
   - Configure SSL certificates
   - Update agent URLs to use HTTPS

3. **Persistent storage**:
   - Mount database volume: `-v /path/to/data:/app/data`
   - Regular backups

4. **Monitoring**:
   - Set up Prometheus + Grafana
   - Configure alerts for offline agents
   - Monitor resource usage

5. **Security**:
   - Use private network for agent communication
   - Enable firewall rules
   - Regular security updates

## Getting Help

- Full documentation: `docs/`
- API documentation: http://localhost:8080/docs
- GitHub Issues: Report bugs and request features
- GitHub Discussions: Ask questions and share ideas
