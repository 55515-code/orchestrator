#!/bin/bash
set -euo pipefail

stamp="$(date +%Y%m%d-%H%M%S)"
backup_root="/userdata/system/config-backups/emulator-links-${stamp}"
mkdir -p "$backup_root"

replace_link() {
    local link="$1"
    local target="$2"
    local relative="${link#/userdata/}"

    mkdir -p "$(dirname "$link")" "$target"
    if [ -e "$link" ] || [ -L "$link" ]; then
        mkdir -p "$backup_root/$(dirname "$relative")"
        cp -a "$link" "$backup_root/$relative"
        rm -rf "$link"
    fi
    ln -s "$target" "$link"
}

# Eden and Citron share Batocera's yuzu-compatible data tree.
replace_link /userdata/system/configs/yuzu/keys /userdata/bios/switch/keys
replace_link /userdata/system/configs/yuzu/nand/system/Contents/registered /userdata/bios/switch/firmware

# These BIOS links are exposed for diagnostics and desktop tools.
replace_link /userdata/bios/yuzu/keys /userdata/bios/switch/keys
replace_link /userdata/bios/yuzu/firmware /userdata/bios/switch/firmware
replace_link /userdata/bios/eden/keys /userdata/bios/switch/keys
replace_link /userdata/bios/eden/firmware /userdata/bios/switch/firmware
replace_link /userdata/bios/citron/keys /userdata/bios/switch/keys
replace_link /userdata/bios/citron/firmware /userdata/bios/switch/firmware
replace_link /userdata/bios/ryujinx/keys /userdata/system/configs/Ryujinx/system
replace_link /userdata/bios/ryujinx/firmware /userdata/system/configs/Ryujinx/bis/system/Contents/registered
replace_link /userdata/bios/shadps4/sys_modules /userdata/system/configs/shadps4/user/sys_modules
replace_link /userdata/bios/flycast/bios /userdata/bios/dc

printf 'Backup: %s\n' "$backup_root"
