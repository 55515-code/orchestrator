#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/compose.yaml"
SERVICE_NAME="substrate-ops"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8090}"
BASE_URL="http://${HOST}:${PORT}"

choose_compose() {
  if command -v docker >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  if command -v podman >/dev/null 2>&1; then
    echo "podman compose"
    return 0
  fi
  return 1
}

run_compose() {
  local compose_cmd="$1"
  shift
  # shellcheck disable=SC2086
  ${compose_cmd} -f "${COMPOSE_FILE}" "$@"
}

wait_for_health() {
  local max_attempts=45
  local attempt=1
  while [[ "${attempt}" -le "${max_attempts}" ]]; do
    local code
    code="$(curl -sS -o /dev/null -w "%{http_code}" "${BASE_URL}/healthz" || true)"
    if [[ "${code}" == "200" ]]; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

main() {
  local action="${1:-up}"
  local compose_cmd
  if ! compose_cmd="$(choose_compose)"; then
    echo "No supported container runtime found (docker/docker-compose/podman)." >&2
    exit 1
  fi

  case "${action}" in
    up)
      run_compose "${compose_cmd}" up --build -d
      if ! wait_for_health; then
        echo "Container did not become healthy at ${BASE_URL}/healthz" >&2
        run_compose "${compose_cmd}" logs --tail 80 "${SERVICE_NAME}" || true
        exit 1
      fi
      curl -fsS "${BASE_URL}/healthz" >/dev/null
      curl -fsS "${BASE_URL}/api/connection/status" >/dev/null
      echo "Container is up: ${BASE_URL}"
      echo "Smoke checks passed: /healthz and /api/connection/status"
      ;;
    down)
      run_compose "${compose_cmd}" down
      ;;
    logs)
      run_compose "${compose_cmd}" logs -f "${SERVICE_NAME}"
      ;;
    *)
      echo "Usage: $0 [up|down|logs]" >&2
      exit 2
      ;;
  esac
}

main "$@"
