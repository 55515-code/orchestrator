#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config="$root/fabric.json"
initial_vm_state="$(virsh --connect qemu:///session domstate fabric-ubuntu 2>/dev/null || true)"

cleanup() {
  if [[ "$initial_vm_state" == "shut off" ]] &&
     [[ "$(virsh --connect qemu:///session domstate fabric-ubuntu 2>/dev/null || true)" == "running" ]]; then
    virsh --connect qemu:///session shutdown fabric-ubuntu >/dev/null
  fi
}
trap cleanup EXIT

"$root/audit.sh"
"$root/smoke-test.sh"
"$root/fabric-test.sh"
"$root/vm-smoke.sh"

jq -e '
  [
    .profiles[],
    .mcps[]
    | select(.backend == "container")
    | .image
    | select(startswith("docker.io/") or startswith("quay.io/") or startswith("ghcr.io/"))
    | contains("@sha256:")
  ] | all
' "$config" >/dev/null
printf 'PASS  all remote runtime images are digest pinned\n'

jq -e '
  .mcps
  | to_entries
  | all(.value.command | any(test("@[0-9]+([.][0-9]+)+$")))
' "$config" >/dev/null
printf 'PASS  MCP package commands are version pinned\n'

"$root/fabric.py" run \
  --profile container-ubuntu \
  --workspace "$root" \
  -- sh -c '
    for tool in python3 git gcc make jq curl rsync ssh; do
      command -v "$tool" >/dev/null || exit 1
    done
    test "$(cat /sys/fs/cgroup/memory.max)" = 17179869184
  '
printf 'PASS  general toolbox is usable and memory constrained\n'

"$root/fabric.py" status
printf 'SUMMARY failures=0\n'
