# Substrate Deploy System Architecture

## Overview

A production-grade, containerized deployment system consisting of:
1. **Control Panel** - Centralized web dashboard for monitoring and management
2. **Deployer Agent** - Lightweight agent for endpoint deployment and management

## System Components

### Control Panel
- **Backend**: FastAPI with SQLAlchemy ORM
- **Frontend**: React with TypeScript (Vite build)
- **Database**: SQLite (portable, no external dependencies)
- **Real-time**: WebSocket for live updates
- **Metrics**: Prometheus endpoint
- **Authentication**: JWT-based with API keys

### Deployer Agent
- **Runtime**: Python 3.12+ (minimal dependencies)
- **Installation**: User-space (~/.substrate-agent/)
- **Communication**: HTTP REST API + WebSocket
- **Features**:
  - File synchronization
  - Status reporting
  - Heartbeat mechanism
  - Self-update capability
  - Health checks

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Control Panel                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Frontend   │  │   Backend    │  │  Database    │ │
│  │   (React)    │◄─┤  (FastAPI)   │◄─┤  (SQLite)    │ │
│  └──────────────┘  └──────┬───────┘  └──────────────┘ │
│                           │                             │
│                    ┌──────┴───────┐                     │
│                    │  WebSocket   │                     │
│                    │   Server     │                     │
│                    └──────────────┘                     │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP/WebSocket
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
┌───────▼────────┐ ┌──────▼───────┐ ┌──────▼───────┐
│   Endpoint 1   │ │  Endpoint 2  │ │  Endpoint N  │
│  ┌──────────┐  │ │ ┌──────────┐ │ │ ┌──────────┐ │
│  │  Agent   │  │ │ │  Agent   │ │ │ │  Agent   │ │
│  └──────────┘  │ │ └──────────┘ │ │ └──────────┘ │
└────────────────┘ └──────────────┘ └──────────────┘
```

## Data Flow

1. **Deployment**:
   - Control Panel packages application files
   - Agent downloads and extracts to user-space
   - Agent reports deployment status

2. **Monitoring**:
   - Agents send heartbeats every 30s
   - Control Panel aggregates status
   - Frontend displays real-time dashboard

3. **Updates**:
   - Control Panel detects new versions
   - Agents pull updates automatically
   - Rollback capability on failure

## Security Model

- JWT tokens for API authentication
- API keys for agent registration
- TLS encryption for all communications
- Sandboxed agent execution
- Audit logging for all operations

## Deployment Modes

1. **Single Container**: All-in-one for development
2. **Distributed**: Separate containers for panel and agents
3. **Bare Metal**: Direct installation on target machines
