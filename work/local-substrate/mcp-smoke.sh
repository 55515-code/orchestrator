#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
response="$(mktemp)"
errors="$(mktemp)"
trap 'rm -f "$response" "$errors"' EXIT

request='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"fabric-smoke","version":"1.0"}}}'

printf '%s\n' "$request" |
  timeout 60 "$root/fabric.py" mcp-run context7 >"$response" 2>"$errors"

jq -e '
  .id == 1 and
  .result.protocolVersion == "2025-06-18" and
  .result.serverInfo.name == "Context7" and
  .result.capabilities.tools
' "$response" >/dev/null

printf 'PASS  containerized Context7 MCP initialize handshake\n'
