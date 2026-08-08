"""Comprehensive test suite for Substrate Deploy System."""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Import control panel components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "control-panel" / "backend"))
from main import app, get_db, Agent, Deployment

# Import agent components
sys.path.insert(0, str(Path(__file__).parent.parent / "agent"))
from agent import SubstrateAgent, AgentState, DEFAULT_CONFIG


@pytest.fixture
def test_db():
    """Create a test database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create tables
    from main import Base
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield TestingSessionLocal

    # Cleanup
    Base.metadata.drop_all(bind=engine)
    Path("./test.db").unlink(missing_ok=True)


@pytest.fixture
def client(test_db):
    """Create test client."""
    return TestClient(app)


class TestControlPanelAPI:
    """Test control panel API endpoints."""

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Substrate Deploy Control Panel"
        assert data["version"] == "1.0.0"
        assert data["status"] == "operational"

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_create_agent(self, client):
        """Test agent registration."""
        response = client.post(
            "/api/agents",
            json={"name": "test-agent", "hostname": "test-host"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "test-agent"
        assert data["hostname"] == "test-host"
        assert "id" in data
        assert "api_key" in data
        assert data["status"] == "offline"

    def test_create_duplicate_agent(self, client):
        """Test duplicate agent registration fails."""
        client.post("/api/agents", json={"name": "duplicate-agent"})
        response = client.post("/api/agents", json={"name": "duplicate-agent"})
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_list_agents(self, client):
        """Test listing agents."""
        # Create some agents
        client.post("/api/agents", json={"name": "agent1"})
        client.post("/api/agents", json={"name": "agent2"})

        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] in ["agent1", "agent2"]
        assert data[1]["name"] in ["agent1", "agent2"]

    def test_get_agent(self, client):
        """Test getting agent details."""
        create_response = client.post("/api/agents", json={"name": "get-test-agent"})
        agent_id = create_response.json()["id"]

        response = client.get(f"/api/agents/{agent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "get-test-agent"
        assert data["id"] == agent_id

    def test_get_nonexistent_agent(self, client):
        """Test getting non-existent agent."""
        response = client.get("/api/agents/nonexistent-id")
        assert response.status_code == 404

    def test_update_agent_status(self, client):
        """Test updating agent status."""
        create_response = client.post("/api/agents", json={"name": "status-test-agent"})
        agent_id = create_response.json()["id"]

        response = client.patch(
            f"/api/agents/{agent_id}/status",
            json={
                "status": "online",
                "version": "1.0.0",
                "hostname": "updated-host",
                "ip_address": "192.168.1.100"
            }
        )
        assert response.status_code == 200

        # Verify update
        get_response = client.get(f"/api/agents/{agent_id}")
        data = get_response.json()
        assert data["status"] == "online"
        assert data["version"] == "1.0.0"
        assert data["hostname"] == "updated-host"
        assert data["ip_address"] == "192.168.1.100"

    def test_delete_agent(self, client):
        """Test deleting an agent."""
        create_response = client.post("/api/agents", json={"name": "delete-test-agent"})
        agent_id = create_response.json()["id"]

        response = client.delete(f"/api/agents/{agent_id}")
        assert response.status_code == 200

        # Verify deletion
        get_response = client.get(f"/api/agents/{agent_id}")
        assert get_response.status_code == 404

    def test_create_deployment(self, client):
        """Test creating a deployment."""
        # Create agent first
        agent_response = client.post("/api/agents", json={"name": "deploy-agent"})
        agent_id = agent_response.json()["id"]

        # Create deployment
        response = client.post(
            "/api/deployments",
            json={"agent_id": agent_id, "version": "1.0.0"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == agent_id
        assert data["version"] == "1.0.0"
        assert data["status"] == "pending"

    def test_create_deployment_invalid_agent(self, client):
        """Test creating deployment for non-existent agent."""
        response = client.post(
            "/api/deployments",
            json={"agent_id": "nonexistent", "version": "1.0.0"}
        )
        assert response.status_code == 404

    def test_list_deployments(self, client):
        """Test listing deployments."""
        # Create agent
        agent_response = client.post("/api/agents", json={"name": "list-deploy-agent"})
        agent_id = agent_response.json()["id"]

        # Create deployments
        client.post("/api/deployments", json={"agent_id": agent_id, "version": "1.0.0"})
        client.post("/api/deployments", json={"agent_id": agent_id, "version": "1.1.0"})

        response = client.get("/api/deployments")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_deployments_filtered(self, client):
        """Test listing deployments filtered by agent."""
        # Create agents
        agent1_response = client.post("/api/agents", json={"name": "filter-agent1"})
        agent2_response = client.post("/api/agents", json={"name": "filter-agent2"})
        agent1_id = agent1_response.json()["id"]
        agent2_id = agent2_response.json()["id"]

        # Create deployments
        client.post("/api/deployments", json={"agent_id": agent1_id, "version": "1.0.0"})
        client.post("/api/deployments", json={"agent_id": agent2_id, "version": "1.0.0"})

        # Filter by agent1
        response = client.get(f"/api/deployments?agent_id={agent1_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == agent1_id

    def test_update_deployment_status(self, client):
        """Test updating deployment status."""
        # Create agent and deployment
        agent_response = client.post("/api/agents", json={"name": "update-deploy-agent"})
        agent_id = agent_response.json()["id"]
        deploy_response = client.post(
            "/api/deployments",
            json={"agent_id": agent_id, "version": "1.0.0"}
        )
        deployment_id = deploy_response.json()["id"]

        # Update status
        response = client.patch(
            f"/api/deployments/{deployment_id}/status",
            json={"status": "success", "logs": "Deployment completed"}
        )
        assert response.status_code == 200

        # Verify update
        deployments = client.get("/api/deployments").json()
        deployment = next(d for d in deployments if d["id"] == deployment_id)
        assert deployment["status"] == "success"
        assert deployment["logs"] == "Deployment completed"
        assert deployment["completed_at"] is not None

    def test_dashboard_stats(self, client):
        """Test dashboard statistics."""
        # Create agents with different statuses
        agent1 = client.post("/api/agents", json={"name": "stats-agent1"}).json()
        agent2 = client.post("/api/agents", json={"name": "stats-agent2"}).json()

        # Update one agent to online
        client.patch(
            f"/api/agents/{agent1['id']}/status",
            json={"status": "online"}
        )

        # Create deployments
        client.post("/api/deployments", json={"agent_id": agent1["id"], "version": "1.0.0"})
        deploy2 = client.post("/api/deployments", json={"agent_id": agent2["id"], "version": "1.0.0"}).json()
        client.patch(
            f"/api/deployments/{deploy2['id']}/status",
            json={"status": "success"}
        )

        # Get stats
        response = client.get("/api/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_agents"] == 2
        assert data["online_agents"] == 1
        assert data["offline_agents"] == 1
        assert data["total_deployments"] == 2
        assert data["successful_deployments"] == 1

    def test_metrics_endpoint(self, client):
        """Test Prometheus metrics endpoint."""
        # Create some data
        client.post("/api/agents", json={"name": "metrics-agent"})

        response = client.get("/metrics")
        assert response.status_code == 200
        assert "substrate_agents_total" in response.text
        assert "substrate_deployments_total" in response.text


class TestAgentState:
    """Test agent state management."""

    def test_state_initialization(self, tmp_path):
        """Test state initialization."""
        with patch('agent.STATE_FILE', tmp_path / "state.json"):
            state = AgentState()
            assert state.state["current_version"] is None
            assert state.state["last_heartbeat"] is None
            assert state.state["deployment_history"] == []

    def test_state_persistence(self, tmp_path):
        """Test state persistence."""
        state_file = tmp_path / "state.json"
        with patch('agent.STATE_FILE', state_file):
            state = AgentState()
            state.update_version("1.0.0")
            state.update_heartbeat()

            # Load again
            state2 = AgentState()
            assert state2.state["current_version"] == "1.0.0"
            assert state2.state["last_heartbeat"] is not None

    def test_deployment_history(self, tmp_path):
        """Test deployment history tracking."""
        with patch('agent.STATE_FILE', tmp_path / "state.json"):
            state = AgentState()
            state.add_deployment("dep1", "1.0.0", "success")
            state.add_deployment("dep2", "1.1.0", "failed")

            assert len(state.state["deployment_history"]) == 2
            assert state.state["deployment_history"][0]["id"] == "dep1"
            assert state.state["deployment_history"][1]["id"] == "dep2"

    def test_deployment_history_limit(self, tmp_path):
        """Test deployment history is limited to 100 entries."""
        with patch('agent.STATE_FILE', tmp_path / "state.json"):
            state = AgentState()

            # Add 150 deployments
            for i in range(150):
                state.add_deployment(f"dep{i}", "1.0.0", "success")

            assert len(state.state["deployment_history"]) == 100


class TestSubstrateAgent:
    """Test SubstrateAgent class."""

    def test_agent_initialization(self):
        """Test agent initialization."""
        config = DEFAULT_CONFIG.copy()
        agent = SubstrateAgent(config)
        assert agent.config == config
        assert agent.running is False

    def test_get_ip_address(self):
        """Test IP address detection."""
        config = DEFAULT_CONFIG.copy()
        agent = SubstrateAgent(config)
        ip = agent._get_ip_address()
        assert ip is not None
        assert isinstance(ip, str)

    def test_calculate_hash(self, tmp_path):
        """Test file hash calculation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        config = DEFAULT_CONFIG.copy()
        agent = SubstrateAgent(config)
        hash1 = agent._calculate_hash(test_file)

        # Same content should produce same hash
        test_file2 = tmp_path / "test2.txt"
        test_file2.write_text("test content")
        hash2 = agent._calculate_hash(test_file2)

        assert hash1 == hash2

        # Different content should produce different hash
        test_file3 = tmp_path / "test3.txt"
        test_file3.write_text("different content")
        hash3 = agent._calculate_hash(test_file3)

        assert hash1 != hash3

    @patch('agent.httpx.Client')
    def test_heartbeat(self, mock_client_class):
        """Test heartbeat functionality."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.patch.return_value = mock_response

        config = DEFAULT_CONFIG.copy()
        config["agent_id"] = "test-id"
        agent = SubstrateAgent(config)

        result = agent.heartbeat()
        assert result is True
        mock_client.patch.assert_called_once()

    def test_heartbeat_unregistered(self):
        """Test heartbeat when agent is not registered."""
        config = DEFAULT_CONFIG.copy()
        agent = SubstrateAgent(config)

        result = agent.heartbeat()
        assert result is False

    @patch('agent.httpx.Client')
    def test_register(self, mock_client_class, tmp_path):
        """Test agent registration."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "test-id",
            "api_key": "test-key",
            "name": "test-agent"
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        config = DEFAULT_CONFIG.copy()
        agent = SubstrateAgent(config)

        with patch('agent.CONFIG_FILE', tmp_path / "config.json"):
            result = agent.register("test-agent")
            assert result["id"] == "test-id"
            assert result["api_key"] == "test-key"
            assert agent.config["agent_id"] == "test-id"
            assert agent.config["api_key"] == "test-key"


