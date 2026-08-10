"""FastAPI router for dashboard endpoints.

Provides REST API and Prometheus metrics exposition for the dashboard.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .collectors import MultiNodeCollector
from .metrics import get_metrics_registry


def create_dashboard_router(
    templates_dir: Path | None = None,
    static_dir: Path | None = None,
) -> APIRouter:
    """Create the dashboard API router.

    Args:
        templates_dir: Path to Jinja2 templates directory.
        static_dir: Path to static files directory.

    Returns:
        Configured FastAPI router.
    """
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    # Initialize collectors
    collector = MultiNodeCollector()

    # Setup templates if provided
    templates = None
    if templates_dir and templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

    @router.get("/metrics")
    async def metrics() -> Response:
        """Expose Prometheus metrics.

        Returns metrics in Prometheus text exposition format
        for scraping by Prometheus server.
        """
        metrics_registry = get_metrics_registry()
        return Response(
            content=metrics_registry.generate_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @router.get("/health")
    async def health() -> dict[str, Any]:
        """Health check endpoint.

        Returns:
            Health status dictionary.
        """
        return {
            "status": "ok",
            "service": "substrate-dashboard",
            "nodes_configured": len(collector.collectors),
        }

    @router.get("/nodes")
    async def list_nodes() -> dict[str, Any]:
        """List configured nodes.

        Returns:
            Dictionary of configured nodes.
        """
        return {
            "nodes": {
                node_id: {
                    "rpc_url": coll.rpc_url,
                    "network": coll.network,
                }
                for node_id, coll in collector.collectors.items()
            }
        }

    @router.post("/nodes/{node_id}")
    async def add_node(
        node_id: str,
        rpc_url: str,
        network: str,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """Add a node to monitor.

        Args:
            node_id: Unique node identifier.
            rpc_url: JSON-RPC endpoint URL.
            network: Network name.
            timeout: RPC timeout in seconds.

        Returns:
            Success status.
        """
        collector.add_node(node_id, rpc_url, network, timeout)
        return {"status": "ok", "node_id": node_id}

    @router.delete("/nodes/{node_id}")
    async def remove_node(node_id: str) -> dict[str, Any]:
        """Remove a node from monitoring.

        Args:
            node_id: Node identifier to remove.

        Returns:
            Success status.
        """
        if node_id not in collector.collectors:
            raise HTTPException(status_code=404, detail="Node not found")
        collector.remove_node(node_id)
        return {"status": "ok", "node_id": node_id}

    @router.get("/collect")
    async def collect_metrics() -> dict[str, Any]:
        """Collect metrics from all configured nodes.

        Returns:
            Collected metrics from all nodes.
        """
        if not collector.collectors:
            return {"nodes": {}, "message": "No nodes configured"}

        metrics = await collector.collect_all()
        return {"nodes": metrics, "collected_at": __import__("time").time()}

    @router.get("/status")
    async def status() -> dict[str, Any]:
        """Get current dashboard status.

        Returns:
            Current status including node health and chain metrics.
        """
        if not collector.collectors:
            return {
                "status": "ok",
                "nodes": 0,
                "message": "No nodes configured",
            }

        metrics = await collector.collect_all()
        return {
            "status": "ok",
            "nodes": len(collector.collectors),
            "metrics": metrics,
        }

    @router.get("/", response_class=HTMLResponse)
    async def dashboard_ui(request: Request) -> HTMLResponse:
        """Dashboard web UI.

        Returns:
            HTML dashboard page.
        """
        if templates is None:
            return HTMLResponse(
                content="<html><body><h1>Dashboard</h1><p>Templates not configured</p></body></html>",
                status_code=503,
            )

        context = {
            "request": request,
            "node_count": len(collector.collectors),
        }
        return templates.TemplateResponse("dashboard.html", context)

    return router
