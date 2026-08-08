"""Control Panel Backend API for Substrate Deploy System."""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./control_panel.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Security
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

# Models
class Agent(Base):
    """Registered agent endpoint."""
    __tablename__ = "agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False)
    api_key = Column(String, unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    hostname = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    version = Column(String, nullable=True)
    status = Column(String, default="offline")  # online, offline, error
    last_heartbeat = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    metadata_json = Column(Text, nullable=True)

class Deployment(Base):
    """Deployment record."""
    __tablename__ = "deployments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_id = Column(String, nullable=False)
    version = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, deploying, success, failed
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    logs = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

# Pydantic schemas
class AgentCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=64)
    hostname: str | None = None
    metadata: dict[str, Any] | None = None

class AgentResponse(BaseModel):
    id: str
    name: str
    api_key: str
    hostname: str | None
    ip_address: str | None
    version: str | None
    status: str
    last_heartbeat: datetime | None
    created_at: datetime

class AgentStatusUpdate(BaseModel):
    status: str
    version: str | None = None
    hostname: str | None = None
    ip_address: str | None = None

class DeploymentCreate(BaseModel):
    agent_id: str
    version: str

class DeploymentResponse(BaseModel):
    id: str
    agent_id: str
    version: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    logs: str | None
    error_message: str | None

class DashboardStats(BaseModel):
    total_agents: int
    online_agents: int
    offline_agents: int
    total_deployments: int
    successful_deployments: int
    failed_deployments: int

# Database dependency
def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create FastAPI app
app = FastAPI(
    title="Substrate Deploy Control Panel",
    description="Centralized control panel for managing Substrate deployments",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Substrate Deploy Control Panel",
        "version": "1.0.0",
        "status": "operational",
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Agent endpoints
@app.post("/api/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(agent: AgentCreate, db: Session = Depends(get_db)):
    """Register a new agent."""
    # Check if agent name already exists
    existing = db.query(Agent).filter(Agent.name == agent.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent name already exists")

    # Create new agent
    db_agent = Agent(
        name=agent.name,
        hostname=agent.hostname,
        metadata_json=str(agent.metadata) if agent.metadata else None,
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)

    # Broadcast update
    await manager.broadcast({
        "type": "agent_created",
        "data": {
            "id": db_agent.id,
            "name": db_agent.name,
            "status": db_agent.status,
        }
    })

    return db_agent

@app.get("/api/agents", response_model=list[AgentResponse])
async def list_agents(db: Session = Depends(get_db)):
    """List all registered agents."""
    agents = db.query(Agent).all()
    return agents

@app.get("/api/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """Get agent details."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@app.patch("/api/agents/{agent_id}/status")
async def update_agent_status(
    agent_id: str,
    update: AgentStatusUpdate,
    db: Session = Depends(get_db)
):
    """Update agent status (called by agent heartbeat)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.status = update.status
    agent.last_heartbeat = datetime.now(timezone.utc)
    if update.version:
        agent.version = update.version
    if update.hostname:
        agent.hostname = update.hostname
    if update.ip_address:
        agent.ip_address = update.ip_address

    db.commit()

    # Broadcast update
    await manager.broadcast({
        "type": "agent_status_updated",
        "data": {
            "id": agent.id,
            "name": agent.name,
            "status": agent.status,
            "last_heartbeat": agent.last_heartbeat.isoformat(),
        }
    })

    return {"status": "updated"}

@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """Delete an agent."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    db.delete(agent)
    db.commit()

    await manager.broadcast({
        "type": "agent_deleted",
        "data": {"id": agent_id}
    })

    return {"status": "deleted"}

# Deployment endpoints
@app.post("/api/deployments", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(deployment: DeploymentCreate, db: Session = Depends(get_db)):
    """Create a new deployment."""
    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == deployment.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    db_deployment = Deployment(
        agent_id=deployment.agent_id,
        version=deployment.version,
    )
    db.add(db_deployment)
    db.commit()
    db.refresh(db_deployment)

    await manager.broadcast({
        "type": "deployment_created",
        "data": {
            "id": db_deployment.id,
            "agent_id": db_deployment.agent_id,
            "version": db_deployment.version,
            "status": db_deployment.status,
        }
    })

    return db_deployment

@app.get("/api/deployments", response_model=list[DeploymentResponse])
async def list_deployments(agent_id: str | None = None, db: Session = Depends(get_db)):
    """List deployments, optionally filtered by agent."""
    query = db.query(Deployment)
    if agent_id:
        query = query.filter(Deployment.agent_id == agent_id)
    return query.order_by(Deployment.started_at.desc()).all()

@app.patch("/api/deployments/{deployment_id}/status")
async def update_deployment_status(
    deployment_id: str,
    status_update: dict,
    db: Session = Depends(get_db)
):
    """Update deployment status."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if "status" in status_update:
        deployment.status = status_update["status"]
    if "logs" in status_update:
        deployment.logs = status_update["logs"]
    if "error_message" in status_update:
        deployment.error_message = status_update["error_message"]
    if status_update.get("status") in ["success", "failed"]:
        deployment.completed_at = datetime.now(timezone.utc)

    db.commit()

    await manager.broadcast({
        "type": "deployment_updated",
        "data": {
            "id": deployment.id,
            "status": deployment.status,
        }
    })

    return {"status": "updated"}

# Dashboard endpoints
@app.get("/api/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics."""
    total_agents = db.query(Agent).count()
    online_agents = db.query(Agent).filter(Agent.status == "online").count()
    offline_agents = db.query(Agent).filter(Agent.status == "offline").count()

    total_deployments = db.query(Deployment).count()
    successful_deployments = db.query(Deployment).filter(Deployment.status == "success").count()
    failed_deployments = db.query(Deployment).filter(Deployment.status == "failed").count()

    return DashboardStats(
        total_agents=total_agents,
        online_agents=online_agents,
        offline_agents=offline_agents,
        total_deployments=total_deployments,
        successful_deployments=successful_deployments,
        failed_deployments=failed_deployments,
    )

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back for keepalive
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics(db: Session = Depends(get_db)):
    """Prometheus metrics endpoint."""
    total_agents = db.query(Agent).count()
    online_agents = db.query(Agent).filter(Agent.status == "online").count()
    total_deployments = db.query(Deployment).count()

    metrics_text = f"""# HELP substrate_agents_total Total number of registered agents
# TYPE substrate_agents_total gauge
substrate_agents_total {total_agents}

# HELP substrate_agents_online Number of online agents
# TYPE substrate_agents_online gauge
substrate_agents_online {online_agents}

# HELP substrate_deployments_total Total number of deployments
# TYPE substrate_deployments_total counter
substrate_deployments_total {total_deployments}
"""
    return metrics_text

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
