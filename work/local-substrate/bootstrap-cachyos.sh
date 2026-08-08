#!/usr/bin/env bash
set -euo pipefail

apply=false
target_user="${SUDO_USER:-${USER:-}}"
while (($#)); do
  case "$1" in
    --apply) apply=true; shift ;;
    --target-user)
      target_user="${2:?missing target user}"
      shift 2
      ;;
    *)
      printf 'usage: %s [--apply] [--target-user USER]\n' "$0" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$target_user" ]] && [[ -n "${PKEXEC_UID:-}" ]]; then
  target_user="$(getent passwd "$PKEXEC_UID" | cut -d: -f1)"
fi
if ! id "$target_user" >/dev/null 2>&1; then
  printf 'Target user does not exist: %s\n' "$target_user" >&2
  exit 1
fi

packages=(
  podman buildah skopeo podman-compose
  qemu-full libvirt virt-manager virt-install virt-viewer
  dnsmasq edk2-ovmf swtpm
)

printf 'Planned packages:\n'
printf '  %s\n' "${packages[@]}"
printf '\nPlanned services:\n'
printf '  user: podman.socket\n'
printf '  system: virtqemud.socket virtnetworkd.socket virtstoraged.socket\n'
printf '\nPlanned group membership: libvirt\n'

if ! $apply; then
  printf '\nDry run only. Re-run with --apply from an interactive terminal.\n'
  exit 0
fi

if [[ "${ID:-}" != "cachyos" ]] && ! grep -qE '^ID=(cachyos|arch)$' /etc/os-release; then
  printf 'This bootstrap supports CachyOS/Arch only.\n' >&2
  exit 1
fi

if ((EUID == 0)); then
  as_root=()
else
  as_root=(sudo)
fi

"${as_root[@]}" pacman -S --needed --noconfirm "${packages[@]}"
"${as_root[@]}" usermod -aG libvirt "$target_user"
"${as_root[@]}" systemctl enable --now \
  virtqemud.socket virtnetworkd.socket virtstoraged.socket
if [[ "$target_user" == "${USER:-}" ]] && ((EUID != 0)); then
  systemctl --user enable --now podman.socket
fi

if "${as_root[@]}" virsh net-info default >/dev/null 2>&1; then
  "${as_root[@]}" virsh net-autostart default
  "${as_root[@]}" virsh net-start default 2>/dev/null || true
elif [[ -r /usr/share/libvirt/networks/default.xml ]]; then
  "${as_root[@]}" virsh net-define /usr/share/libvirt/networks/default.xml
  "${as_root[@]}" virsh net-autostart default
  "${as_root[@]}" virsh net-start default
else
  printf 'Default libvirt network XML was not packaged; network remains unconfigured.\n' >&2
  exit 1
fi

printf '\nBootstrap applied. A new login session will inherit libvirt group access.\n'
