# Dashboard and Orchestration System

This document describes the real-time operations dashboard and workflow orchestration system for the Local Agent Substrate.

## Overview

The system consists of two integrated services:

1. **Dashboard Service** - Real-time monitoring and metrics exposition for Substrate blockchain nodes
2. **Pipelines Service** - CI/CD workflow orchestration with Git event triggers

Both services can run independently or integrated into the main Substrate ops panel.

## Architecture

### Dashboard Service

The dashboard service provides real-time visibility into:

- **Node Health**: Peer count, sync status, latency, error rates, uptime
- **Chain Metrics**: Block production, finality, transaction throughput, gas usage
- **Deployment Status**: Node versions, upgrade history, environment parity

#### Components

- **Metrics Collectors** (`substrate/dashboard/metrics.py`): Prometheus-compatible metrics using `prometheus-client`
- **Data Collectors** (`substrate/dashboard/collectors.py`): JSON-RPC collectors for Substrate nodes
- **API Router** (`substrate/dashboard/api.py`): FastAPI endpoints for metrics and status

#### External Dependencies

| Dependency | Purpose | Justification |
|------------|---------|---------------|
| `prometheus-client` | Metrics exposition | Industry-standard Prometheus client for Python. Widely adopted, actively maintained, and integrates seamlessly with Prometheus/Grafana ecosystem. |
| `httpx` | HTTP client for RPC calls | Modern async HTTP client with excellent performance. Already used in the project's test suite. |

### Pipelines Service

The pipelines service manages CI/CD workflows:

- **Pipeline Definitions**: YAML-based configuration for reusable pipelines
- **Execution Engine**: Sequential stage execution with environment isolation
- **Git Triggers**: Webhook handlers for GitHub events (push, PR, tag, release)
- **Status Tracking**: Real-time run status with logs and artifacts

#### Components

- **Models** (`substrate/pipelines/models.py`): Pipeline, Stage, and Run data structures
- **Registry** (`substrate/pipelines/registry.py`): Pipeline definition management
- **Engine** (`substrate/pipelines/engine.py`): Pipeline execution with async support
- **Triggers** (`substrate/pipelines/triggers.py`): Git event webhook handlers
- **API Router** (`substrate/pipelines/api.py`): REST API for pipeline management

### GitHub Sync Service

The GitHub sync service (`substrate/gh_sync/`) automatically synchronizes repository state:

- Fetches branches, tags, and recent commits
- Periodic background synchronization
- Used by both dashboard and pipelines to stay current

## Setup Instructions

### Prerequisites

- Python 3.12+
- `uv` package manager
- Substrate node(s) with JSON-RPC enabled (for dashboard)
- GitHub repository (for sync service)

### Installation

1. **Install dependencies**:

```bash
uv sync --python 3.12
```

The following packages are automatically installed:
- `prometheus-client>=0.20.0` - Prometheus metrics
- `httpx>=0.27.0` - HTTP client (already in project)

2. **Verify installation**:

```bash
uv run python -m compileall substrate/dashboard substrate/pipelines substrate/gh_sync
```

### Running the Services

#### Option 1: Integrated with Ops Panel

The dashboard and pipelines are automatically available when running the main ops panel:

```bash
uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090
```

Access the services at:
- Dashboard metrics: `http://127.0.0.1:8090/dashboard/metrics`
- Dashboard status: `http://127.0.0.1:8090/dashboard/status`
- Pipelines API: `http://127.0.0.1:8090/pipelines/`

#### Option 2: Standalone Services

**Dashboard Service** (port 8091):

```bash
uv run python scripts/serve_dashboard.py --host 127.0.0.1 --port 8091
```

**Pipelines Service** (port 8092):

```bash
uv run python scripts/serve_pipelines.py --host 127.0.0.1 --port 8092
```

#### Option 3: Using Workspace Tasks

