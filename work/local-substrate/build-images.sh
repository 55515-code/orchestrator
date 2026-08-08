#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

podman build \
  --pull=never \
  --tag localhost/local-substrate-toolbox:2026.07 \
  --file "$root/Containerfile.toolbox" \
  "$root"

podman image inspect localhost/local-substrate-toolbox:2026.07 \
  --format 'Built {{.Id}} ({{.Size}} bytes)'
