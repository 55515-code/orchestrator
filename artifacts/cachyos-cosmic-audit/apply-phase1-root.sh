#!/usr/bin/env bash
set -Eeuo pipefail

AUDIT_DIR="/home/ahron/codespace/artifacts/cachyos-cosmic-audit"
STATE_DIR="$AUDIT_DIR/applied"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$STATE_DIR"
exec > >(tee "$STATE_DIR/phase1-$STAMP.log") 2>&1

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'This script must run as root.\n' >&2
  exit 1
fi

printf 'Creating rollback snapshot and package/service baselines...\n'
snapper create \
  --description "pre-cosmic-only-optimization-$STAMP" \
  --cleanup-algorithm number \
  --print-number | tee "$STATE_DIR/snapshot-number-$STAMP.txt"
pacman -Qqe >"$STATE_DIR/explicit-packages-before-$STAMP.txt"
pacman -Qq >"$STATE_DIR/all-packages-before-$STAMP.txt"
systemctl list-unit-files --state=enabled --no-pager \
  >"$STATE_DIR/enabled-units-before-$STAMP.txt"
btrfs filesystem usage / >"$STATE_DIR/btrfs-usage-before-$STAMP.txt"

printf 'Making COSMIC Greeter the sole enabled display manager...\n'
systemctl disable --now ly@tty2.service
systemctl enable cosmic-greeter.service

printf 'Protecting shared COSMIC/developer packages from recursive removal...\n'
pacman -D --asexplicit \
  cosmic-session cosmic-greeter gnome-keyring gvfs \
  xdg-desktop-portal-cosmic xdg-desktop-portal-gtk \
  xorg-xwayland ripgrep-all xfwm4 thunar iio-sensor-proxy ddcutil

remove_candidates=(
  plasma-desktop
  sddm
  cachyos-kde-settings
  plasma5-integration
  kde-gtk-config
  xfce4-appfinder
  xfce4-notifyd
  xfce4-power-manager
  xfce4-screensaver
  xfce4-session
  xfce4-settings
  xfce4-taskmanager
  xfce4-terminal
  xfdesktop
  wayfire-desktop-git
  ly
  swaybg
)

installed_candidates=()
for package in "${remove_candidates[@]}"; do
  if pacman -Q "$package" >/dev/null 2>&1; then
    installed_candidates+=("$package")
  fi
done

printf 'Removing reviewed non-COSMIC roots: %s\n' "${installed_candidates[*]}"
if ((${#installed_candidates[@]})); then
  pacman -Rns --noconfirm "${installed_candidates[@]}"
fi

printf 'Disabling the duplicate mDNS responder while retaining resolved...\n'
systemctl disable --now avahi-daemon.socket avahi-daemon.service

printf 'Bounding future core dump storage without disabling debugging...\n'
install -d -m 0755 /etc/systemd/coredump.conf.d
cat > /etc/systemd/coredump.conf.d/50-developer-workstation-limits.conf <<'EOF'
[Coredump]
Storage=external
Compress=yes
ProcessSizeMax=4G
ExternalSizeMax=2G
MaxUse=2G
KeepFree=10G
EOF
systemctl daemon-reload

pacman -Qqe >"$STATE_DIR/explicit-packages-after-$STAMP.txt"
pacman -Qq >"$STATE_DIR/all-packages-after-$STAMP.txt"
pacman -Qdtq >"$STATE_DIR/orphans-after-$STAMP.txt" || true
systemctl --failed --no-pager >"$STATE_DIR/failed-units-after-$STAMP.txt"

printf 'Phase 1 root changes completed successfully.\n'
