#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: container-run.sh [policy options] IMAGE [COMMAND...]

Run a rootless development container with workstation-safe defaults.

Policy options:
  --cpu N          CPU quota (default: 8)
  --memory SIZE    memory limit (default: 16g)
  --pids N         process limit (default: 4096)
  --network MODE   network mode (default: pasta; use none for offline builds)
  --kvm            pass /dev/kvm to the container
  --workspace DIR  mount DIR at /workspace with rw access
  --name NAME      assign a stable container name
  --               end policy options
EOF
}

cpus=8
memory=16g
pids=4096
network=pasta
kvm=false
workspace=
name=

while (($#)); do
  case "$1" in
    --cpu) cpus="${2:?missing CPU count}"; shift 2 ;;
    --memory) memory="${2:?missing memory limit}"; shift 2 ;;
    --pids) pids="${2:?missing PID limit}"; shift 2 ;;
    --network) network="${2:?missing network mode}"; shift 2 ;;
    --kvm) kvm=true; shift ;;
    --workspace) workspace="${2:?missing workspace path}"; shift 2 ;;
    --name) name="${2:?missing name}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    --) shift; break ;;
    -*) printf 'unknown policy option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *) break ;;
  esac
done

(($#)) || { usage >&2; exit 2; }
[[ "$cpus" =~ ^([1-9]|1[0-6])$ ]] ||
  { printf 'CPU limit must be between 1 and 16\n' >&2; exit 2; }
[[ "$pids" =~ ^[1-9][0-9]*$ ]] ||
  { printf 'PID limit must be a positive integer\n' >&2; exit 2; }

args=(run --rm --cpus "$cpus" --memory "$memory" --pids-limit "$pids"
      --network "$network" --security-opt no-new-privileges)

if $kvm; then
  [[ -r /dev/kvm && -w /dev/kvm ]] ||
    { printf '/dev/kvm is not accessible\n' >&2; exit 1; }
  args+=(--device /dev/kvm)
fi

if [[ -n "$workspace" ]]; then
  workspace="$(realpath -e "$workspace")"
  [[ -d "$workspace" ]] ||
    { printf 'workspace is not a directory: %s\n' "$workspace" >&2; exit 2; }
  args+=(--volume "$workspace:/workspace:rw")
fi

[[ -z "$name" ]] || args+=(--name "$name")
exec podman "${args[@]}" "$@"

