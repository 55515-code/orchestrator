#!/usr/bin/env bash
set -Eeuo pipefail

AUDIT_DIR="/home/ahron/codespace/artifacts/cachyos-cosmic-audit"
STATE_DIR="$AUDIT_DIR/applied"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$STATE_DIR"
exec > >(tee "$STATE_DIR/mdns-$STAMP.log") 2>&1

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'This script must run as root.\n' >&2
  exit 1
fi

install -d -m 0755 /etc/systemd/resolved.conf.d
install -m 0644 \
  "$AUDIT_DIR/config/60-avahi-coexistence.conf" \
  /etc/systemd/resolved.conf.d/60-avahi-coexistence.conf
install -m 0644 \
  "$AUDIT_DIR/config/nsswitch.conf" \
  /etc/nsswitch.conf
systemctl unmask avahi-daemon.socket avahi-daemon.service
systemctl restart systemd-resolved.service
systemctl enable --now avahi-daemon.socket avahi-daemon.service
resolvectl status >"$STATE_DIR/resolved-mdns-$STAMP.txt"
ss -uap >"$STATE_DIR/udp-listeners-mdns-$STAMP.txt"
journalctl --since '-2 minutes' -u avahi-daemon.service --no-pager \
  >"$STATE_DIR/avahi-mdns-$STAMP.txt"
