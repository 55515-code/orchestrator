#!/bin/bash
set -u

container=/userdata/system/containers/arch-plasma
rootfs="$container/rootfs"
mounts=/userdata/system/add-ons/desktop/helpers/arch-plasma-mounts.sh
controller=/userdata/system/add-ons/desktop/helpers/desktop-controller.sh
sync_apps=/userdata/system/add-ons/desktop/helpers/sync-plasma-apps.py
command_file=/userdata/system/add-ons/desktop/helpers/plasma-command
pidfile=/tmp/arch-plasma-session.pid
log="$container/logs/session.log"
wayland_socket=/run/wayland-0
runtime_dir=/run/arch-plasma-runtime-1000
runtime_mount="$rootfs$runtime_dir/doc"
nested_wrapper="$rootfs/usr/local/bin/kwin_wayland_wrapper"

is_container_process() {
    pid=${1:-0}
    [ -d "/proc/$pid" ] && [ "$(readlink "/proc/$pid/root" 2>/dev/null)" = "$rootfs" ]
}

stop_session() {
    if [ -s "$pidfile" ]; then
        pid=$(cat "$pidfile")
        if is_container_process "$pid"; then
            kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
            for _ in $(seq 1 30); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.1
            done
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
            fi
        fi
    fi
    "$controller" stop >/dev/null 2>&1 || true
    rm -f "$pidfile"
    setfacl -x u:1000 "$wayland_socket" 2>/dev/null || true
    if findmnt -rn -o TARGET "$runtime_mount" 2>/dev/null | grep -Fxq "$runtime_mount"; then
        umount "$runtime_mount" 2>/dev/null || umount -l "$runtime_mount" 2>/dev/null || true
    fi
    rm -rf "$runtime_dir"
    "$mounts" stop >/dev/null 2>&1 || true
}

case "${1:-start}" in
    stop)
        stop_session
        exit 0
        ;;
    start) ;;
    *) printf 'Usage: %s {start|stop}\n' "$0" >&2; exit 2 ;;
esac

if [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    printf '%s\n' 'A Plasma session is already running' >&2
    exit 1
fi
if [ ! -S "$wayland_socket" ]; then
    printf '%s\n' 'Batocera Wayland socket is unavailable' >&2
    exit 1
fi
if [ ! -x "$nested_wrapper" ]; then
    printf '%s\n' 'Nested KWin wrapper is unavailable' >&2
    exit 1
fi

mkdir -p "$container/logs"
"$mounts" || exit 1
[ ! -x "$sync_apps" ] || "$sync_apps" >>"$log" 2>&1 || true

session_pid=
acl_granted=false
cleaned=false
cleanup() {
    [ "$cleaned" = false ] || return 0
    cleaned=true
    trap - EXIT INT TERM HUP

    "$controller" stop >/dev/null 2>&1 || true
    if [ -n "$session_pid" ] && is_container_process "$session_pid"; then
        kill -TERM -- "-$session_pid" 2>/dev/null || true
        for _ in $(seq 1 20); do
            kill -0 "$session_pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -KILL -- "-$session_pid" 2>/dev/null || true
        wait "$session_pid" 2>/dev/null || true
    fi

    rm -f "$pidfile"
    [ "$acl_granted" = false ] || \
        setfacl -x u:1000 "$wayland_socket" 2>/dev/null || true
    if findmnt -rn -o TARGET "$runtime_mount" 2>/dev/null | \
        grep -Fxq "$runtime_mount"; then
        umount "$runtime_mount" 2>/dev/null || umount -l "$runtime_mount" 2>/dev/null || true
    fi
    rm -rf "$runtime_dir"
    "$mounts" stop >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM HUP

# Plasma runs unprivileged while Labwc remains the sole display owner.  Give
# only UID 1000 temporary access to the parent socket; never change its owner.
if findmnt -rn -o TARGET "$runtime_mount" 2>/dev/null | \
    grep -Fxq "$runtime_mount"; then
    umount "$runtime_mount" 2>/dev/null || umount -l "$runtime_mount" 2>/dev/null || true
fi
rm -rf "$runtime_dir"
mkdir -p "$runtime_dir"
chown 1000:1000 "$runtime_dir"
chmod 700 "$runtime_dir"
if ! setfacl -m u:1000:rwx "$wayland_socket"; then
    printf '%s\n' 'Unable to grant Plasma access to Batocera Wayland' >&2
    exit 1
fi
acl_granted=true

: >"$command_file"
chown root:1000 "$command_file"
chmod 660 "$command_file"

plasma_compositor_alive() {
    for process in /proc/[0-9]*; do
        case "$(cat "$process/comm" 2>/dev/null)" in
            kwin_wayland|kwin_wayland_wr) ;;
            *) continue ;;
        esac
        [ "$(readlink "$process/root" 2>/dev/null)" = "$rootfs" ] || continue
        state=$(awk '{print $3}' "$process/stat" 2>/dev/null)
        [ "$state" != Z ] && [ "$state" != X ] && return 0
    done
    return 1
}

