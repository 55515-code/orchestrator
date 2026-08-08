#!/usr/bin/env bash
set -Eeuo pipefail

AUDIT_DIR="/home/ahron/codespace/artifacts/cachyos-cosmic-audit"
STATE_DIR="$AUDIT_DIR/applied"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$STATE_DIR"
exec > >(tee "$STATE_DIR/phase2-$STAMP.log") 2>&1

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'This script must run as root.\n' >&2
  exit 1
fi

printf 'Completing a full CachyOS upgrade and installing developer modernization tools...\n'
pacman -Syu --needed --noconfirm \
  python-setuptools python-wheel qt5-wayland \
  arch-audit rustup cargo-audit cargo-deny \
  fwupd mold sccache

printf 'Configuring bounded weekly package-cache retention...\n'
install -m 0644 \
  "$AUDIT_DIR/config/pacman-contrib" \
  /etc/conf.d/pacman-contrib
paccache -rk2
paccache -ruk1
systemctl enable --now paccache.timer

printf 'Clearing the removed Ly unit failure and refreshing systemd...\n'
systemctl daemon-reload
systemctl reset-failed ly@tty2.service || true

printf 'Refreshing firmware metadata without applying firmware updates...\n'
fwupdmgr refresh --force || true
fwupdmgr get-devices >"$STATE_DIR/fwupd-devices-$STAMP.txt" 2>&1 || true
fwupdmgr get-updates >"$STATE_DIR/fwupd-updates-$STAMP.txt" 2>&1 || true

printf 'Recording post-modernization validation...\n'
pacman -Qqe >"$STATE_DIR/explicit-packages-modernized-$STAMP.txt"
pacman -Qdtq >"$STATE_DIR/orphans-modernized-$STAMP.txt" || true
systemctl --failed --no-pager >"$STATE_DIR/failed-units-modernized-$STAMP.txt"
systemctl list-timers paccache.timer --no-pager \
  >"$STATE_DIR/paccache-timer-$STAMP.txt"
btrfs filesystem usage / >"$STATE_DIR/btrfs-usage-modernized-$STAMP.txt"

printf 'Phase 2 root changes completed successfully.\n'
