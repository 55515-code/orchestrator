#!/bin/bash
set -euo pipefail

stamp="$(date +%Y%m%d-%H%M%S)"
backup="/userdata/system/config-backups/dead-steamos-links-${stamp}"
mkdir -p "$backup"

find /userdata/bios /userdata/saves \
    -path /userdata/saves/flatpak -prune -o \
    -xtype l -print0 2>/dev/null |
while IFS= read -r -d '' link; do
    target="$(readlink "$link")"
    case "$target" in
        /home/deck/*|/run/media/deck/*)
            relative="${link#/userdata/}"
            mkdir -p "$backup/$(dirname "$relative")"
            cp -a "$link" "$backup/$relative"
            printf '%s -> %s\n' "$link" "$target" >> "$backup/links.txt"
            rm -f "$link"
            ;;
    esac
done

printf 'Backup: %s\n' "$backup"
