#!/usr/bin/env bash
set -uo pipefail

OUT_DIR="${1:-$(pwd)/artifacts/cachyos-cosmic-audit/evidence}"
mkdir -p "$OUT_DIR"

capture() {
  local name="$1"
  shift
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n'
    "$@"
  } >"$OUT_DIR/$name.txt" 2>&1 || true
}

capture_shell() {
  local name="$1"
  local command="$2"
  {
    printf '$ %s\n' "$command"
    bash -o pipefail -c "$command"
  } >"$OUT_DIR/$name.txt" 2>&1 || true
}

capture os-release cat /etc/os-release
capture uname uname -a
capture cpu lscpu
capture memory free -h
capture block-devices lsblk -e7 -o NAME,TYPE,SIZE,FSTYPE,FSVER,MOUNTPOINTS,MODEL,ROTA,DISC-GRAN
capture mounts findmnt -R /
capture filesystem df -hT
capture btrfs-filesystems btrfs filesystem show
capture btrfs-usage btrfs filesystem usage /
capture pci lspci -nnk
capture usb lsusb
capture firmware bootctl status
capture cmdline cat /proc/cmdline
capture kernel-parameters sysctl -a
capture security systemd-analyze security
capture boot-time systemd-analyze time
capture boot-blame systemd-analyze blame
capture boot-critical-chain systemd-analyze critical-chain
capture failed-units systemctl --failed --no-pager
capture enabled-unit-files systemctl list-unit-files --state=enabled --no-pager
capture running-services systemctl list-units --type=service --state=running --no-pager
capture timers systemctl list-timers --all --no-pager
capture sockets systemctl list-sockets --all --no-pager
capture user-failed systemctl --user --failed --no-pager
capture user-enabled systemctl --user list-unit-files --state=enabled --no-pager
capture user-running systemctl --user list-units --type=service --state=running --no-pager
capture sessions loginctl list-sessions
capture session-details loginctl show-session self -a
capture seats loginctl seat-status seat0
capture power-profiles systemctl status power-profiles-daemon.service --no-pager
capture tuned systemctl status tuned.service --no-pager
capture irqbalance systemctl status irqbalance.service --no-pager
capture thermald systemctl status thermald.service --no-pager
capture zram zramctl
capture swaps swapon --show
capture oomd systemctl status systemd-oomd.service --no-pager
capture journal-size journalctl --disk-usage
capture journal-errors journalctl -b -p warning..alert --no-pager
capture coredumps coredumpctl list --no-pager
capture packages-explicit pacman -Qqe
capture packages-foreign pacman -Qqm
capture packages-orphans pacman -Qdtq
capture package-groups pacman -Qg
capture package-stats pacman -Q
capture package-files pacman -Qk
capture mirrors cat /etc/pacman.d/mirrorlist
capture cachyos-mirrors cat /etc/pacman.d/cachyos-mirrorlist
capture pacman-config pacman-conf
capture_shell package-cache "du -sh /var/cache/pacman/pkg 2>/dev/null; find /var/cache/pacman/pkg -maxdepth 1 -type f | wc -l"
capture_shell desktop-packages "pacman -Q | rg -i '(^|[-])(cosmic|gnome|gtk|kde|plasma|xfce|mate|cinnamon|lxqt|budgie|deepin|sway|hyprland|wayland|xorg|gdm|sddm|lightdm|xdg-desktop-portal)'"
capture_shell display-managers "systemctl list-unit-files --no-pager | rg -i '(^|/)(gdm|sddm|lightdm|greetd|cosmic-greeter)'"
capture_shell desktop-files "find /usr/share/xsessions /usr/share/wayland-sessions -maxdepth 1 -type f -printf '%p\n' 2>/dev/null | sort"
capture_shell portals "systemctl --user status 'xdg-desktop-portal*' --no-pager"
capture_shell large-packages "expac -H M '%m\t%n' 2>/dev/null | sort -hr | head -100"
capture_shell large-system-dirs "du -x -h -d1 /usr /var /opt 2>/dev/null | sort -h"
capture_shell large-home-dirs "du -x -h -d1 \"$HOME\" 2>/dev/null | sort -h"
capture_shell config-inventory "find /etc -xdev -type f -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort -nr"
capture_shell home-config-inventory "find \"$HOME/.config\" -xdev -type f -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort -nr"
capture_shell autostart "find /etc/xdg/autostart \"$HOME/.config/autostart\" -maxdepth 1 -type f -printf '%p\n' 2>/dev/null | sort"
capture_shell shell-startup "find \"$HOME\" -maxdepth 1 -type f \\( -name '.bash*' -o -name '.zsh*' -o -name '.profile' -o -name '.pam_environment' \\) -printf '%s\t%p\n'"
capture_shell flatpak "flatpak list --columns=application,ref,size,installation 2>/dev/null"
capture_shell flatpak-remotes "flatpak remotes --show-details 2>/dev/null"
capture_shell containers "docker system df 2>/dev/null; podman system df 2>/dev/null"
capture_shell network-units "systemctl list-unit-files --no-pager | rg -i '(NetworkManager|systemd-networkd|iwd|wpa_supplicant|connman|bluetooth|avahi|cups|ssh)'"
capture_shell listening-ports "ss -lntup"
capture_shell network-links "networkctl list 2>/dev/null; nmcli -f GENERAL.DEVICE,GENERAL.TYPE,GENERAL.STATE,GENERAL.CONNECTION device show 2>/dev/null"
capture_shell gpu-state 'for card in /sys/class/drm/card[0-9]*; do printf "%s\n" "$card"; cat "$card/device/power_dpm_force_performance_level" 2>/dev/null; cat "$card/device/power/runtime_status" 2>/dev/null; done'
capture_shell cpu-governor 'for f in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do printf "%s: " "$f"; cat "$f"; done'
capture_shell trim "systemctl status fstrim.timer --no-pager"
capture_shell btrfs-maintenance "systemctl list-timers --all --no-pager | rg -i '(btrfs|scrub|balance|trim|snapper)'"
capture_shell snapshots "snapper list-configs 2>/dev/null; timeshift --list 2>/dev/null"
capture_shell environment "printf 'XDG_CURRENT_DESKTOP=%s\nXDG_SESSION_DESKTOP=%s\nXDG_SESSION_TYPE=%s\nDESKTOP_SESSION=%s\n' \"${XDG_CURRENT_DESKTOP-}\" \"${XDG_SESSION_DESKTOP-}\" \"${XDG_SESSION_TYPE-}\" \"${DESKTOP_SESSION-}\""
capture_shell toolchains 'for x in gcc clang rustc cargo go python python3 node npm pnpm bun deno java javac docker podman distrobox flatpak; do command -v "$x" >/dev/null && "$x" --version 2>&1 | head -2; done'
capture_shell security-modernization 'cat /sys/kernel/security/lsm 2>/dev/null; cat /sys/kernel/security/lockdown 2>/dev/null; sysctl kernel.yama.ptrace_scope kernel.kptr_restrict kernel.dmesg_restrict kernel.unprivileged_bpf_disabled kernel.kexec_load_disabled kernel.randomize_va_space fs.protected_hardlinks fs.protected_symlinks fs.protected_fifos fs.protected_regular user.max_user_namespaces; rg -n "^(CFLAGS|CXXFLAGS|LDFLAGS|RUSTFLAGS|MAKEFLAGS|BUILDENV|OPTIONS)" /etc/makepkg.conf /etc/makepkg.conf.d/* 2>/dev/null; rg -n "^$(id -un):" /etc/subuid /etc/subgid 2>/dev/null; podman info --format json 2>/dev/null | rg -n "rootless|seccomp|apparmor|selinux|cgroupVersion|graphDriverName"'

{
  date --iso-8601=seconds
  printf 'hostname=%s\n' "$(hostname)"
  printf 'collector_user=%s\n' "$(id -un)"
  printf 'root_access=no (collector intentionally does not prompt for sudo)\n'
} >"$OUT_DIR/manifest.txt"