```bash
# Start dashboard service
uv run python scripts/substrate_cli.py run-task --repo substrate-core --task dashboard_service

# Start pipelines service
uv run python scripts/substrate_cli.py run-task --repo substrate-core --task pipelines_service
```

## Configuration

### Dashboard Configuration

#### Adding Nodes to Monitor

Use the dashboard API to add Substrate nodes:

```bash
curl -X POST "http://127.0.0.1:8091/dashboard/nodes/node1" \
  -d "rpc_url=http://localhost:9933" \
  -d "network=polkadot"
```

Or configure via environment variables in a `.env` file:

```bash
DASHBOARD_NODES=node1:http://localhost:9933:polkadot,node2:http://localhost:9934:kusama
```

#### Prometheus Integration

The dashboard exposes metrics in Prometheus format at `/dashboard/metrics`.

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'substrate-dashboard'
    static_configs:
      - targets: ['localhost:8091']
    metrics_path: '/dashboard/metrics'
    scrape_interval: 10s
```

A sample Prometheus configuration is provided in `deploy/prometheus/prometheus.yml`.

#### Grafana Integration

Pre-configured Grafana dashboards are available in `deploy/grafana/`:

- **Dashboard JSON**: `deploy/grafana/dashboards/substrate-dashboard.json`
- **Provisioning**: `deploy/grafana/provisioning/`

To use with Grafana:

1. Copy dashboard JSON to Grafana's dashboard directory
2. Configure provisioning files in `/etc/grafana/provisioning/`
3. Restart Grafana

Or import the dashboard manually via Grafana UI using the JSON file.

### Pipelines Configuration

#### Creating Pipeline Definitions

Create YAML files in the `pipelines/` directory:

```yaml
# pipelines/ci.yaml
pipelines:
  - name: ci-pipeline
    description: Continuous Integration pipeline
    stages:
      - name: lint
        commands:
          - uv run ruff check substrate scripts tests
        timeout_seconds: 300
      
      - name: test
        commands:
          - uv run pytest tests -v
        timeout_seconds: 600
        artifacts:
          - "coverage.xml"
          - "test-results.xml"
      
      - name: build
        commands:
          - uv run python -m compileall substrate scripts
        timeout_seconds: 300
    
    triggers:
      - push
      - pull_request
    
    branch_filter:
      - main
      - develop
    
    environment:
      PYTHONUNBUFFERED: "1"
```

#### Pipeline Trigger Configuration

Pipelines support the following triggers:

- `push` - Triggered on git push events
- `pull_request` - Triggered on PR events
- `tag` - Triggered on tag creation
- `release` - Triggered on release events
- `manual` - Manual execution via API
- `schedule` - Scheduled execution (future)

#### GitHub Webhook Setup

1. Go to your GitHub repository settings
2. Navigate to Webhooks → Add webhook
3. Configure:
   - **Payload URL**: `http://your-server:8092/pipelines/webhook/github`
   - **Content type**: `application/json`
   - **Events**: Select "Push", "Pull request", "Branch or tag creation", "Releases"
   - **Active**: Yes

### GitHub Sync Configuration

Configure the GitHub sync service via environment variables:

```bash
GITHUB_OWNER=your-org
GITHUB_REPO=your-repo
GITHUB_TOKEN=ghp_xxxxxxxxxxxx  # Optional, for higher rate limits
SYNC_INTERVAL_SECONDS=300
```

Or initialize programmatically:

```python
from substrate.gh_sync import GitHubSyncService

service = GitHubSyncService(
    owner="your-org",
    repo="your-repo",
    token="your-token",
    sync_interval_seconds=300,
)
await service.start()
```

## API Reference

### Dashboard API

#### GET /dashboard/metrics

Returns Prometheus metrics in text format.

**Response**: `text/plain`

#### GET /dashboard/health

Health check endpoint.

**Response**:
```json
{
  "status": "ok",
  "service": "substrate-dashboard",
  "nodes_configured": 2
}
```

