#!/usr/bin/env python3
"""Standalone pipelines service entry point.

Starts the Substrate pipelines service for CI/CD workflow orchestration.
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

from substrate.pipelines import PipelineEngine, PipelineRegistry, create_pipelines_router


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Substrate Pipelines Service",
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
        default=8092,
        help="Port to bind to (default: 8092)",
    )
    parser.add_argument(
        "--pipelines-dir",
        type=Path,
        default=ROOT / "pipelines",
        help="Directory containing pipeline YAML files (default: ./pipelines)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    return parser.parse_args()


def create_app(pipelines_dir: Path) -> FastAPI:
    """Create the pipelines FastAPI application."""
    app = FastAPI(
        title="Substrate Pipelines Service",
        version="0.1.0",
        description="CI/CD workflow orchestration for Substrate projects",
    )

    # Add CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize pipeline registry and engine
    registry = PipelineRegistry()
    
    # Load pipelines from directory
    if pipelines_dir.exists():
        count = registry.load_from_directory(pipelines_dir)
        print(f"📋 Loaded {count} pipeline(s) from {pipelines_dir}")
    else:
        print(f"⚠️  Pipelines directory not found: {pipelines_dir}")

    engine = PipelineEngine(
        registry=registry,
        workdir=ROOT,
        artifacts_dir=ROOT / "artifacts" / "pipelines",
    )

    # Create pipelines router
    pipelines_router = create_pipelines_router(registry, engine)
    app.include_router(pipelines_router)

    @app.get("/")
    async def root():
        """Root endpoint with service info."""
        return {
            "service": "substrate-pipelines",
            "version": "0.1.0",
            "endpoints": {
                "pipelines": "/pipelines/",
                "runs": "/pipelines/runs",
                "webhook": "/pipelines/webhook/github",
            },
            "loaded_pipelines": len(registry.list()),
        }

    @app.on_event("startup")
    async def startup():
        """Initialize pipelines on startup."""
        print("🚀 Substrate Pipelines Service starting...")
        print(f"📋 Pipelines API at: http://{args.host}:{args.port}/pipelines/")
        print(f"🔗 Webhook endpoint at: http://{args.host}:{args.port}/pipelines/webhook/github")

    return app


if __name__ == "__main__":
    args = parse_args()

    app = create_app(args.pipelines_dir)

    print(f"Starting Substrate Pipelines Service on {args.host}:{args.port}")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
