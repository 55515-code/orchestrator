#!/bin/bash
set -euo pipefail

rootfs=/userdata/system/containers/arch-plasma/rootfs

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

unmount_if_needed() {
    target_path=$1

    if findmnt -rn -o TARGET --target "$target_path" | grep -Fxq "$target_path"; then
        umount -R "$target_path" 2>/dev/null || umount -l "$target_path" 2>/dev/null || true
    fi
}

stop_mounts() {
    unmount_if_needed "$rootfs/home/deck"
    unmount_if_needed "$rootfs/root"
    unmount_if_needed "$rootfs/mnt/batocera/desktop-config"
    unmount_if_needed "$rootfs/mnt/batocera/desktop-tools"
    unmount_if_needed "$rootfs/mnt/batocera/desktop-shortcuts"
    unmount_if_needed "$rootfs/mnt/batocera/system-configs"
    for name in music themes screenshots saves bios; do
        unmount_if_needed "$rootfs/mnt/batocera/$name"
    done
    unmount_if_needed "$rootfs/mnt/steam-sd"
    unmount_if_needed "$rootfs/mnt/roms"
    unmount_if_needed "$rootfs/run"
    unmount_if_needed "$rootfs/sys"
    unmount_if_needed "$rootfs/proc"
    unmount_if_needed "$rootfs/dev"
}

case "${1:-start}" in
    start) ;;
    stop) stop_mounts; exit 0 ;;
    *) printf 'Usage: %s {start|stop}\n' "$0" >&2; exit 2 ;;
esac

[ -x "$rootfs/usr/bin/plasmashell" ] || exit 1
mkdir -p /userdata/system/containers/arch-plasma/home/deck
chown 1000:1000 /userdata/system/containers/arch-plasma/home/deck
chmod 700 /userdata/system/containers/arch-plasma/home/deck
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
mount_if_needed /userdata/system/add-ons/desktop/config "$rootfs/mnt/batocera/desktop-config"
mount_if_needed /userdata/system/containers/arch-plasma/home/root "$rootfs/root"
mount_if_needed /userdata/system/containers/arch-plasma/home/deck "$rootfs/home/deck"
cp -L /etc/resolv.conf "$rootfs/etc/resolv.conf"
