#!/bin/bash
set -euo pipefail

rootfs=/userdata/system/containers/arch-plasma/rootfs
bridge=/usr/local/bin/plasma-gamepad-bridge
pidfile=/tmp/batocera-desktop-controller.pid
log=/userdata/system/logs/plasma-gamepad-bridge.log
desktop_state=/tmp/arch-plasma-desktop.active

start_mapper() {
    [ -f "$desktop_state" ] || {
        printf '%s\n' 'Refusing controller mapper outside desktop mode' >>"$log"
        return 1
    }
    if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        return
    fi
    rm -f "$pidfile"
    mkdir -p "$(dirname "$log")"

    [ -x "$rootfs$bridge" ] && [ -c /dev/uinput ] || {
        printf '%s\n' 'uinput or gamepad bridge is unavailable' >>"$log"
        return 1
    }
    setfacl -m u:1000:rw /dev/uinput || {
        printf '%s\n' 'Unable to grant the desktop mapper access to uinput' >>"$log"
        return 1
    }

    setsid chroot "$rootfs" /usr/bin/setpriv \
        --reuid=1000 --regid=1000 --init-groups \
        /usr/bin/env HOME=/home/deck USER=deck XDG_RUNTIME_DIR=/run/arch-plasma-runtime-1000 \
        SDL_JOYSTICK_HIDAPI=1 \
        "$bridge" \
        >>"$log" 2>&1 &
    printf '%s\n' "$!" > "$pidfile"
}

stop_mapper() {
    if [ -s "$pidfile" ]; then
        pid="$(cat "$pidfile")"
        if [ "$(readlink "/proc/$pid/root" 2>/dev/null)" = "$rootfs" ] && \
            grep -Fq "$bridge" "/proc/$pid/cmdline" 2>/dev/null; then
            kill -TERM -- "-$pid" 2>/dev/null || true
            pkill -TERM -P "$pid" 2>/dev/null || true
            kill -TERM "$pid" 2>/dev/null || true
            for _ in $(seq 1 20); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.1
            done
            kill -KILL -- "-$pid" 2>/dev/null || true
        fi
    fi
    rm -f "$pidfile"
    setfacl -x u:1000 /dev/uinput 2>/dev/null || true
}

case "${1:-}" in
    start) start_mapper ;;
    stop) stop_mapper ;;
    restart) stop_mapper; start_mapper ;;
    *) printf 'Usage: %s {start|stop|restart}\n' "$0" >&2; exit 2 ;;
esac