class TestIntegration:
    """Integration tests for the complete system."""

    def test_full_deployment_flow(self, client):
        """Test complete deployment flow."""
        # 1. Register agent
        agent_response = client.post(
            "/api/agents",
            json={"name": "integration-agent", "hostname": "test-host"}
        )
        assert agent_response.status_code == 201
        agent = agent_response.json()
        agent_id = agent["id"]

        # 2. Agent sends heartbeat
        status_response = client.patch(
            f"/api/agents/{agent_id}/status",
            json={
                "status": "online",
                "version": "1.0.0",
                "hostname": "test-host",
                "ip_address": "192.168.1.100"
            }
        )
        assert status_response.status_code == 200

        # 3. Create deployment
        deploy_response = client.post(
            "/api/deployments",
            json={"agent_id": agent_id, "version": "1.0.0"}
        )
        assert deploy_response.status_code == 201
        deployment = deploy_response.json()
        deployment_id = deployment["id"]

        # 4. Update deployment status
        update_response = client.patch(
            f"/api/deployments/{deployment_id}/status",
            json={
                "status": "success",
                "logs": "Deployment completed successfully"
            }
        )
        assert update_response.status_code == 200

        # 5. Verify final state
        agent_final = client.get(f"/api/agents/{agent_id}").json()
        assert agent_final["status"] == "online"
        assert agent_final["version"] == "1.0.0"

        deployment_final = next(
            d for d in client.get("/api/deployments").json()
            if d["id"] == deployment_id
        )
        assert deployment_final["status"] == "success"
        assert deployment_final["completed_at"] is not None

    def test_multiple_agents_and_deployments(self, client):
        """Test system with multiple agents and deployments."""
        # Create 5 agents
        agents = []
        for i in range(5):
            response = client.post("/api/agents", json={"name": f"multi-agent-{i}"})
            assert response.status_code == 201
            agents.append(response.json())

        # Create 10 deployments (2 per agent)
        deployments = []
        for agent in agents:
            for version in ["1.0.0", "1.1.0"]:
                response = client.post(
                    "/api/deployments",
                    json={"agent_id": agent["id"], "version": version}
                )
                assert response.status_code == 201
                deployments.append(response.json())

        # Verify counts
        stats = client.get("/api/dashboard/stats").json()
        assert stats["total_agents"] == 5
        assert stats["total_deployments"] == 10

        # Update some deployments to success
        for deployment in deployments[:5]:
            client.patch(
                f"/api/deployments/{deployment['id']}/status",
                json={"status": "success"}
            )

        # Verify stats updated
        stats = client.get("/api/dashboard/stats").json()
        assert stats["successful_deployments"] == 5


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_json(self, client):
        """Test handling of invalid JSON."""
        response = client.post(
            "/api/agents",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_missing_required_fields(self, client):
        """Test handling of missing required fields."""
        response = client.post("/api/agents", json={})
        assert response.status_code == 422

    def test_invalid_agent_name(self, client):
        """Test handling of invalid agent name."""
        response = client.post("/api/agents", json={"name": ""})
        assert response.status_code == 422

    def test_concurrent_requests(self, client):
        """Test handling of concurrent requests."""
        import concurrent.futures

        def create_agent(i):
            return client.post("/api/agents", json={"name": f"concurrent-agent-{i}"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_agent, i) for i in range(10)]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.status_code == 201 for r in results)

        # Verify all agents created
        agents = client.get("/api/agents").json()
        assert len(agents) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
