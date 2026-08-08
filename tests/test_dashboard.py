"""Tests for the dashboard module."""

from __future__ import annotations

import asyncio

import pytest
from prometheus_client import CollectorRegistry

from substrate.dashboard import DashboardMetrics, create_dashboard_router
from substrate.dashboard.collectors import MultiNodeCollector, SubstrateNodeCollector
from substrate.dashboard.metrics import (
    get_metrics_registry,
    record_node_error,
    update_chain_metrics,
    update_node_health,
)


class TestDashboardMetrics:
    """Test dashboard metrics functionality."""

    def test_metrics_initialization(self):
        """Test that metrics can be initialized."""
        registry = CollectorRegistry()
        metrics = DashboardMetrics(registry=registry)
        assert metrics.registry is registry

    def test_global_metrics_registry(self):
        """Test that global metrics registry is accessible."""
        metrics = get_metrics_registry()
        assert metrics is not None
        assert isinstance(metrics, DashboardMetrics)

    def test_update_node_health(self):
        """Test updating node health metrics."""
        # Should not raise
        update_node_health(
            node_id="test-node",
            network="test-network",
            peer_count=10,
            is_synced=True,
            uptime_seconds=3600.0,
        )

    def test_update_chain_metrics(self):
        """Test updating chain metrics."""
        # Should not raise
        update_chain_metrics(
            network="test-network",
            block_height=1000,
            finalized_height=990,
            transaction_count=50,
            gas_used=1000000,
            gas_limit=2000000,
        )

    def test_record_node_error(self):
        """Test recording node errors."""
        # Should not raise
        record_node_error("test-node", "test_error")

    def test_generate_metrics(self):
        """Test that metrics can be generated."""
        metrics = get_metrics_registry()
        output = metrics.generate_metrics()
        assert isinstance(output, bytes)
        assert len(output) > 0


class TestSubstrateNodeCollector:
    """Test Substrate node collector."""

    def test_collector_initialization(self):
        """Test that collector can be initialized."""
        collector = SubstrateNodeCollector(
            node_id="test-node",
            rpc_url="http://localhost:9933",
            network="test-network",
        )
        assert collector.node_id == "test-node"
        assert collector.rpc_url == "http://localhost:9933"
        assert collector.network == "test-network"

    def test_collector_close(self):
        """Test that collector can be closed."""
        collector = SubstrateNodeCollector(
            node_id="test-node",
            rpc_url="http://localhost:9933",
            network="test-network",
        )
        asyncio.run(collector.close())
        # Should not raise


class TestMultiNodeCollector:
    """Test multi-node collector."""

    def test_multi_collector_initialization(self):
        """Test that multi-collector can be initialized."""
        collector = MultiNodeCollector()
        assert len(collector.collectors) == 0

    def test_add_node(self):
        """Test adding a node to the collector."""
        collector = MultiNodeCollector()
        collector.add_node(
            node_id="test-node",
            rpc_url="http://localhost:9933",
            network="test-network",
        )
        assert "test-node" in collector.collectors
        assert len(collector.collectors) == 1

    def test_remove_node(self):
        """Test removing a node from the collector."""
        collector = MultiNodeCollector()
        collector.add_node(
            node_id="test-node",
            rpc_url="http://localhost:9933",
            network="test-network",
        )
        collector.remove_node("test-node")
        assert "test-node" not in collector.collectors
        assert len(collector.collectors) == 0

    def test_collect_all_empty(self):
        """Test collecting from empty collector."""
        collector = MultiNodeCollector()
        result = asyncio.run(collector.collect_all())
        assert result == {}

    def test_close(self):
        """Test closing the multi-collector."""
        collector = MultiNodeCollector()
        collector.add_node(
            node_id="test-node",
            rpc_url="http://localhost:9933",
            network="test-network",
        )
        asyncio.run(collector.close())
        # Should not raise


class TestDashboardRouter:
    """Test dashboard API router."""

    def test_create_router(self):
        """Test that router can be created."""
        router = create_dashboard_router()
        assert router is not None

    def test_create_router_with_templates(self):
        """Test creating router with template directory."""
        from pathlib import Path

        # Use a non-existent path to test graceful handling
        router = create_dashboard_router(
            templates_dir=Path("/nonexistent"),
            static_dir=Path("/nonexistent"),
        )
        assert router is not None
