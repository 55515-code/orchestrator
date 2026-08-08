#!/bin/bash
set -euo pipefail

container=/userdata/system/containers/arch-plasma
rootfs="$container/rootfs"
cache="$container/cache"
archive="$cache/archlinux-bootstrap-x86_64.tar.zst"
archive_url=https://geo.mirror.pkgbuild.com/iso/latest/archlinux-bootstrap-x86_64.tar.zst
sums_url=https://geo.mirror.pkgbuild.com/iso/latest/sha256sums.txt

log() {
    printf '[arch-plasma] %s\n' "$*"
}

mount_if_needed() {
    source_path=$1
    target_path=$2
    recursive=${3:-false}

    mkdir -p "$target_path"
    if findmnt -rn -o TARGET --target "$target_path" | grep -Fxq "$target_path"; then
        return 0
    fi
    if [ "$recursive" = true ]; then
        mount --rbind "$source_path" "$target_path"
        mount --make-rslave "$target_path"
    else
        mount --bind "$source_path" "$target_path"
    fi
}

mkdir -p "$cache"
if [ ! -s "$archive" ]; then
    log "Downloading the official Arch Linux bootstrap"
    curl -fL --retry 5 --retry-delay 3 -o "$archive.part" "$archive_url"
    mv "$archive.part" "$archive"
fi

log "Verifying the Arch Linux checksum"
curl -fsSL "$sums_url" -o "$cache/sha256sums.txt"
expected=$(awk '$2 == "archlinux-bootstrap-x86_64.tar.zst" { print $1 }' "$cache/sha256sums.txt")
actual=$(sha256sum "$archive" | awk '{ print $1 }')
[ -n "$expected" ] && [ "$actual" = "$expected" ] || {
    log "Checksum verification failed"
    exit 1
}

if [ ! -x "$rootfs/usr/bin/pacman" ]; then
    staging="$container/rootfs.staging"
    mkdir -p "$staging"
    log "Extracting the Arch Linux root filesystem"
    tar --zstd -xf "$archive" -C "$staging"
    mv "$staging/root.x86_64" "$rootfs"
fi

log "Mapping Batocera devices, runtime services, and local storage"
mount_if_needed /dev "$rootfs/dev" true
mount_if_needed /proc "$rootfs/proc"
mount_if_needed /sys "$rootfs/sys" true
mount_if_needed /run "$rootfs/run" true
mount_if_needed /userdata/roms "$rootfs/mnt/roms" true
mount_if_needed /userdata/steam-sd "$rootfs/mnt/steam-sd" true
for name in bios saves screenshots themes music; do
    [ -d "/userdata/$name" ] && \
        mount_if_needed "/userdata/$name" "$rootfs/mnt/batocera/$name"
done
mount_if_needed /userdata/system/configs "$rootfs/mnt/batocera/system-configs"
mount_if_needed /userdata/system/Desktop "$rootfs/mnt/batocera/desktop-shortcuts"
mount_if_needed /userdata/system/add-ons/desktop/helpers "$rootfs/mnt/batocera/desktop-tools"
cp -L /etc/resolv.conf "$rootfs/etc/resolv.conf"

mirrorlist="$rootfs/etc/pacman.d/mirrorlist"
if ! grep -q '^Server' "$mirrorlist"; then
    sed -i '0,/^#Server/s//Server/' "$mirrorlist"
fi
sed -i '/^DisableSandbox$/d' "$rootfs/etc/pacman.conf"
sed -i '/^\[options\]$/a DisableSandbox' "$rootfs/etc/pacman.conf"
sed -i 's/^CheckSpace/#CheckSpace/' "$rootfs/etc/pacman.conf"

log "Initializing Arch package trust"
chroot "$rootfs" pacman-key --init
chroot "$rootfs" pacman-key --populate archlinux
chroot "$rootfs" pacman -Sy --noconfirm archlinux-keyring

log "Installing Plasma 6 and the core KDE desktop applications"
chroot "$rootfs" pacman -S --needed --noconfirm \
    plasma-meta dolphin konsole kate ark kio-admin \
    gwenview okular filelight kcalc pacman-contrib fakeroot sudo python-pyqt6 \
    qt6-wayland xorg-xwayland mesa vulkan-radeon libinput \
    pipewire pipewire-alsa pipewire-pulse wireplumber \
    noto-fonts ttf-dejavu noto-fonts-emoji \
    xdg-user-dirs xdg-utils

mkdir -p "$container/home/root" "$container/home/deck" "$container/logs"
chmod 700 "$container/home/root"
chown 1000:1000 "$container/home/deck"
chmod 700 "$container/home/deck"
mount_if_needed "$container/home/root" "$rootfs/root"
mount_if_needed "$container/home/deck" "$rootfs/home/deck"

log "Plasma userspace installed successfully"
chroot "$rootfs" /usr/bin/pacman -Q plasma-workspace kwin dolphin
