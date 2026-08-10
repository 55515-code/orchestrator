#!/bin/bash

# Substrate Autonomous Git Sync Daemon
# Automates repository initialization, staging, committing, and pushing.
# Designed to run alongside other daemon loops without conflicts.
#
# Safety: runs a secret scan before committing and refuses to push if the
# scan fails. Ignores directories listed in .gitignore (e.g. .kilo/).

set -e

# Configuration
WORKSPACE_DIR="/home/ahron/codespace"
LOG_DIR="${WORKSPACE_DIR}/memory/community-sim/logs"
LOG_FILE="${LOG_DIR}/git_sync_$(date +%Y%m%d).log"
BRANCH_NAME="${GIT_SYNC_BRANCH:-$(git -C "$WORKSPACE_DIR" branch --show-current 2>/dev/null || echo main)}"

mkdir -p "$LOG_DIR"

# Redirect output
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting Git Sync execution..."

cd "$WORKSPACE_DIR"

# 1. Stale Lock Cleanup
if [ -f ".git/index.lock" ]; then
    # Check if a git process is actually running
    if ! pgrep -x "git" > /dev/null; then
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Found stale .git/index.lock with no active git process. Removing..."
        rm -f .git/index.lock
    else
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Git process is currently running. Yielding this sync cycle."
        exit 0
    fi
fi

# 2. Repository Initialization
if [ ! -d ".git" ]; then
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] No .git directory found. Initializing repository..."
    git init
    git checkout -b "$BRANCH_NAME" || true
    
    # Configure local bot identity if not set globally
    if ! git config user.name > /dev/null; then
        git config user.name "Substrate Auto-Sync Bot"
        git config user.email "bot@substrate.local"
    fi
fi

# 3. Remote Configuration
# If GIT_REMOTE_URL is set in environment, ensure origin matches it
if [ -n "$GIT_REMOTE_URL" ]; then
    if git remote | grep -q "^origin$"; then
        CURRENT_REMOTE=$(git remote get-url origin)
        if [ "$CURRENT_REMOTE" != "$GIT_REMOTE_URL" ]; then
            echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Updating remote origin to $GIT_REMOTE_URL"
            git remote set-url origin "$GIT_REMOTE_URL"
        fi
    else
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Adding remote origin $GIT_REMOTE_URL"
        git remote add origin "$GIT_REMOTE_URL"
    fi
fi

# 4. Stage and Commit
git add -A

# 4a. Secret scan gate — refuse to commit if secret-like material is staged
if ! bash scripts/scan_secrets.sh "$WORKSPACE_DIR"; then
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] SECRET SCAN BLOCKED COMMIT. Unstaging and aborting sync."
    git reset 2>/dev/null || true
    exit 1
fi

# Check if there are any changes to commit
if git diff --staged --quiet; then
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] No changes to commit. Workspace is clean."
else
    COMMIT_MSG="auto-sync: autonomous workspace checkpoint $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Committing changes: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG"
fi

# 5. Pull (Rebase) and Push
if git remote | grep -q "^origin$"; then
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Synchronizing with remote..."
    
    # Fetch latest
    git fetch origin "$BRANCH_NAME" || true
    
    # Check if remote branch exists before pulling/rebasing
    if git ls-remote --heads origin "$BRANCH_NAME" | grep -q "$BRANCH_NAME"; then
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Pulling latest changes via rebase..."
        git pull --rebase origin "$BRANCH_NAME" || {
            echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Rebase conflict detected! Aborting rebase to protect workspace."
            git rebase --abort
            exit 1
        }
    fi
    
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Pushing to origin..."
    git push origin HEAD:"$BRANCH_NAME" || echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Push failed, will retry next cycle."
else
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] No 'origin' remote configured. Skipping network sync."
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Git Sync execution completed."
