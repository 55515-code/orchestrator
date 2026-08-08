#!/usr/bin/env bash
set -euo pipefail

failures=0
warnings=0

pass() { printf 'PASS  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL  %s\n' "$*"; failures=$((failures + 1)); }

command -v podman >/dev/null && pass "Podman is installed" || fail "Podman is missing"
test -r /dev/kvm && test -w /dev/kvm &&
  pass "KVM is accessible to the current user" ||
  fail "/dev/kvm is not read/write accessible"
test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs &&
  pass "cgroup v2 is active" ||
  fail "cgroup v2 is not active"
test "$(sysctl -n kernel.unprivileged_userns_clone 2>/dev/null)" = 1 &&
  pass "unprivileged user namespaces are enabled" ||
  fail "unprivileged user namespaces are disabled"
test -r /dev/net/tun && test -w /dev/net/tun &&
  pass "TUN networking is accessible" ||
  fail "/dev/net/tun is not accessible"

if swapon --noheadings --show=NAME 2>/dev/null | grep -qx '/dev/zram0'; then
  pass "zram swap is active"
else
  warn "zram swap is not active"
fi

if compgen -G '/dev/dri/renderD*' >/dev/null; then
  pass "GPU render nodes are available for accelerated containers/emulators"
else
  warn "no GPU render node is available"
fi

if systemctl --user is-active --quiet podman.socket; then
  pass "Podman user API socket is active"
else
  warn "Podman user API socket is inactive"
fi

if command -v qemu-system-x86_64 >/dev/null; then
  pass "host QEMU is installed"
else
  warn "host QEMU is not installed (containerized QEMU may still work)"
fi

if command -v virsh >/dev/null; then
  pass "libvirt client is installed"
  if virsh --connect qemu:///session uri >/dev/null 2>&1; then
    pass "rootless user-session libvirt connection works"
  else
    fail "rootless user-session libvirt connection is unavailable"
  fi
  if virsh --connect qemu:///system uri >/dev/null 2>&1 ||
     { getent group libvirt | grep -qE "(^|,)$USER(,|$)" &&
       sg libvirt -c 'virsh --connect qemu:///system uri' >/dev/null 2>&1; }; then
    pass "system libvirt QEMU connection works"
  else
    warn "system libvirt QEMU connection is unavailable"
  fi
else
  warn "libvirt client is not installed"
fi

command -v swtpm >/dev/null &&
  pass "software TPM emulator is installed" ||
  warn "software TPM emulator is not installed"

if compgen -G '/usr/share/edk2/x64/*OVMF*' >/dev/null ||
   compgen -G '/usr/share/edk2-ovmf/*' >/dev/null; then
  pass "OVMF UEFI firmware is installed"
else
  warn "OVMF UEFI firmware was not found"
fi

available_kib="$(df --output=avail / | tail -n 1 | tr -d ' ')"
if (( available_kib >= 104857600 )); then
  pass "root filesystem has at least 100 GiB available"
else
  warn "root filesystem has less than 100 GiB available: $((available_kib / 1048576)) GiB"
fi

if git_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  git_dir="$git_root/.git"
  if [[ -d "$git_dir/objects/pack" ]]; then
    read -r temp_count temp_bytes < <(
      find "$git_dir/objects/pack" -maxdepth 1 -type f -name 'tmp_pack_*' \
        -printf '%s\n' |
        awk '{count += 1; bytes += $1} END {print count + 0, bytes + 0}'
    )
    if (( temp_bytes >= 1073741824 )); then
      warn "Git has $temp_count temporary pack files using $((temp_bytes / 1073741824)) GiB"
    elif (( temp_count > 0 )); then
      warn "Git has $temp_count temporary pack files"
    else
      pass "Git has no abandoned temporary pack files"
    fi
  fi
fi

if pgrep -af 'git .* (add|gc|repack|pack-objects|index-pack)' >/dev/null; then
  warn "a Git write/packing process is active; do not run cleanup"
fi

if command -v podman >/dev/null; then
  if command -v jq >/dev/null; then
    podman info --format json |
      jq -r '"INFO  Podman rootless=\(.host.security.rootless) cgroups=\(.host.cgroupVersion) runtime=\(.host.ociRuntime.name) network=\(.host.networkBackend)"'
    driver="$(podman info --format json | jq -r '.store.graphDriverName')"
    [[ "$driver" == overlay ]] &&
      pass "Podman uses the overlay storage driver" ||
      warn "Podman storage driver is $driver, not overlay"
  else
    podman info --format 'INFO  Podman rootless={{.Host.Security.Rootless}} runtime={{.Host.OCIRuntime.Name}}'
  fi
  podman system df
fi

printf 'SUMMARY failures=%d warnings=%d\n' "$failures" "$warnings"
(( failures == 0 ))
