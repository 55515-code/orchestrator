#!/usr/bin/env bash
set -Eeuo pipefail

AUDIT_DIR="/home/ahron/codespace/artifacts/cachyos-cosmic-audit"
STATE_DIR="$AUDIT_DIR/applied"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$STATE_DIR"
exec > >(tee "$STATE_DIR/phase3-$STAMP.log") 2>&1

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'This script must run as root.\n' >&2
  exit 1
fi

printf 'Preventing duplicate Avahi activation while resolved owns mDNS...\n'
systemctl disable --now avahi-daemon.socket avahi-daemon.service || true
systemctl mask avahi-daemon.socket avahi-daemon.service

printf 'Removing only reviewed true orphans...\n'
for package in ninja wdisplays; do
  if pacman -Qdtq | rg -Fxq "$package"; then
    pacman -Rns --noconfirm "$package"
  fi
done

printf 'Running root-complete validation...\n'
pacman -Qkk >"$STATE_DIR/package-integrity-$STAMP.txt" 2>&1 || true
systemctl --failed --no-pager >"$STATE_DIR/system-failures-$STAMP.txt"
systemctl is-enabled cosmic-greeter.service \
  >"$STATE_DIR/cosmic-greeter-enabled-$STAMP.txt"
systemctl is-enabled avahi-daemon.service avahi-daemon.socket \
  >"$STATE_DIR/avahi-state-$STAMP.txt" 2>&1 || true
ufw status verbose >"$STATE_DIR/ufw-status-$STAMP.txt"
btrfs filesystem usage / >"$STATE_DIR/btrfs-usage-final-$STAMP.txt"
btrfs scrub status / >"$STATE_DIR/btrfs-scrub-status-$STAMP.txt" 2>&1 || true
journalctl -b -p warning..alert --no-pager \
  >"$STATE_DIR/journal-warnings-final-$STAMP.txt"
du -sh /var/cache/pacman/pkg >"$STATE_DIR/pacman-cache-final-$STAMP.txt"
find /var/cache/pacman/pkg -mindepth 1 -maxdepth 1 \
  -type d -name 'download-*' -empty -delete

printf 'Phase 3 root validation completed successfully.\n'
