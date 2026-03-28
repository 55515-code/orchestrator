#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP_UTC="$(date -u +"%Y%m%d-%H%M%SZ")"
LOG_DIR="$ROOT_DIR/memory/task-runs"
LOG_FILE="$LOG_DIR/${TIMESTAMP_UTC}-developer-polish.log"
FAILED_STEP=""
HAS_GIT_REPO="false"
RUFF_TARGETS=(
  substrate
  scripts/run_chain.py
  scripts/package_substrate.py
  scripts/probe_system.py
)

mkdir -p "$LOG_DIR"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  HAS_GIT_REPO="true"
fi

git_status_snapshot() {
  if [[ "$HAS_GIT_REPO" == "true" ]]; then
    git status --short || true
  else
    echo "(workspace is not a git repository)"
  fi
}

git_changed_files_snapshot() {
  if [[ "$HAS_GIT_REPO" == "true" ]]; then
    git diff --name-only || true
  else
    echo "(workspace is not a git repository)"
  fi
}

append_footer() {
  local exit_code="$1"
  {
    echo
    echo "## Result"
    if [[ "$exit_code" -eq 0 ]]; then
      echo "status: success"
    else
      echo "status: failed"
      if [[ -n "$FAILED_STEP" ]]; then
        echo "failed_step: $FAILED_STEP"
      fi
    fi
    echo "finished_utc: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo
    echo "## Git Status (after)"
    git_status_snapshot
    echo
    echo "## Changed Files"
    git_changed_files_snapshot
  } >>"$LOG_FILE"
}

trap 'exit_code=$?; append_footer "$exit_code"; exit "$exit_code"' EXIT

{
  echo "# Developer Polish Run"
  echo "started_utc: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "workspace: $ROOT_DIR"
  echo
  echo "## Git Status (before)"
  git_status_snapshot
} >"$LOG_FILE"

run_step() {
  local step_name="$1"
  shift
  {
    echo
    echo "## ${step_name}"
    printf '$'
    printf ' %q' "$@"
    echo
  } >>"$LOG_FILE"

  if "$@" >>"$LOG_FILE" 2>&1; then
    echo "status: success" >>"$LOG_FILE"
    return 0
  else
    local exit_code="$?"
    FAILED_STEP="$step_name"
    echo "status: failed (exit_code=${exit_code})" >>"$LOG_FILE"
    return "$exit_code"
  fi
}

scan_voice_markers() {
  local pattern='(as an ai|language model|chatgpt)'
  local output
  local exit_code

  {
    echo
    echo "## Team Voice Marker Scan"
    echo "pattern: ${pattern}"
  } >>"$LOG_FILE"

  set +e
  output="$(rg -n -i "$pattern" README.md CONTRIBUTING.md docs substrate 2>&1)"
  exit_code="$?"
  set -e

  if [[ "$exit_code" -eq 1 ]]; then
    echo "status: success (no markers found)" >>"$LOG_FILE"
    return 0
  fi

  if [[ "$exit_code" -eq 0 ]]; then
    FAILED_STEP="Team Voice Marker Scan"
    {
      echo "status: failed (markers found)"
      echo "$output"
    } >>"$LOG_FILE"
    return 1
  fi

  FAILED_STEP="Team Voice Marker Scan"
  {
    echo "status: failed (rg exit_code=${exit_code})"
    echo "$output"
  } >>"$LOG_FILE"
  return "$exit_code"
}

run_step "Repository Scan" uv run python scripts/substrate_cli.py scan
run_step "Lint Check" uv run --with ruff ruff check "${RUFF_TARGETS[@]}"
run_step "Format Check" uv run --with ruff ruff format --check "${RUFF_TARGETS[@]}"
run_step "Compile Smoke Test" env PYTHONDONTWRITEBYTECODE=1 uv run python -m compileall substrate scripts
scan_voice_markers

echo "developer_polish_log=$LOG_FILE"
