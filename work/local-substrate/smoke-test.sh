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

check "shell syntax" bash -n \
  "$root/audit.sh" "$root/bootstrap-cachyos.sh" "$root/container-run.sh"
check "Podman API socket" curl --fail --silent --show-error \
  --unix-socket "$XDG_RUNTIME_DIR/podman/podman.sock" \
  http://podman/v5.0.0/libpod/_ping
check "constrained offline container" \
  "$root/container-run.sh" --cpu 1 --memory 256m --pids 64 \
  --network none docker.io/library/ubuntu:24.04 \
  sh -c 'test -r /etc/os-release &&
         test "$(cat /sys/fs/cgroup/memory.max)" = 268435456 &&
         test "$(cat /sys/fs/cgroup/cpu.max)" = "100000 100000"'

if command -v qemu-system-x86_64 >/dev/null; then
  check "host QEMU executes with KVM acceleration" \
    bash -c '
      status=0
      timeout --signal=TERM 2 \
        qemu-system-x86_64 \
          -machine q35,accel=kvm \
          -cpu host \
          -nodefaults \
          -display none \
          -S || status=$?
      test "$status" -eq 124
    '
else
  printf 'SKIP  host QEMU smoke test (not installed)\n'
fi

printf 'SUMMARY failures=%d\n' "$failures"
(( failures == 0 ))
