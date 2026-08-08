#!/bin/sh
set -eu

BOOT_CONFIG=/boot/batocera-boot.conf
INTERNAL_ROOT=/mnt/internal-share-audit
INTERNAL_UUID=3d477112-3706-4ad8-83d6-bd6df44ae0ae
SD_UUID=31993872-bbf3-473d-b3e6-b8bd2115893f
SD_ROMS_PATH=/batocera/roms
STAMP=$(date +%Y%m%d-%H%M%S)

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || fail "run as root"
[ -f "$BOOT_CONFIG" ] || fail "missing $BOOT_CONFIG"
[ -d "$INTERNAL_ROOT/system" ] || fail "internal userdata migration is missing"
[ -s "$INTERNAL_ROOT/system/.ssh/authorized_keys" ] || fail "persistent SSH key is missing"

[ "$(blkid -s UUID -o value /dev/nvme0n1p2)" = "$INTERNAL_UUID" ] || fail "internal UUID mismatch"
[ "$(blkid -s UUID -o value /dev/mmcblk0p1)" = "$SD_UUID" ] || fail "SD UUID mismatch"
[ -d "/var/batocerafs$SD_ROMS_PATH" ] || fail "SD ROM directory is missing"

mount -o remount,rw /boot

BOOT_BACKUP="$BOOT_CONFIG.pre-nvme-userdata-$STAMP"
cp -a "$BOOT_CONFIG" "$BOOT_BACKUP"

TMP_BOOT=$(mktemp)
awk -v internal="$INTERNAL_UUID" -v sd="$SD_UUID" -v roms="$SD_ROMS_PATH" '
    /^sharedevice=/ { print "sharedevice=DEVICES"; found=1; next }
    /^sharedevice_part[0-9]+=/ { next }
    /^sharewait=/ { next }
    { print }
    END {
        if (!found) print "sharedevice=DEVICES"
        print "sharedevice_part1=SHARE@" internal
        print "sharedevice_part2=ROMS@" sd ":" roms
        print "sharewait=15"
    }
' "$BOOT_CONFIG" > "$TMP_BOOT"
install -m 0644 "$TMP_BOOT" "$BOOT_CONFIG"
rm -f "$TMP_BOOT"

TARGET_CONFIG="$INTERNAL_ROOT/system/batocera.conf"
TARGET_CUSTOM="$INTERNAL_ROOT/system/custom.sh"
CONFIG_BACKUP="$TARGET_CONFIG.pre-nvme-userdata-$STAMP"
CUSTOM_BACKUP="$TARGET_CUSTOM.pre-nvme-userdata-$STAMP"

cp -a "$TARGET_CONFIG" "$CONFIG_BACKUP"
cp -a "$TARGET_CUSTOM" "$CUSTOM_BACKUP"

# Preserve torrent data but keep background download services out of the console boot path.
sed -i -E \
    -e 's/(system\.services=.*) batocera_torrent/\1/' \
    -e 's/(system\.services=)batocera_torrent /\1/' \
    -e 's/(system\.services=)batocera_torrent$/\1/' \
    "$TARGET_CONFIG"

sed -i -E \
    's|^(/userdata/system/add-ons/qbittorrent/extra/startup\.sh.*)$|# Disabled for console performance: \1|' \
    "$TARGET_CUSTOM"

cat > "$INTERNAL_ROOT/system/storage-layout.txt" <<EOF
Configured: $STAMP
Batocera boot: internal NVMe /dev/nvme0n1p1
Batocera userdata: internal SHARE UUID $INTERNAL_UUID
ROM source: SD UUID $SD_UUID:$SD_ROMS_PATH
SD Steam library: SD root (configured after reboot)
Boot config backup: $BOOT_BACKUP
Previous internal userdata backup: $INTERNAL_ROOT/migration-backups/
Original SD userdata retained at: /batocera/
EOF

sync
mount -o remount,ro /boot

printf 'Storage layout staged successfully.\n'
printf 'Boot backup: %s\n' "$BOOT_BACKUP"
grep -E '^sharedevice|^sharewait' "$BOOT_CONFIG"
