#!/bin/bash
# Single-command launcher for Substrate Deploy System

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
}

# Build the Docker image
build() {
    log_info "Building Docker image..."
    cd "$PROJECT_DIR"
    docker build -f docker/Dockerfile -t substrate-deploy-system:latest .
    log_info "Build complete!"
}

# Start the control panel
start() {
    check_docker
    log_info "Starting Substrate Deploy Control Panel..."

    cd "$PROJECT_DIR/docker"

    # Generate secret key if not set
    if [ -z "$SECRET_KEY" ]; then
        export SECRET_KEY=$(openssl rand -hex 32)
        log_warn "Generated random SECRET_KEY. Set SECRET_KEY environment variable for production."
    fi

    docker-compose up -d

    log_info "Control Panel started successfully!"
    log_info "Access the dashboard at: http://localhost:8080"
    log_info "API documentation at: http://localhost:8080/docs"
}

# Stop the control panel
stop() {
    check_docker
    log_info "Stopping Substrate Deploy Control Panel..."

    cd "$PROJECT_DIR/docker"
    docker-compose down

    log_info "Control Panel stopped."
}

# Show logs
logs() {
    check_docker
    cd "$PROJECT_DIR/docker"
    docker-compose logs -f
}

# Register a new agent
register_agent() {
    local agent_name=$1

    if [ -z "$agent_name" ]; then
        log_error "Usage: $0 register-agent <agent-name>"
        exit 1
    fi

    log_info "Registering agent: $agent_name"

    # Get API key from control panel
    response=$(curl -s -X POST http://localhost:8080/api/agents \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$agent_name\"}")

    agent_id=$(echo $response | jq -r '.id')
    api_key=$(echo $response | jq -r '.api_key')

    if [ "$agent_id" = "null" ]; then
        log_error "Failed to register agent"
        exit 1
    fi

    log_info "Agent registered successfully!"
    log_info "Agent ID: $agent_id"
    log_info "API Key: $api_key"
    log_info ""
    log_info "To start the agent on a target machine:"
    log_info "  python agent/agent.py --control-panel-url http://YOUR_CONTROL_PANEL:8080"
    log_info "  The agent will register itself on first run."
}

# Deploy to an agent
deploy() {
    local agent_id=$1
    local version=$2
    local files_url=$3

    if [ -z "$agent_id" ] || [ -z "$version" ] || [ -z "$files_url" ]; then
        log_error "Usage: $0 deploy <agent-id> <version> <files-url>"
        exit 1
    fi

    log_info "Deploying version $version to agent $agent_id"

    response=$(curl -s -X POST http://localhost:8080/api/deployments \
        -H "Content-Type: application/json" \
        -d "{
            \"agent_id\": \"$agent_id\",
            \"version\": \"$version\",
            \"files_url\": \"$files_url\"
        }")

    deployment_id=$(echo $response | jq -r '.id')

    if [ "$deployment_id" = "null" ]; then
        log_error "Failed to create deployment"
        exit 1
    fi

    log_info "Deployment created: $deployment_id"
    log_info "Status: $(echo $response | jq -r '.status')"
}

# Show status
status() {
    check_docker
    cd "$PROJECT_DIR/docker"

    log_info "Container Status:"
    docker-compose ps

    echo ""
    log_info "Agent Status:"
    curl -s http://localhost:8080/api/agents | jq -r '.[] | "\(.name): \(.status) (last seen: \(.last_heartbeat // "never"))"'
}

# Run tests
test() {
    log_info "Running tests..."
    cd "$PROJECT_DIR"
    python -m pytest tests/ -v
}

# Show help
help() {
    echo "Substrate Deploy System Launcher"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start                    Start the control panel"
    echo "  stop                     Stop the control panel"
    echo "  build                    Build the Docker image"
    echo "  logs                     Show container logs"
    echo "  status                   Show system status"
    echo "  register-agent <name>    Register a new agent"
    echo "  deploy <id> <ver> <url>  Deploy to an agent"
    echo "  test                     Run tests"
    echo "  help                     Show this help message"
    echo ""
}

# Main command router
case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    build)
        build
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    register-agent)
        register_agent "$2"
        ;;
    deploy)
        deploy "$2" "$3" "$4"
        ;;
    test)
        test
        ;;
    help|--help|-h)
        help
        ;;
    *)
        help
        exit 1
        ;;
esac
