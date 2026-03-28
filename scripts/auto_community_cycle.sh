#!/bin/bash

# Auto Community Cycle Wrapper Script
# Handles configuration verification, execution, and logging.

set -e

# Configuration
WORKSPACE_DIR="/home/ahron/codespace"
LOG_DIR="${WORKSPACE_DIR}/memory/community-sim/logs"
LOG_FILE="${LOG_DIR}/auto_cycle_$(date +%Y%m%d_%H%M%S).log"
WORKSPACE_YAML="${WORKSPACE_DIR}/workspace.yaml"

mkdir -p "$LOG_DIR"

# Redirect all output to log file and terminal
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting Auto Community Cycle Initialization..."

# 2. Verify workspace.yaml is in mutate mode
echo "Verifying workspace.yaml configuration..."
if grep -q "default_mode: mutate" "$WORKSPACE_YAML" && grep -q "allow_mutations: true" "$WORKSPACE_YAML"; then
    echo "workspace.yaml is properly configured for mutation."
else
    echo "WARNING: workspace.yaml is not fully set to mutate mode. Attempting automatic correction..."
    # Simple inline replacement for known patterns
    sed -i 's/default_mode: observe/default_mode: mutate/g' "$WORKSPACE_YAML"
    sed -i 's/allow_mutations: false/allow_mutations: true/g' "$WORKSPACE_YAML"
    echo "workspace.yaml updated."
fi

# 3. Execution with Error Recovery Loop
CYCLE_NUM=2
MAX_RETRIES=3
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Executing Community Cycle $CYCLE_NUM (Attempt $((RETRY_COUNT+1))/$MAX_RETRIES)..."
    
    cd "$WORKSPACE_DIR"
    
    # Run the cycle
    if uv run python scripts/substrate_cli.py community-cycle \
        --cycle $CYCLE_NUM \
        --repo substrate-core \
        --stage local \
        --concurrency-limit 5 \
        --agent-provider local \
        --agent-model roo-router; then
        
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Community Cycle $CYCLE_NUM completed successfully."
        
        # Generate status page after successful run
        echo "Generating project status page..."
        if [ -f "scripts/generate_status_page.py" ]; then
            uv run python scripts/generate_status_page.py || echo "Status page generation failed, but cycle succeeded."
        fi
        
        exit 0
    else
        EXIT_CODE=$?
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] ERROR: Community Cycle failed with exit code $EXIT_CODE."
        RETRY_COUNT=$((RETRY_COUNT+1))
        
        if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
            echo "Waiting 60 seconds before retrying..."
            sleep 60
        else
            echo "Max retries reached. Aborting automated execution."
            exit 1
        fi
    fi
done
