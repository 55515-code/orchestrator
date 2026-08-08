#!/usr/bin/env python3
"""
Substrate Deploy Agent - Lightweight deployment agent for endpoints.

This agent runs on target machines and manages:
- File synchronization from control panel
- Status reporting and heartbeats
- Self-update capability
- Health monitoring
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Configuration
AGENT_DIR = Path.home() / ".substrate-agent"
CONFIG_FILE = AGENT_DIR / "config.json"
STATE_FILE = AGENT_DIR / "state.json"
LOG_DIR = AGENT_DIR / "logs"
DEPLOY_DIR = AGENT_DIR / "deployments"

# Default configuration
DEFAULT_CONFIG = {
    "control_panel_url": "http://localhost:8080",
    "agent_id": None,
    "api_key": None,
    "heartbeat_interval": 30,
    "log_level": "INFO",
}

# Setup logging
def setup_logging(level: str = "INFO") -> logging.Logger:
    """Setup logging configuration."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"agent-{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("substrate-agent")


logger = setup_logging()


class AgentState:
    """Manage agent state persistence."""

    def __init__(self):
        self.state_file = STATE_FILE
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        """Load state from file."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
        return {
            "current_version": None,
            "last_heartbeat": None,
            "deployment_history": [],
        }

    def save(self):
        """Save state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def update_heartbeat(self):
        """Update last heartbeat timestamp."""
        self.state["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def update_version(self, version: str):
        """Update current version."""
        self.state["current_version"] = version
        self.save()

    def add_deployment(self, deployment_id: str, version: str, status: str):
        """Add deployment to history."""
        self.state["deployment_history"].append({
            "id": deployment_id,
            "version": version,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep only last 100 deployments
        self.state["deployment_history"] = self.state["deployment_history"][-100:]
        self.save()


class SubstrateAgent:
    """Main agent class."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.state = AgentState()
        self.client = httpx.Client(timeout=30.0)
        self.running = False

    def register(self, name: str) -> dict[str, Any]:
        """Register agent with control panel."""
        logger.info(f"Registering agent with name: {name}")

        hostname = socket.gethostname()
        ip_address = self._get_ip_address()

        payload = {
            "name": name,
            "hostname": hostname,
            "metadata": {
                "platform": sys.platform,
                "python_version": sys.version,
                "agent_version": "1.0.0",
            },
        }

        try:
            response = self.client.post(
                f"{self.config['control_panel_url']}/api/agents",
                json=payload,
            )
            response.raise_for_status()
            agent_data = response.json()

            # Save credentials
            self.config["agent_id"] = agent_data["id"]
            self.config["api_key"] = agent_data["api_key"]
            self._save_config()

            logger.info(f"Agent registered successfully: {agent_data['id']}")
            return agent_data

        except Exception as e:
            logger.error(f"Failed to register agent: {e}")
            raise

    def heartbeat(self) -> bool:
        """Send heartbeat to control panel."""
        if not self.config.get("agent_id"):
            logger.warning("Agent not registered, skipping heartbeat")
            return False

        try:
            payload = {
                "status": "online",
                "version": self.state.state.get("current_version"),
                "hostname": socket.gethostname(),
                "ip_address": self._get_ip_address(),
            }

            response = self.client.patch(
                f"{self.config['control_panel_url']}/api/agents/{self.config['agent_id']}/status",
                json=payload,
            )
            response.raise_for_status()

            self.state.update_heartbeat()
            logger.debug("Heartbeat sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
            return False

    def deploy(self, deployment_id: str, version: str, files_url: str) -> bool:
        """Deploy application files."""
        logger.info(f"Starting deployment {deployment_id} version {version}")

        try:
            # Update deployment status to deploying
            self._update_deployment_status(deployment_id, "deploying")

            # Create deployment directory
            deploy_dir = DEPLOY_DIR / deployment_id
            deploy_dir.mkdir(parents=True, exist_ok=True)

            # Download and extract files
            response = self.client.get(files_url)
            response.raise_for_status()

            # Save files (in production, this would be a tarball extraction)
            archive_path = deploy_dir / "app.tar.gz"
            archive_path.write_bytes(response.content)

            # Extract archive
            shutil.unpack_archive(archive_path, deploy_dir)
            archive_path.unlink()

            # Verify deployment
            if self._verify_deployment(deploy_dir):
                # Update state
                self.state.update_version(version)
                self.state.add_deployment(deployment_id, version, "success")

                # Update deployment status
                self._update_deployment_status(deployment_id, "success")

                logger.info(f"Deployment {deployment_id} completed successfully")
                return True
            else:
                raise Exception("Deployment verification failed")

        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            self.state.add_deployment(deployment_id, version, "failed")
            self._update_deployment_status(deployment_id, "failed", error_message=str(e))
            return False

    def _verify_deployment(self, deploy_dir: Path) -> bool:
        """Verify deployment integrity."""
        # Check for required files
        required_files = ["app.py", "requirements.txt"]
        for file in required_files:
            if not (deploy_dir / file).exists():
                logger.error(f"Required file missing: {file}")
                return False

        # Verify file checksums if manifest exists
        manifest_path = deploy_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                for file_path, expected_hash in manifest.get("checksums", {}).items():
                    full_path = deploy_dir / file_path
                    if not full_path.exists():
                        return False
                    actual_hash = self._calculate_hash(full_path)
                    if actual_hash != expected_hash:
                        logger.error(f"Checksum mismatch for {file_path}")
                        return False
            except Exception as e:
                logger.error(f"Failed to verify manifest: {e}")
                return False

        return True

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _update_deployment_status(
        self,
        deployment_id: str,
        status: str,
        logs: str | None = None,
        error_message: str | None = None,
    ):
        """Update deployment status on control panel."""
        try:
            payload = {"status": status}
            if logs:
                payload["logs"] = logs
            if error_message:
                payload["error_message"] = error_message

            self.client.patch(
                f"{self.config['control_panel_url']}/api/deployments/{deployment_id}/status",
                json=payload,
            )
        except Exception as e:
            logger.error(f"Failed to update deployment status: {e}")

    def _get_ip_address(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _save_config(self):
        """Save configuration to file."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self.config, indent=2))

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from file."""
        if CONFIG_FILE.exists():
            try:
                return json.loads(CONFIG_FILE.read_text())
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return DEFAULT_CONFIG.copy()

    def run(self):
        """Run agent main loop."""
        logger.info("Starting Substrate Agent")
        self.running = True

        heartbeat_interval = self.config.get("heartbeat_interval", 30)

        while self.running:
            try:
                # Send heartbeat
                self.heartbeat()

                # Sleep until next heartbeat
                time.sleep(heartbeat_interval)

            except KeyboardInterrupt:
                logger.info("Agent stopped by user")
                self.running = False
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)

    def stop(self):
        """Stop agent."""
        self.running = False
        logger.info("Agent stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Substrate Deploy Agent")
    parser.add_argument(
        "--register",
        metavar="NAME",
        help="Register agent with control panel",
    )
    parser.add_argument(
        "--deploy",
        nargs=3,
        metavar=("DEPLOYMENT_ID", "VERSION", "FILES_URL"),
        help="Deploy application",
    )
    parser.add_argument(
        "--control-panel-url",
        default="http://localhost:8080",
        help="Control panel URL",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=30,
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Log level",
    )

    args = parser.parse_args()

    # Setup logging
    global logger
    logger = setup_logging(args.log_level)

    # Load or create config
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            config.update(json.loads(CONFIG_FILE.read_text()))
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")

    # Override with command line args
    config["control_panel_url"] = args.control_panel_url
    config["heartbeat_interval"] = args.heartbeat_interval

    # Create agent
    agent = SubstrateAgent(config)

    # Handle commands
    if args.register:
        agent.register(args.register)
    elif args.deploy:
        deployment_id, version, files_url = args.deploy
        success = agent.deploy(deployment_id, version, files_url)
        sys.exit(0 if success else 1)
    else:
        # Run agent
        agent.run()


if __name__ == "__main__":
    main()
