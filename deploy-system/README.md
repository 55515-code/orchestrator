# Substrate Deploy System

A production-grade, containerized deployment system with a centralized control panel and lightweight agents for managing distributed endpoints.

## Features

- **Centralized Control Panel**: Web-based dashboard for monitoring and managing all deployed endpoints
- **Lightweight Agents**: Minimal footprint agents that run on target machines
- **Real-time Monitoring**: Live status updates via WebSocket
- **Automated Deployments**: Streamlined deployment workflow with version tracking
- **Production Ready**: Docker containerization, health checks, and comprehensive testing

## Architecture

```
┌─────────────────────────────────────────┐
│         Control Panel (Docker)          │
│  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │ Frontend │  │ Backend  │  │  DB  │ │
│  │  (React) │  │ (FastAPI)│  │(SQL) │ │
│  └──────────┘  └──────────┘  └──────┘ │
└─────────────────┬───────────────────────┘
                  │ HTTP/WebSocket
        ┌─────────┼─────────┐
        │         │         │
   ┌────▼───┐ ┌──▼────┐ ┌──▼────┐
   │ Agent 1│ │Agent 2│ │Agent N│
   └────────┘ └───────┘ └───────┘
```

## Quick Start

### 1. Start the Control Panel

```bash
./scripts/launch.sh start
```

This will:
- Build the Docker image
- Start the control panel on port 8080
- Initialize the database

Access the dashboard at: http://localhost:8080

### 2. Register an Agent

```bash
./scripts/launch.sh register-agent my-agent
```

This will:
- Register the agent with the control panel
- Return an agent ID and API key

### 3. Install Agent on Target Machine

On each target machine:

```bash
# Install agent
pip install -r agent/requirements.txt

# Start agent (it will auto-register)
python agent/agent.py --control-panel-url http://CONTROL_PANEL_HOST:8080
```

### 4. Deploy to an Agent

```bash
./scripts/launch.sh deploy <agent-id> 1.0.0 https://example.com/app.tar.gz
```

## System Requirements

- Docker and Docker Compose
- Python 3.12+ (for agent)
- 512MB RAM minimum
- 1GB disk space

## Development

### Run Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run unit tests
pytest tests/test_system.py -v

# Run integration tests (requires running control panel)
pytest tests/test_simulation.py -v -m integration
```

### Build Docker Image

```bash
./scripts/launch.sh build
```

### View Logs

```bash
./scripts/launch.sh logs
```

## API Documentation

Once the control panel is running, access the interactive API documentation at:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

## Configuration

### Environment Variables

Control Panel:
- `DATABASE_URL`: Database connection string (default: sqlite:///./data/control_panel.db)
- `SECRET_KEY`: Secret key for JWT tokens (auto-generated if not set)

Agent:
- `CONTROL_PANEL_URL`: Control panel URL
- `HEARTBEAT_INTERVAL`: Heartbeat interval in seconds (default: 30)

### Docker Compose

Edit `docker/docker-compose.yml` to customize:
- Port mappings
- Volume mounts
- Environment variables
- Resource limits

## Monitoring

### Prometheus Metrics

The control panel exposes Prometheus metrics at `/metrics`:

```bash
curl http://localhost:8080/metrics
```

Available metrics:
- `substrate_agents_total`: Total number of registered agents
- `substrate_agents_online`: Number of online agents
- `substrate_deployments_total`: Total number of deployments

### Dashboard

The web dashboard provides:
- Real-time agent status
- Deployment history
- System statistics
- Quick actions (register, deploy, delete)

## Security

- **Authentication**: JWT-based API authentication
- **API Keys**: Unique API keys for each agent
- **TLS**: Enable HTTPS in production (configure reverse proxy)
- **Network**: Use private networks for agent communication

### Production Security Checklist

- [ ] Set strong `SECRET_KEY` environment variable
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Use strong passwords for database
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Backup database regularly

## Troubleshooting

### Agent Cannot Connect to Control Panel

1. Verify control panel is running: `./scripts/launch.sh status`
2. Check network connectivity: `curl http://CONTROL_PANEL:8080/health`
3. Verify firewall allows port 8080
4. Check agent logs in `~/.substrate-agent/logs/`

### Database Issues

1. Check database file permissions
2. Verify disk space: `df -h`
3. Check database logs in container: `docker logs control-panel`
4. Backup and restore if needed

### High Resource Usage

1. Check number of registered agents
2. Review deployment frequency
3. Adjust heartbeat interval
4. Scale horizontally if needed

## Deployment Scenarios

### Single Machine Development

```bash
./scripts/launch.sh start
```

### Multi-Machine Production

1. Deploy control panel on central server
2. Install agents on target machines
3. Configure load balancer if needed
4. Set up monitoring and alerting

### Kubernetes Deployment

See `docs/k8s-deployment.md` for Kubernetes manifests and Helm charts.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- Documentation: `docs/`
- Issues: GitHub Issues
- Discussions: GitHub Discussions

## Roadmap

- [ ] Multi-tenancy support
- [ ] Role-based access control
- [ ] Deployment rollback
- [ ] Agent auto-update
- [ ] Advanced monitoring and alerting
- [ ] Plugin system
- [ ] Mobile app
