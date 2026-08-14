"""Prometheus metrics for Substrate blockchain monitoring.

Uses prometheus-client for standards-compliant metrics exposition.
All metrics follow Prometheus naming conventions and best practices.
"""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)


class DashboardMetrics:
    """Centralized metrics registry for Substrate dashboard.

    Exposes metrics in Prometheus format for scraping by Prometheus server
    and visualization in Grafana.
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize metrics with optional custom registry.

        Args:
            registry: Custom Prometheus registry. If None, uses default.
        """
        self.registry = registry or CollectorRegistry()

        # Node Health Metrics
        self.node_peer_count = Gauge(
            "substrate_node_peer_count",
            "Number of connected peers",
            ["node_id", "network"],
            registry=self.registry,
        )

        self.node_sync_status = Gauge(
            "substrate_node_sync_status",
            "Node synchronization status (0=syncing, 1=synced)",
            ["node_id", "network"],
            registry=self.registry,
        )

        self.node_latency_seconds = Histogram(
            "substrate_node_latency_seconds",
            "RPC request latency in seconds",
            ["node_id", "method"],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self.registry,
        )

        self.node_error_total = Counter(
            "substrate_node_error_total",
            "Total number of node errors",
            ["node_id", "error_type"],
            registry=self.registry,
        )

        self.node_uptime_seconds = Gauge(
            "substrate_node_uptime_seconds",
            "Node uptime in seconds",
            ["node_id"],
            registry=self.registry,
        )

        # Chain Metrics
        self.chain_block_height = Gauge(
            "substrate_chain_block_height",
            "Current block height",
            ["network"],
            registry=self.registry,
        )

        self.chain_finalized_height = Gauge(
            "substrate_chain_finalized_height",
            "Current finalized block height",
            ["network"],
            registry=self.registry,
        )

        self.chain_blocks_produced_total = Counter(
            "substrate_chain_blocks_produced_total",
            "Total number of blocks produced",
            ["network", "validator"],
            registry=self.registry,
        )

        self.chain_transaction_count = Counter(
            "substrate_chain_transaction_count",
            "Total number of transactions",
            ["network"],
            registry=self.registry,
        )

        self.chain_transaction_throughput = Gauge(
            "substrate_chain_transaction_throughput",
            "Transactions per second (rolling average)",
            ["network"],
            registry=self.registry,
        )

        self.chain_gas_used = Gauge(
            "substrate_chain_gas_used",
            "Gas used in latest block",
            ["network"],
            registry=self.registry,
        )

        self.chain_gas_limit = Gauge(
            "substrate_chain_gas_limit",
            "Gas limit per block",
            ["network"],
            registry=self.registry,
        )

        self.chain_block_production_time = Histogram(
            "substrate_chain_block_production_time_seconds",
            "Time between block productions",
            ["network"],
            buckets=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 30.0, 60.0),
            registry=self.registry,
        )

        self.chain_finality_lag = Gauge(
            "substrate_chain_finality_lag",
            "Number of blocks between head and finalized",
            ["network"],
            registry=self.registry,
        )

        # Deployment Metrics
        self.deployment_node_version = Info(
            "substrate_deployment_node_version",
            "Node version information",
            ["node_id", "environment"],
            registry=self.registry,
        )

        self.deployment_upgrade_total = Counter(
            "substrate_deployment_upgrade_total",
            "Total number of node upgrades",
            ["node_id", "environment", "status"],
            registry=self.registry,
        )

        self.deployment_environment_parity = Gauge(
            "substrate_deployment_environment_parity",
            "Environment parity score (0-100)",
            ["environment"],
            registry=self.registry,
        )

        # Dashboard Service Metrics
        self.dashboard_scrape_duration = Histogram(
            "substrate_dashboard_scrape_duration_seconds",
            "Time spent collecting metrics",
            ["collector"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
            registry=self.registry,
        )

        self.dashboard_scrape_errors_total = Counter(
            "substrate_dashboard_scrape_errors_total",
            "Total number of metric collection errors",
            ["collector"],
            registry=self.registry,
        )

    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics in text format.

        Returns:
            Prometheus metrics in text exposition format.
        """
        return generate_latest(self.registry)


# Global metrics instance
_metrics_instance: DashboardMetrics | None = None


def get_metrics_registry() -> DashboardMetrics:
    """Get or create the global metrics registry.

    Returns:
        Global DashboardMetrics instance.
    """
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = DashboardMetrics()
    return _metrics_instance


def update_node_health(
    node_id: str,
    network: str,
    peer_count: int,
    is_synced: bool,
    uptime_seconds: float,
) -> None:
    """Update node health metrics.

    Args:
        node_id: Unique node identifier.
        network: Network name (e.g., 'polkadot', 'kusama').
        peer_count: Number of connected peers.
        is_synced: Whether node is fully synced.
        uptime_seconds: Node uptime in seconds.
    """
    metrics = get_metrics_registry()
    metrics.node_peer_count.labels(node_id=node_id, network=network).set(peer_count)
    metrics.node_sync_status.labels(node_id=node_id, network=network).set(
        1 if is_synced else 0
    )
    metrics.node_uptime_seconds.labels(node_id=node_id).set(uptime_seconds)


def update_chain_metrics(
    network: str,
    block_height: int,
    finalized_height: int,
    transaction_count: int,
    gas_used: int,
    gas_limit: int,
) -> None:
    """Update chain-level metrics.

    Args:
        network: Network name.
        block_height: Current block height.
        finalized_height: Current finalized block height.
        transaction_count: Number of transactions in latest block.
        gas_used: Gas used in latest block.
        gas_limit: Gas limit per block.
    """
    metrics = get_metrics_registry()
    metrics.chain_block_height.labels(network=network).set(block_height)
    metrics.chain_finalized_height.labels(network=network).set(finalized_height)
    metrics.chain_transaction_count.labels(network=network).inc(transaction_count)
    metrics.chain_gas_used.labels(network=network).set(gas_used)
    metrics.chain_gas_limit.labels(network=network).set(gas_limit)
    metrics.chain_finality_lag.labels(network=network).set(block_height - finalized_height)


def record_node_error(node_id: str, error_type: str) -> None:
    """Record a node error.

    Args:
        node_id: Unique node identifier.
        error_type: Type of error (e.g., 'rpc_timeout', 'connection_failed').
    """
    metrics = get_metrics_registry()
    metrics.node_error_total.labels(node_id=node_id, error_type=error_type).inc()


def record_block_production(network: str, validator: str) -> None:
    """Record a block production event.

    Args:
        network: Network name.
        validator: Validator address or ID.
    """
    metrics = get_metrics_registry()
    metrics.chain_blocks_produced_total.labels(network=network, validator=validator).inc()


def update_deployment_info(
    node_id: str,
    environment: str,
    version: str,
    parity_score: float,
) -> None:
    """Update deployment information.

    Args:
        node_id: Unique node identifier.
        environment: Environment name (e.g., 'production', 'staging').
        version: Node version string.
        parity_score: Environment parity score (0-100).
    """
    metrics = get_metrics_registry()
    metrics.deployment_node_version.labels(node_id=node_id, environment=environment).info(
        {"version": version}
    )
    metrics.deployment_environment_parity.labels(environment=environment).set(parity_score)
