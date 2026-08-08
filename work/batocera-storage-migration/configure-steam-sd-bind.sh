#!/bin/sh
set -eu

CUSTOM=/userdata/system/custom.sh
SD_TARGET=/userdata/steam-sd
STAMP=$(date +%Y%m%d-%H%M%S)

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
SD_DEVICE=$(findmnt -rn -o SOURCE --target /userdata/roms | sed 's/\[.*//')
SD_SOURCE=$(findmnt -rn -S "$SD_DEVICE" -o TARGET | sed -n '\#^/var/batocera_subdir_#p' | head -n 1)
[ -n "$SD_SOURCE" ] && [ -d "$SD_SOURCE/steamapps" ] || {
    echo "unable to discover SD Steam library from /userdata/roms" >&2
    exit 1
}

cp -a "$CUSTOM" "$CUSTOM.pre-steam-sd-$STAMP"

if ! grep -q '^# BEGIN CODEX STEAM SD BIND$' "$CUSTOM"; then
    cat >> "$CUSTOM" <<'EOF'

# BEGIN CODEX STEAM SD BIND
# Give Steam and Proton a stable path to the SD library mounted by Batocera DEVICES mode.
SD_STEAM_TARGET=/userdata/steam-sd
SD_STEAM_DEVICE="$(findmnt -rn -o SOURCE --target /userdata/roms | sed 's/\[.*//')"
SD_STEAM_SOURCE="$(findmnt -rn -S "$SD_STEAM_DEVICE" -o TARGET | sed -n '\#^/var/batocera_subdir_#p' | head -n 1)"
mkdir -p "$SD_STEAM_TARGET"
if [ -n "$SD_STEAM_SOURCE" ] && [ -d "$SD_STEAM_SOURCE/steamapps" ] && ! grep -qs " $SD_STEAM_TARGET " /proc/mounts; then
    mount --bind "$SD_STEAM_SOURCE" "$SD_STEAM_TARGET"
fi
# END CODEX STEAM SD BIND
EOF
fi

mkdir -p "$SD_TARGET"
if ! grep -qs " $SD_TARGET " /proc/mounts; then
    mount --bind "$SD_SOURCE" "$SD_TARGET"
fi

grep -qs " $SD_TARGET " /proc/mounts
test -d "$SD_TARGET/steamapps"
printf 'Steam SD bind active: %s -> %s\n' "$SD_SOURCE" "$SD_TARGET"
