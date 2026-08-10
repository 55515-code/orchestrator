#!/bin/bash

# Substrate Autonomous Orchestrator Daemon
# Wraps the auto_community_cycle.sh in a continuous respawn loop

WORKSPACE_DIR="/home/ahron/codespace"
DAEMON_LOG="${WORKSPACE_DIR}/memory/community-sim/logs/daemon_stdout_stderr.log"

mkdir -p "${WORKSPACE_DIR}/memory/community-sim/logs"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting Substrate Orchestrator Daemon..." >> "$DAEMON_LOG"

while true; do
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Spawning auto_community_cycle.sh..." >> "$DAEMON_LOG"
    
    bash "${WORKSPACE_DIR}/scripts/auto_community_cycle.sh" >> "$DAEMON_LOG" 2>&1
    EXIT_CODE=$?
    
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Spawning auto_git_sync.sh for workspace backup..." >> "$DAEMON_LOG"
    bash "${WORKSPACE_DIR}/scripts/auto_git_sync.sh" >> "$DAEMON_LOG" 2>&1
    
    if [ $EXIT_CODE -ne 0 ]; then
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] WARNING: auto_community_cycle.sh exited with failure code $EXIT_CODE." >> "$DAEMON_LOG"
        echo "Crash recovered. Waiting 60 seconds before daemon restart..." >> "$DAEMON_LOG"
        sleep 60
    else
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] SUCCESS: auto_community_cycle.sh completed gracefully." >> "$DAEMON_LOG"
        echo "Waiting 30 seconds before next continuous cycle..." >> "$DAEMON_LOG"
        sleep 30
    fi
done