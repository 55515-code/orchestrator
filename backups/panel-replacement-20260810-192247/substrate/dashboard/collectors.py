"""Data collectors for Substrate node and chain metrics.

Collects metrics from Substrate nodes via JSON-RPC and updates
the Prometheus metrics registry.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .metrics import (
    get_metrics_registry,
    record_node_error,
    update_chain_metrics,
    update_node_health,
)


class SubstrateNodeCollector:
    """Collects metrics from a Substrate node via JSON-RPC.

    Connects to a Substrate node's RPC endpoint and collects
    health, chain, and deployment metrics.
    """

    def __init__(
        self,
        node_id: str,
        rpc_url: str,
        network: str,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the collector.

        Args:
            node_id: Unique identifier for this node.
            rpc_url: JSON-RPC endpoint URL.
            network: Network name (e.g., 'polkadot', 'kusama').
            timeout: RPC request timeout in seconds.
        """
        self.node_id = node_id
        self.rpc_url = rpc_url
        self.network = network
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._started_at: float | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _rpc_call(self, method: str, params: list[Any] | None = None) -> Any:
        """Make a JSON-RPC call to the node.

        Args:
            method: RPC method name.
            params: Optional parameters.

        Returns:
            RPC result.

        Raises:
            Exception: If RPC call fails.
        """
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1,
        }

        start_time = time.perf_counter()
        try:
            response = await client.post(self.rpc_url, json=payload)
            response.raise_for_status()
            data = response.json()

            duration = time.perf_counter() - start_time
            metrics = get_metrics_registry()
            metrics.node_latency_seconds.labels(
                node_id=self.node_id, method=method
            ).observe(duration)

            if "error" in data:
                raise Exception(f"RPC error: {data['error']}")

            return data.get("result")
        except Exception as exc:
            record_node_error(self.node_id, type(exc).__name__)
            raise

    async def collect_health(self) -> dict[str, Any]:
        """Collect node health metrics.

        Returns:
            Health metrics dictionary.
        """
        try:
            health = await self._rpc_call("system_health")
            is_synced = not health.get("isSyncing", True)
            peer_count = health.get("peers", 0)

            uptime = 0.0
            if self._started_at is not None:
                uptime = time.time() - self._started_at

            update_node_health(
                node_id=self.node_id,
                network=self.network,
                peer_count=peer_count,
                is_synced=is_synced,
                uptime_seconds=uptime,
            )

            return {
                "peers": peer_count,
                "is_syncing": health.get("isSyncing", True),
                "should_have_peers": health.get("shouldHavePeers", True),
                "is_synced": is_synced,
                "uptime_seconds": uptime,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def collect_chain(self) -> dict[str, Any]:
        """Collect chain metrics.

        Returns:
            Chain metrics dictionary.
        """
        try:
            header = await self._rpc_call("chain_getHeader")
            block_height = int(header["number"], 16)

            # Get finalized head
            finalized_hash = await self._rpc_call("chain_getFinalizedHead")
            finalized_header = await self._rpc_call("chain_getHeader", [finalized_hash])
            finalized_height = int(finalized_header["number"], 16)

            # Get block body for transaction count
            block_hash = await self._rpc_call("chain_getBlockHash", [block_height])
            block = await self._rpc_call("chain_getBlock", [block_hash])
            extrinsics = block.get("block", {}).get("extrinsics", [])
            transaction_count = len(extrinsics)

            # Gas metrics (simplified - actual implementation would parse extrinsics)
            gas_used = 0
            gas_limit = 0

            update_chain_metrics(
                network=self.network,
                block_height=block_height,
                finalized_height=finalized_height,
                transaction_count=transaction_count,
                gas_used=gas_used,
                gas_limit=gas_limit,
            )

            return {
                "block_height": block_height,
                "finalized_height": finalized_height,
                "transaction_count": transaction_count,
                "block_hash": block_hash,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def collect_version(self) -> dict[str, Any]:
        """Collect node version information.

        Returns:
            Version information dictionary.
        """
        try:
            version = await self._rpc_call("system_version")
            name = await self._rpc_call("system_name")
            chain_name = await self._rpc_call("system_chain")

            return {
                "version": version,
                "name": name,
                "chain": chain_name,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def collect_all(self) -> dict[str, Any]:
        """Collect all metrics from the node.

        Returns:
            Combined metrics dictionary.
        """
        if self._started_at is None:
            self._started_at = time.time()

        health, chain, version = await asyncio.gather(
            self.collect_health(),
            self.collect_chain(),
            self.collect_version(),
            return_exceptions=True,
        )

        return {
            "node_id": self.node_id,
            "network": self.network,
            "health": health if not isinstance(health, Exception) else {"error": str(health)},
            "chain": chain if not isinstance(chain, Exception) else {"error": str(chain)},
            "version": version if not isinstance(version, Exception) else {"error": str(version)},
            "collected_at": time.time(),
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class MultiNodeCollector:
    """Collects metrics from multiple Substrate nodes.

    Manages multiple node collectors and aggregates their metrics.
    """

    def __init__(self) -> None:
        """Initialize the multi-node collector."""
        self.collectors: dict[str, SubstrateNodeCollector] = {}

    def add_node(
        self,
        node_id: str,
        rpc_url: str,
        network: str,
        timeout: float = 10.0,
    ) -> None:
        """Add a node to collect metrics from.

        Args:
            node_id: Unique node identifier.
            rpc_url: JSON-RPC endpoint URL.
            network: Network name.
            timeout: RPC timeout in seconds.
        """
        self.collectors[node_id] = SubstrateNodeCollector(
            node_id=node_id,
            rpc_url=rpc_url,
            network=network,
            timeout=timeout,
        )

    def remove_node(self, node_id: str) -> None:
        """Remove a node from collection.

        Args:
            node_id: Node identifier to remove.
        """
        self.collectors.pop(node_id, None)

    async def collect_all(self) -> dict[str, dict[str, Any]]:
        """Collect metrics from all nodes.

        Returns:
            Dictionary mapping node_id to metrics.
        """
        tasks = [collector.collect_all() for collector in self.collectors.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for node_id, result in zip(self.collectors.keys(), results):
            if isinstance(result, Exception):
                output[node_id] = {"error": str(result)}
            else:
                output[node_id] = result

        return output

    async def close(self) -> None:
        """Close all collectors."""
        for collector in self.collectors.values():
            await collector.close()
