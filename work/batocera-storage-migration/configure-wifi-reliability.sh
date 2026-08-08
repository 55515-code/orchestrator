#!/bin/bash
set -euo pipefail

custom=/userdata/system/custom.sh
begin='# BEGIN CODEX WIFI RELIABILITY'
end='# END CODEX WIFI RELIABILITY'
tmp="$(mktemp)"

touch "$custom"
awk -v begin="$begin" -v end="$end" '
    $0 == begin { skip=1; next }
    $0 == end { skip=0; next }
    !skip { print }
' "$custom" > "$tmp"

cat >> "$tmp" <<'EOF'
# BEGIN CODEX WIFI RELIABILITY
# Keep controller streaming, SSH, scraping, and network shares stable while idle.
for iface in /sys/class/net/wlan*; do
    [ -e "$iface" ] || continue
    name="$(basename "$iface")"
    iw dev "$name" set power_save off 2>/dev/null || true
    [ -w "$iface/power/control" ] && printf 'on\n' > "$iface/power/control"
done
# END CODEX WIFI RELIABILITY
EOF

cp -a "$custom" "${custom}.pre-wifi-reliability-$(date +%Y%m%d-%H%M%S)"
install -m 0755 "$tmp" "$custom"
rm -f "$tmp"

for iface in /sys/class/net/wlan*; do
    [ -e "$iface" ] || continue
    name="$(basename "$iface")"
    iw dev "$name" set power_save off 2>/dev/null || true
    [ -w "$iface/power/control" ] && printf 'on\n' > "$iface/power/control"
done
