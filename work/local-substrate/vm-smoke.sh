#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

virsh --connect qemu:///session dominfo fabric-ubuntu >/dev/null
"$root/fabric.py" run \
  --profile vm-rootless \
  --workspace "$root" \
  -- sh -c '
    test -f fabric.py
    test "$(nproc)" -eq 8
    command -v podman >/dev/null
    command -v git >/dev/null
    command -v gcc >/dev/null
    command -v python3 >/dev/null
    test -f /var/lib/cloud/instance/fabric-ready
  '

printf 'PASS  rootless VM lifecycle and guest command dispatch\n'
