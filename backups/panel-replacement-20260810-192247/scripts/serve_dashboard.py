#!/usr/bin/env python3
"""Standalone dashboard service entry point.

Starts the Substrate dashboard service with Prometheus metrics exposition.
Can be run independently from the main substrate ops panel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from substrate.dashboard import create_dashboard_router


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Substrate Dashboard Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8091,
        help="Port to bind to (default: 8091)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    return parser.parse_args()


def create_app() -> FastAPI:
    """Create the dashboard FastAPI application."""
    app = FastAPI(
        title="Substrate Dashboard Service",
        version="0.1.0",
        description="Real-time monitoring dashboard for Substrate blockchain nodes",
    )

    # Add CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create dashboard router
    templates_dir = ROOT / "substrate" / "dashboard" / "templates"
    static_dir = ROOT / "substrate" / "dashboard" / "static"

    dashboard_router = create_dashboard_router(
        templates_dir=templates_dir if templates_dir.exists() else None,
        static_dir=static_dir if static_dir.exists() else None,
    )

    app.include_router(dashboard_router)

    @app.get("/")
    async def root():
        """Root endpoint with service info."""
        return {
            "service": "substrate-dashboard",
            "version": "0.1.0",
            "endpoints": {
                "metrics": "/dashboard/metrics",
                "health": "/dashboard/health",
                "nodes": "/dashboard/nodes",
                "collect": "/dashboard/collect",
                "status": "/dashboard/status",
            },
        }

    @app.on_event("startup")
    async def startup():
        """Initialize dashboard on startup."""
        print("🚀 Substrate Dashboard Service starting...")
        print(f"📊 Metrics available at: http://{args.host}:{args.port}/dashboard/metrics")
        print(f"💚 Health check at: http://{args.host}:{args.port}/dashboard/health")

    return app


if __name__ == "__main__":
    args = parse_args()

    app = create_app()

    print(f"Starting Substrate Dashboard Service on {args.host}:{args.port}")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