#### GET /dashboard/nodes

List configured nodes.

**Response**:
```json
{
  "nodes": {
    "node1": {
      "rpc_url": "http://localhost:9933",
      "network": "polkadot"
    }
  }
}
```

#### POST /dashboard/nodes/{node_id}

Add a node to monitor.

**Parameters**:
- `rpc_url` (string): JSON-RPC endpoint URL
- `network` (string): Network name
- `timeout` (float, optional): RPC timeout in seconds (default: 10.0)

#### GET /dashboard/collect

Collect metrics from all configured nodes.

**Response**:
```json
{
  "nodes": {
    "node1": {
      "node_id": "node1",
      "network": "polkadot",
      "health": {
        "peers": 25,
        "is_synced": true,
        "uptime_seconds": 86400
      },
      "chain": {
        "block_height": 12345678,
        "finalized_height": 12345670
      }
    }
  },
  "collected_at": 1234567890.123
}
```

### Pipelines API

#### GET /pipelines/

List all registered pipelines.

**Response**:
```json
{
  "pipelines": [
    {
      "name": "ci-pipeline",
      "description": "CI pipeline",
      "stages": [...],
      "triggers": ["push", "pull_request"],
      "enabled": true
    }
  ],
  "count": 1
}
```

#### GET /pipelines/{pipeline_name}

Get a specific pipeline definition.

#### POST /pipelines/{pipeline_name}/trigger

Manually trigger a pipeline.

**Request Body** (optional):
```json
{
  "branch": "main",
  "tag": "v1.0.0",
  "environment": {
    "CUSTOM_VAR": "value"
  }
}
```

**Response**:
```json
{
  "status": "ok",
  "run_id": "abc123-def456",
  "pipeline": "ci-pipeline",
  "status_url": "/pipelines/runs/abc123-def456"
}
```

#### GET /pipelines/runs

List pipeline runs.

**Query Parameters**:
- `pipeline_name` (string, optional): Filter by pipeline
- `status` (string, optional): Filter by status (pending, running, success, failed, cancelled)
- `limit` (int, optional): Maximum runs to return (default: 100, max: 500)

#### GET /pipelines/runs/{run_id}

Get a specific run's details.

**Response**:
```json
{
  "id": "abc123",
  "pipeline_name": "ci-pipeline",
  "status": "success",
  "trigger": "manual",
  "started_at": "2024-01-01T12:00:00",
  "completed_at": "2024-01-01T12:05:00",
  "commit_sha": "abc123def456",
  "branch": "main",
  "artifacts": ["/path/to/artifact.txt"],
  "logs": {
    "build": "/path/to/build.log",
    "test": "/path/to/test.log"
  }
}
```

#### POST /pipelines/runs/{run_id}/cancel

Cancel a running pipeline.

#### POST /pipelines/webhook/github

GitHub webhook endpoint. Automatically triggered by GitHub events.

**Headers**:
- `X-GitHub-Event`: Event type (push, pull_request, create, release)

**Request Body**: GitHub webhook payload

#### GET /pipelines/runs/{run_id}/logs/{stage_name}

Get logs for a specific stage.

## Metrics Reference

### Node Health Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `substrate_node_peer_count` | Gauge | `node_id`, `network` | Number of connected peers |
| `substrate_node_sync_status` | Gauge | `node_id`, `network` | Sync status (0=syncing, 1=synced) |
| `substrate_node_latency_seconds` | Histogram | `node_id`, `method` | RPC request latency |
| `substrate_node_error_total` | Counter | `node_id`, `error_type` | Total node errors |
| `substrate_node_uptime_seconds` | Gauge | `node_id` | Node uptime |

