"""Compute-node registry stub for the Android swarm.

Phase A scaffold: keeps an in-memory registry so the gateway and
control-panel can be wired without a real phone. A persistent WebSocket
route will be added in the next pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ComputeNode:
    node_id: str
    display_name: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    last_seen: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "online"


class ComputeNodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, ComputeNode] = {}

    def register(self, node: ComputeNode) -> None:
        node.last_seen = datetime.now(UTC).isoformat()
        self._nodes[node.node_id] = node

    def heartbeat(self, node_id: str, capabilities: dict[str, Any] | None = None) -> None:
        n = self._nodes.get(node_id)
        if n is None:
            return
        n.last_seen = datetime.now(UTC).isoformat()
        if capabilities is not None:
            n.capabilities.update(capabilities)

    def list_nodes(self) -> list[ComputeNode]:
        return list(self._nodes.values())

    def remove(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)


REGISTRY = ComputeNodeRegistry()