plasma_bus_address() {
    for process in /proc/[0-9]*; do
        [ "$(cat "$process/comm" 2>/dev/null)" = plasma_session ] || continue
        [ "$(readlink "$process/root" 2>/dev/null)" = "$rootfs" ] || continue
        tr '\0' '\n' <"$process/environ" 2>/dev/null | \
            sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' | head -n 1
        return
    done
}

run_as_deck() {
    chroot "$rootfs" /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups "$@"
}

toggle_osk() {
    bus=$(plasma_bus_address)
    [ -n "$bus" ] || return 1
    visible=$(run_as_deck /usr/bin/env DBUS_SESSION_BUS_ADDRESS="$bus" \
        /usr/bin/busctl --user get-property org.kde.KWin /VirtualKeyboard \
        org.kde.kwin.VirtualKeyboard visible 2>/dev/null | awk '{print $2}')
    if [ "$visible" = true ]; then
        active=false
    else
        active=true
    fi
    run_as_deck /usr/bin/env DBUS_SESSION_BUS_ADDRESS="$bus" \
        /usr/bin/busctl --user set-property org.kde.KWin /VirtualKeyboard \
        org.kde.kwin.VirtualKeyboard active b "$active" >/dev/null
    [ "$active" = false ] || run_as_deck /usr/bin/env DBUS_SESSION_BUS_ADDRESS="$bus" \
        /usr/bin/busctl --user call org.kde.KWin /VirtualKeyboard \
        org.kde.kwin.VirtualKeyboard forceActivate >/dev/null
}

refresh_apps() {
    [ ! -x "$sync_apps" ] || "$sync_apps" >>"$log" 2>&1 || true
    bus=$(plasma_bus_address)
    [ -n "$bus" ] || return 0
    run_as_deck /usr/bin/env HOME=/home/deck DBUS_SESSION_BUS_ADDRESS="$bus" \
        /usr/bin/kbuildsycoca6 --noincremental >>"$log" 2>&1 || true
}

# KWin is a nested Wayland client of Batocera's persistent Labwc compositor.
# The PATH shim adds KWin's supported nested fullscreen options to Plasma's own
# kwin_wayland_wrapper launch, so there is exactly one KWin compositor.
setsid chroot "$rootfs" /usr/bin/setpriv \
    --reuid=1000 --regid=1000 --init-groups \
    /usr/bin/env -i \
    HOME=/home/deck USER=deck LOGNAME=deck SHELL=/bin/bash \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/bin \
    XDG_RUNTIME_DIR=/run/arch-plasma-runtime-1000 XDG_SESSION_TYPE=wayland XDG_SESSION_DESKTOP=KDE \
    XDG_CURRENT_DESKTOP=KDE KDE_FULL_SESSION=true \
    XDG_DATA_DIRS=/home/deck/.local/share/flatpak/exports/share:/var/lib/flatpak/exports/share:/usr/local/share:/usr/share \
    WAYLAND_DISPLAY=/run/wayland-0 QT_QPA_PLATFORM=wayland \
    PULSE_SERVER=unix:/run/pulse/native PIPEWIRE_RUNTIME_DIR=/run \
    /usr/bin/dbus-run-session -- /usr/bin/plasma_session \
    >>"$log" 2>&1 &
session_pid=$!
printf '%s\n' "$session_pid" >"$pidfile"

started=false
for _ in $(seq 1 80); do
    if plasma_compositor_alive; then
        started=true
        break
    fi
    kill -0 "$session_pid" 2>/dev/null || break
    sleep 0.25
done
if [ "$started" != true ]; then
    printf '%s\n' 'Plasma compositor failed to start' >&2
    exit 1
fi

# This private mapper is allowed to own controllers only while ES is suspended.
"$controller" start || {
    printf '%s\n' 'Desktop controller mapper failed to start' >&2
    exit 1
}

while plasma_compositor_alive && kill -0 "$session_pid" 2>/dev/null; do
    if [ -s "$command_file" ]; then
        IFS= read -r command <"$command_file"
        : >"$command_file"
        case "$command" in
            return)
                break
                ;;
            steam-gamepadui|steam-bigpicture|steam-desktop|steam-app:*)
                # Steam and Steam games belong to Batocera's synchronous Steam
                # generator. Return to Game Mode instead of creating a second
                # Steam process outside that lifecycle.
                printf '%s requested; returning to Batocera Game Mode\n' \
                    "$command" >>"$log"
                break
                ;;
            osk-toggle)
                toggle_osk || true
                ;;
        esac
    fi
    sleep 0.25
done

exit 0