### Chain Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `substrate_chain_block_height` | Gauge | `network` | Current block height |
| `substrate_chain_finalized_height` | Gauge | `network` | Finalized block height |
| `substrate_chain_blocks_produced_total` | Counter | `network`, `validator` | Total blocks produced |
| `substrate_chain_transaction_count` | Counter | `network` | Total transactions |
| `substrate_chain_transaction_throughput` | Gauge | `network` | Transactions per second |
| `substrate_chain_gas_used` | Gauge | `network` | Gas used in latest block |
| `substrate_chain_gas_limit` | Gauge | `network` | Gas limit per block |
| `substrate_chain_block_production_time` | Histogram | `network` | Time between blocks |
| `substrate_chain_finality_lag` | Gauge | `network` | Blocks between head and finalized |

### Deployment Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `substrate_deployment_node_version` | Info | `node_id`, `environment` | Node version info |
| `substrate_deployment_upgrade_total` | Counter | `node_id`, `environment`, `status` | Total upgrades |
| `substrate_deployment_environment_parity` | Gauge | `environment` | Environment parity score (0-100) |

## Testing

Run the test suite:

```bash
uv run --with pytest --with httpx pytest -q tests/test_dashboard.py tests/test_pipelines.py tests/test_gh_sync.py
```

Or run all tests:

```bash
uv run --with pytest --with httpx pytest -q tests
```

## Troubleshooting

### Dashboard Service

**Issue**: No metrics being collected

- Verify nodes are configured: `GET /dashboard/nodes`
- Check node connectivity: `curl http://node-rpc:9933 -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"system_health","params":[],"id":1}'`
- Check dashboard logs for errors

**Issue**: Prometheus not scraping metrics

- Verify metrics endpoint: `curl http://localhost:8091/dashboard/metrics`
- Check Prometheus configuration
- Verify network connectivity between Prometheus and dashboard

### Pipelines Service

**Issue**: Pipeline not triggering

- Check webhook configuration in GitHub
- Verify pipeline is enabled: `GET /pipelines/{name}`
- Check triggers match the event type
- Review branch/tag filters

**Issue**: Pipeline execution fails

- Check stage logs: `GET /pipelines/runs/{id}/logs/{stage}`
- Verify commands are valid in the working directory
- Check environment variables
- Review timeout settings

**Issue**: Artifacts not collected

- Verify artifact patterns in stage configuration
- Check file permissions
- Ensure artifacts directory exists

### GitHub Sync Service

**Issue**: Sync not updating

- Check GitHub API rate limits (unauthenticated: 60/hour, authenticated: 5000/hour)
- Verify `GITHUB_TOKEN` is set for higher limits
- Check network connectivity to `api.github.com`
- Review sync errors: `service.get_state().sync_errors`

## Development

### Adding New Metrics

1. Define metric in `substrate/dashboard/metrics.py`:

```python
self.my_metric = Gauge(
    "substrate_my_metric",
    "Description of metric",
    ["label1", "label2"],
    registry=self.registry,
)
```

2. Create update function:

```python
def update_my_metric(label1: str, label2: str, value: float) -> None:
    metrics = get_metrics_registry()
    metrics.my_metric.labels(label1=label1, label2=label2).set(value)
```

3. Call from collector or API endpoint

### Adding New Pipeline Stages

1. Define stage in pipeline YAML:

```yaml
stages:
  - name: my-stage
    commands:
      - my-command --arg value
    environment:
      MY_VAR: "value"
    artifacts:
      - "output/*"
    timeout_seconds: 600
```

2. Register pipeline in registry

3. Trigger manually or via webhook

## Contributing

Follow the project's contribution guidelines in `CONTRIBUTING.md`.

Key points:
- Maintain backward compatibility for API endpoints
- Add tests for new functionality
- Update documentation for behavior changes
- Follow existing code style (ruff linting)

## License

GPL-3.0-or-later (same as parent project)

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Substrate JSON-RPC API](https://polkadot.js.org/docs/substrate/rpc)
- [GitHub Webhooks](https://docs.github.com/en/webhooks)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
