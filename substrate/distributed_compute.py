"""Distributed compute community integration.

Supported communities:
- BOINC (Berkeley Open Infrastructure for Network Computing)
- Mesh-LLM (distributed AI/LLM compute sharing)
- Local cycle donor (contribute our idle CPU/GPU cycles back)

This module bridges external volunteer-compute communities into the
substrate's existing resource scheduler and compute-node registry so:
  - substrate tasks can be routed to community nodes when local/cloud is saturated
  - our spare cycles can be donated back when our utilization is low
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from .compute_nodes import ComputeNode, REGISTRY

logger = logging.getLogger(__name__)

CommunityKind = Literal["boinc", "mesh-llm", "local-donor"]
NodeStatus = Literal["online", "offline", "donating", "receiving"]

BOINC_PROJECTS: dict[str, str] = {
    "rosetta": "https://boinc.bakerlab.org/rosetta/",
    "einstein": "https://einsteinathome.org/",
    "worldcommunitygrid": "https://www.worldcommunitygrid.org/",
    "gpugrid": "https://gpugrid.net/gpugrid/",
    "lhc": "https://lhcathome.cern.ch/lhcathome/",
    "asteroids": "https://asteroidsathome.net/boinc/",
}

MESH_LLM_DEFAULT_URL = os.getenv("MESH_LLM_URL", "http://meshllm.cloud")
MESH_LLM_API_KEY = os.getenv("MESH_LLM_API_KEY", "")


@dataclass
class CommunityNodeConfig:
    kind: CommunityKind
    project_id: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    max_concurrent_tasks: int = 2
    donate_when_idle: bool = True
    idle_threshold_utilization: float = 0.15
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommunityNode:
    node_id: str
    config: CommunityNodeConfig
    status: NodeStatus = "online"
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_heartbeat: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    current_utilization: float = 0.0

    def to_compute_node(self) -> ComputeNode:
        caps = {
            "kind": self.config.kind,
            "max_concurrent": self.config.max_concurrent_tasks,
            "status": self.status,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            **(self.config.capabilities),
        }
        if self.config.project_id:
            caps["project_id"] = self.config.project_id
        return ComputeNode(
            node_id=self.node_id,
            display_name=f"{self.config.kind}:{self.node_id}",
            capabilities=caps,
            last_seen=self.last_heartbeat,
            status="online" if self.status != "offline" else "offline",
        )


class CommunityIntegrationRegistry:
    """Tracks configured external compute community connections."""

    def __init__(self) -> None:
        self._nodes: dict[str, CommunityNode] = {}
        self._contribution_enabled: dict[str, bool] = {}

    def register(self, node: CommunityNode) -> None:
        self._nodes[node.node_id] = node
        REGISTRY.register(node.to_compute_node())
        logger.info("Registered community node %s (%s)", node.node_id, node.config.kind)

    def unregister(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        REGISTRY.remove(node_id)

    def node(self, node_id: str) -> CommunityNode | None:
        return self._nodes.get(node_id)

    def all_nodes(self) -> list[CommunityNode]:
        return list(self._nodes.values())

    def nodes_by_kind(self, kind: CommunityKind) -> list[CommunityNode]:
        return [n for n in self._nodes.values() if n.config.kind == kind]

    def available_for_work(self) -> list[CommunityNode]:
        return [
            n
            for n in self._nodes.values()
            if n.status in {"online", "receiving"}
            and n.current_utilization < 1.0
        ]

    def eligible_for_donation(self, local_utilization: float) -> list[CommunityNode]:
        return [
            n
            for n in self._nodes.values()
            if n.config.kind == "local-donor"
            and n.config.donate_when_idle
            and local_utilization <= n.config.idle_threshold_utilization
        ]

    def set_contribution_enabled(self, node_id: str, enabled: bool) -> None:
        self._contribution_enabled[node_id] = enabled

    def contribution_enabled(self, node_id: str) -> bool:
        return self._contribution_enabled.get(node_id, True)


COMMUNITY_REGISTRY = CommunityIntegrationRegistry()


# ---------------------------------------------------------------------------
# BOINC adapter
# ---------------------------------------------------------------------------

class BOINCAdapter:
    """Minimal BOINC project client integration.

    Requires the BOINC client (`boinccmd`) to be installed and an account
    configured for at least one project.  When full BOINC setup is not
    present, the adapter falls back to recording the configured project
    intent in the compute-node registry without making live calls.
    """

    def __init__(self, project_url: str | None = None) -> None:
        self.project_url = project_url or BOINC_PROJECTS.get("rosetta")
        self._has_client = self._check_client()

    def _check_client(self) -> bool:
        try:
            subprocess.run(
                ["boinccmd", "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            logger.info("BOINC client not available; using registry-only mode.")
            return False

    def register_project_node(
        self, project_key: str, max_tasks: int = 2
    ) -> CommunityNode | None:
        url = BOINC_PROJECTS.get(project_key) or self.project_url
        if not url:
            return None
        node_id = f"boinc-{project_key}"
        config = CommunityNodeConfig(
            kind="boinc",
            project_id=project_key,
            endpoint=url,
            max_concurrent_tasks=max_tasks,
            capabilities={
                "cpu": True,
                "gpu": True,
                "platform": "boinc",
                "project_url": url,
            },
        )
        node = CommunityNode(node_id=node_id, config=config)
        COMMUNITY_REGISTRY.register(node)
        return node

    def heartbeat(self, node_id: str) -> dict[str, Any]:
        node = COMMUNITY_REGISTRY.node(node_id)
        if node is None:
            return {"status": "unknown"}
        if not self._has_client:
            node.last_heartbeat = datetime.now(UTC).isoformat()
            return {"status": "registry-only", "tasks_completed": node.tasks_completed}
        try:
            result = subprocess.run(
                ["boinccmd", "--get_tasks"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
            active = result.stdout.count("active")
            node.current_utilization = min(1.0, active / max(1, node.config.max_concurrent_tasks))
            node.last_heartbeat = datetime.now(UTC).isoformat()
            node.status = "receiving" if active > 0 else "online"
            return {
                "status": node.status,
                "active_tasks": active,
                "utilization": node.current_utilization,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("BOINC heartbeat failed for %s: %s", node_id, exc)
            return {"status": "error", "error": str(exc)}

    def donate_idle_cycles(self, node_id: str, enable: bool) -> dict[str, Any]:
        node = COMMUNITY_REGISTRY.node(node_id)
        if node is None:
            return {"status": "unknown_node"}
        node.config.donate_when_idle = enable
        node.status = "donating" if enable else "online"
        return {
            "status": node.status,
            "donate_when_idle": enable,
            "project": node.config.project_id,
        }


# ---------------------------------------------------------------------------
# Mesh-LLM adapter
# ---------------------------------------------------------------------------

class MeshLLMAdapter:
    """Mesh-LLM distributed AI compute integration.

    Interacts with a running Mesh-LLM node to offer local compute for
    remote inference jobs and to request inference from the network.
    API shape is based on Mesh-LLM's documented endpoints; adjust as
    the upstream API evolves.
    """

    def __init__(self, base_url: str = MESH_LLM_DEFAULT_URL, api_key: str = MESH_LLM_API_KEY) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._reachable = self._probe()

    def _probe(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception as exc:  # noqa: BLE001
            logger.info("Mesh-LLM not reachable at %s: %s", self.base_url, exc)
            return False

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            logger.error("Mesh-LLM HTTP %s: %s", exc.code, body[:500])
            return {"error": f"HTTP {exc.code}", "body": body[:500]}
        except Exception as exc:  # noqa: BLE001
            logger.error("Mesh-LLM request failed: %s", exc)
            return {"error": str(exc)}

    def register_compute_node(
        self, node_id: str, max_concurrent: int = 2
    ) -> CommunityNode:
        config = CommunityNodeConfig(
            kind="mesh-llm",
            endpoint=self.base_url,
            api_key=self.api_key or None,
            max_concurrent_tasks=max_concurrent,
            capabilities={
                "cpu": True,
                "gpu": True,
                "llm_inference": True,
                "platform": "mesh-llm",
            },
        )
        node = CommunityNode(node_id=node_id, config=config)
        COMMUNITY_REGISTRY.register(node)
        if self._reachable:
            self._post("nodes/register", {"node_id": node_id, "max_concurrent": max_concurrent})
        return node

    def heartbeat(self, node_id: str) -> dict[str, Any]:
        node = COMMUNITY_REGISTRY.node(node_id)
        if node is None:
            return {"status": "unknown"}
        node.last_heartbeat = datetime.now(UTC).isoformat()
        if not self._reachable:
            return {"status": "local-only"}
        result = self._post("nodes/heartbeat", {"node_id": node_id})
        if "error" not in result:
            node.status = result.get("status", "online")
            node.current_utilization = float(result.get("utilization", 0.0))
        return result

    def donate_idle_cycles(self, node_id: str, enable: bool) -> dict[str, Any]:
        node = COMMUNITY_REGISTRY.node(node_id)
        if node is None:
            return {"status": "unknown_node"}
        node.config.donate_when_idle = enable
        node.status = "donating" if enable else "online"
        if self._reachable:
            return self._post("nodes/donate", {"node_id": node_id, "enable": enable})
        return {"status": "local-only", "donate_when_idle": enable}

    def request_inference(
        self, node_id: str, prompt: str, model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        if not self._reachable:
            return {"error": "mesh-llm not reachable"}
        payload: dict[str, Any] = {"node_id": node_id, "prompt": prompt}
        if model:
            payload["model"] = model
        payload.update(kwargs)
        return self._post("inference", payload)


# ---------------------------------------------------------------------------
# Local cycle donor
# ---------------------------------------------------------------------------

class LocalCycleDonor:
    """Contribute our own idle CPU/GPU cycles to configured communities.

    This is the substrate-side of the reciprocity loop: when our local
    utilization drops below the configured threshold, we offer compute
    to BOINC or Mesh-LLM; when pressure rises, we pause donation and
    reclaim capacity for local work.
    """

    def __init__(
        self,
        node_id: str = "local-donor",
        idle_threshold: float = 0.15,
        max_donated_workers: int = 2,
    ) -> None:
        self.node_id = node_id
        self.idle_threshold = idle_threshold
        self.max_donated_workers = max_donated_workers
        self._donating = False
        self._donated_workers = 0

        config = CommunityNodeConfig(
            kind="local-donor",
            donate_when_idle=True,
            idle_threshold_utilization=idle_threshold,
            max_concurrent_tasks=max_donated_workers,
            capabilities={
                "cpu": True,
                "gpu": True,
                "platform": "substrate-local",
                "role": "donor",
            },
        )
        node = CommunityNode(node_id=node_id, config=config)
        COMMUNITY_REGISTRY.register(node)

    def evaluate(self, local_utilization: float) -> dict[str, Any]:
        eligible = COMMUNITY_REGISTRY.eligible_for_donation(local_utilization)
        if eligible and not self._donating:
            self._donating = True
            self._donated_workers = min(
                self.max_donated_workers,
                max(1, int((1.0 - local_utilization) * 4)),
            )
            logger.info(
                "Starting cycle donation: %d workers at %.0f%% local utilization",
                self._donated_workers,
                local_utilization * 100,
            )
            return {
                "action": "start_donating",
                "donated_workers": self._donated_workers,
                "local_utilization": local_utilization,
            }
        if not eligible and self._donating:
            logger.info("Reclaiming donated cycles: local utilization %.0f%%", local_utilization * 100)
            self._donating = False
            reclaimed = self._donated_workers
            self._donated_workers = 0
            return {
                "action": "stop_donating",
                "reclaimed_workers": reclaimed,
                "local_utilization": local_utilization,
            }
        return {
            "action": "noop",
            "donating": self._donating,
            "donated_workers": self._donated_workers,
            "local_utilization": local_utilization,
        }

    def donate_status(self) -> dict[str, Any]:
        return {
            "donating": self._donating,
            "donated_workers": self._donated_workers,
            "max_donated": self.max_donated_workers,
            "idle_threshold": self.idle_threshold,
        }


# ---------------------------------------------------------------------------
# High-level facade
# ---------------------------------------------------------------------------

class DistributedComputeFacade:
    """Unified interface for all distributed compute community integrations."""

    def __init__(self) -> None:
        self.boinc = BOINCAdapter()
        self.mesh_llm = MeshLLMAdapter()
        self.local_donor = LocalCycleDonor()
        self._initialized = False

    def initialize(self, configs: list[CommunityNodeConfig] | None = None) -> dict[str, Any]:
        if self._initialized:
            return {"status": "already_initialized"}
        results: dict[str, Any] = {"boinc": [], "mesh_llm": [], "local_donor": None}
        configs = configs or []
        for cfg in configs:
            if cfg.kind == "boinc":
                node = self.boinc.register_project_node(
                    cfg.project_id or "rosetta",
                    max_tasks=cfg.max_concurrent_tasks,
                )
                if node:
                    results["boinc"].append(node.node_id)
            elif cfg.kind == "mesh-llm":
                node = self.mesh_llm.register_compute_node(
                    cfg.project_id or "mesh-llm-local",
                    max_concurrent=cfg.max_concurrent_tasks,
                )
                results["mesh_llm"].append(node.node_id)
        results["local_donor"] = self.local_donor.donate_status()
        self._initialized = True
        logger.info("Distributed compute initialized: %s", results)
        return results

    def heartbeat_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for node in COMMUNITY_REGISTRY.all_nodes():
            if node.config.kind == "boinc":
                results[node.node_id] = self.boinc.heartbeat(node.node_id)
            elif node.config.kind == "mesh-llm":
                results[node.node_id] = self.mesh_llm.heartbeat(node.node_id)
            elif node.config.kind == "local-donor":
                results[node.node_id] = {
                    "status": node.status,
                    "donating": node.config.donate_when_idle,
                    "utilization": node.current_utilization,
                }
        return results

    def evaluate_donation(self, local_utilization: float) -> dict[str, Any]:
        return self.local_donor.evaluate(local_utilization)

    def request_community_inference(
        self, prompt: str, preferred_kind: CommunityKind | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        available = COMMUNITY_REGISTRY.available_for_work()
        if preferred_kind:
            available = [n for n in available if n.config.kind == preferred_kind] or available
        if not available:
            return {"error": "no community nodes available", "provider": "none"}
        node = available[0]
        if node.config.kind == "mesh-llm":
            return self.mesh_llm.request_inference(node.node_id, prompt, **kwargs)
        return {
            "error": f"inference not supported for {node.config.kind}",
            "node": node.node_id,
            "provider": node.config.kind,
        }

    def export_compute_nodes(self) -> list[ComputeNode]:
        return [n.to_compute_node() for n in COMMUNITY_REGISTRY.all_nodes()]

    def summary(self) -> dict[str, Any]:
        nodes = COMMUNITY_REGISTRY.all_nodes()
        kinds: tuple[CommunityKind, ...] = ("boinc", "mesh-llm", "local-donor")
        return {
            "total_nodes": len(nodes),
            "by_kind": {
                kind: len(COMMUNITY_REGISTRY.nodes_by_kind(kind))
                for kind in kinds
            },
            "available_for_work": len(COMMUNITY_REGISTRY.available_for_work()),
            "donation_status": self.local_donor.donate_status(),
            "nodes": [
                {
                    "node_id": n.node_id,
                    "kind": n.config.kind,
                    "status": n.status,
                    "utilization": n.current_utilization,
                    "tasks_completed": n.tasks_completed,
                }
                for n in nodes
            ],
        }


# Singleton facade used by orchestrator / scheduler hooks
distributed_compute = DistributedComputeFacade()
