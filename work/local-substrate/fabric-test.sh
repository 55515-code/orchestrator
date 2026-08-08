#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failures=0

check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label" >&2
    failures=$((failures + 1))
  fi
}

check "fabric Python syntax" python -m py_compile "$root/fabric.py"
check "fabric JSON syntax" python -m json.tool "$root/fabric.json"
check "fabric status" "$root/fabric.py" status
check "project discovery is bounded" bash -c \
  'count="$("$1" projects | jq length)"; ((count >= 5 && count <= 30))' \
  _ "$root/fabric.py"
check "local resource-scoped dispatch" \
  "$root/fabric.py" run --profile local-light --workspace "$root" \
  -- sh -c 'test "$PWD" = /home/ahron/codespace/work/local-substrate'
check "container dispatch plan" bash -c \
  '"$1" run --profile container-ubuntu --workspace "$2" --dry-run -- true |
   jq -e ".[0] | endswith(\"container-run.sh\")" >/dev/null' \
  _ "$root/fabric.py" "$root"
check "project-name dispatch selects override" bash -c \
  '"$1" run --project LuigiOS --dry-run -- true |
   jq -e "index(\"--kvm\") != null" >/dev/null' \
  _ "$root/fabric.py"
check "rootless VM default" bash -c \
  'test "$(virsh uri)" = qemu:///session'
check "MCP client routes through fabric" jq -e \
  '.mcpServers.context7.command |
   endswith("/work/local-substrate/fabric.py")' \
  /home/ahron/codespace/.roo/mcp.json
check "containerized MCP handshake" "$root/mcp-smoke.sh"

printf 'SUMMARY failures=%d\n' "$failures"
((failures == 0))
