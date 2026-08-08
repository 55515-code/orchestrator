#!/usr/bin/env bash
# run.sh — execute a pre-defined action by name.
# Source of truth: actions.json (versioned in ~/codespace/automation).
# Usage:
#   run.sh                          # list available actions
#   run.sh <action_name>            # run an action
#   run.sh agent_session "prompt"   # run the agent_session action with %PROMPT% substituted
#   run.sh --which <name>           # print the resolved command + cwd, don't run

set -euo pipefail

ACTION_FILE="$(cd "$(dirname "$0")" && pwd)/actions.json"

if [ ! -f "$ACTION_FILE" ]; then
  echo "actions.json not found: $ACTION_FILE" >&2
  exit 1
fi

list_actions() {
  jq -r '.actions | to_entries[] | "  \(.key) — \(.value.description)"' "$ACTION_FILE"
}

resolve() {
  local name="$1"
  local cmd cwd
  cmd=$(jq -r --arg n "$name" '.actions[$n].command // ""' "$ACTION_FILE")
  cwd=$(jq -r --arg n "$name" '.actions[$n].cwd // ""' "$ACTION_FILE")
  if [ -z "$cmd" ]; then
    echo "Unknown action: $name" >&2
    echo "Available actions:" >&2
    list_actions >&2
    exit 3
  fi
  if [ -n "$cwd" ] && [ "$cwd" != "." ]; then
    echo "cd $cwd && $cmd"
  else
    echo "$cmd"
  fi
}

if [ $# -eq 0 ]; then
  echo "Available actions (from $ACTION_FILE):" >&2
  list_actions >&2
  exit 0
fi

NAME="$1"
shift || true

if [ "$NAME" = "--which" ]; then
  resolve "$1"
  exit $?
fi

CMD=$(jq -r --arg n "$NAME" '.actions[$n].command // ""' "$ACTION_FILE")
CWD=$(jq -r --arg n "$NAME" '.actions[$n].cwd // ""' "$ACTION_FILE")

if [ -z "$CMD" ]; then
  echo "Unknown action: $NAME" >&2
  echo "Available actions:" >&2
  list_actions >&2
  exit 3
fi

# Substitute %PROMPT% with a positional parameter reference ($1). The prompt is
# passed to bash -c as a separate argument, so it can never be interpreted as
# shell code (defeats command injection via %PROMPT%).
if [[ "$CMD" == *"%PROMPT%"* ]]; then
  PROMPT="$*"
  CMD=$(printf '%s' "$CMD" | sed 's/"%PROMPT%"/"$1"/g; s/%PROMPT%/$1/g')
  HAS_PROMPT=1
fi

if [ -n "$CWD" ] && [ "$CWD" != "." ]; then
  cd "$CWD"
fi

echo "+ $CMD" >&2
if [ "${HAS_PROMPT:-0}" = "1" ]; then
  exec bash -c "$CMD" bash "$PROMPT"
else
  exec bash -c "$CMD"
fi
