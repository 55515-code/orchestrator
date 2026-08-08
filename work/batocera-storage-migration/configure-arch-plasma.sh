#!/bin/bash
set -euo pipefail

container=/userdata/system/containers/arch-plasma
rootfs="$container/rootfs"
home="$container/home/deck"

[ -x "$rootfs/usr/bin/plasmashell" ] || {
    echo "Plasma is not installed" >&2
    exit 1
}

if ! chroot "$rootfs" /usr/bin/id deck >/dev/null 2>&1; then
    chroot "$rootfs" /usr/bin/useradd -u 1000 -M -d /home/deck \
        -G wheel,audio,video,input,storage,games deck
fi

cat > "$rootfs/etc/sudoers.d/deck-plasma-update" <<'EOF'
deck ALL=(root) NOPASSWD: /usr/bin/pacman -Syu
EOF
chmod 440 "$rootfs/etc/sudoers.d/deck-plasma-update"

mkdir -p "$home/.config/autostart" "$home/Desktop" "$home/Documents" \
    "$home/Downloads" "$home/.local/share" \
    "$home/.local/share/applications" \
    "$home/.local/share/icons/hicolor/256x256/apps"

install -m 755 /userdata/system/add-ons/desktop/helpers/kwin-wayland-wrapper \
    "$rootfs/usr/local/bin/kwin_wayland_wrapper"

if [ -f /userdata/system/add-ons/steam/extra/icon.png ]; then
    install -m 644 /userdata/system/add-ons/steam/extra/icon.png \
        "$home/.local/share/icons/hicolor/256x256/apps/steam.png"
fi

install -m 755 /userdata/system/add-ons/desktop/helpers/arch-plasma-update-notifier.py \
    "$rootfs/usr/local/bin/arch-plasma-update-notifier"

cat > "$rootfs/usr/local/bin/plasma-discover-deck" <<'EOF'
#!/bin/bash
exec plasma-discover --backends flatpak-backend "$@"
EOF
chmod 755 "$rootfs/usr/local/bin/plasma-discover-deck"

cat > "$rootfs/usr/local/bin/arch-plasma-update" <<'EOF'
#!/bin/bash
set -e

if [ "${1:-}" = --run ]; then
    printf '%s\n' 'Updating the persistent Arch Plasma userspace...'
    sudo /usr/bin/pacman -Syu
    printf '\n%s\n' 'Updating Plasma Flatpak applications...'
    flatpak --user update
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
    printf '\n%s\n' 'Updates complete. This does not modify the Batocera base system.'
    exit
fi

exec konsole --hold -e /usr/local/bin/arch-plasma-update --run
EOF
chmod 755 "$rootfs/usr/local/bin/arch-plasma-update"

cat > "$home/.config/autostart/org.kde.plasma-welcome.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Plasma Welcome
Hidden=true
EOF

cat > "$home/.config/autostart/arch-plasma-update-notifier.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Arch Plasma Update Notifier
Exec=/usr/local/bin/arch-plasma-update-notifier
Icon=system-software-update
Terminal=false
X-KDE-autostart-after=panel
EOF

cat > "$home/.config/kdeglobals" <<'EOF'
[General]
ColorScheme=BreezeDark

[Icons]
Theme=breeze-dark

[KDE]
LookAndFeelPackage=org.kde.breezedark.desktop
SingleClick=true
EOF

cat > "$home/.config/kscreenlockerrc" <<'EOF'
[Daemon]
Autolock=false
LockOnResume=false
EOF

if [ -f "$home/.config/kwinrc" ] && grep -q '^\[Wayland\]$' "$home/.config/kwinrc"; then
    if ! grep -q '^InputMethod=/usr/share/applications/org.kde.plasma.keyboard.desktop$' \
        "$home/.config/kwinrc"; then
        sed -i '/^\[Wayland\]$/a InputMethod=/usr/share/applications/org.kde.plasma.keyboard.desktop' \
            "$home/.config/kwinrc"
    fi
    if ! grep -q '^VirtualKeyboardMode=0$' "$home/.config/kwinrc"; then
        sed -i '/^\[Wayland\]$/a VirtualKeyboardMode=0' "$home/.config/kwinrc"
    fi
else
    cat >> "$home/.config/kwinrc" <<'EOF'

[Wayland]
InputMethod=/usr/share/applications/org.kde.plasma.keyboard.desktop
VirtualKeyboardMode=0
EOF
fi

cat > "$home/.config/baloofilerc" <<'EOF'
[Basic Settings]
Indexing-Enabled=false
EOF

cat > "$home/.config/user-dirs.dirs" <<'EOF'
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="/mnt/batocera/music"
XDG_PICTURES_DIR="/mnt/batocera/screenshots"
XDG_VIDEOS_DIR="$HOME/Videos"
EOF

cat > "$rootfs/usr/local/bin/batocera-desktop-command" <<'EOF'
#!/bin/bash
set -e
case "${1:-}" in
    return|steam-gamepadui|steam-bigpicture|steam-desktop|osk-toggle|steam-app:*)
        printf '%s\n' "$1" > /mnt/batocera/desktop-tools/plasma-command
        ;;
    *)
        echo "Usage: batocera-desktop-command {return|steam-gamepadui|steam-bigpicture|steam-desktop|osk-toggle|steam-app:APPID}" >&2
        exit 2
        ;;
esac
EOF
chmod 755 "$rootfs/usr/local/bin/batocera-desktop-command"

cat > "$home/Desktop/Return-to-Batocera.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Return to Batocera
Comment=Close Plasma and return to the console interface
Icon=system-log-out
Exec=/usr/local/bin/batocera-desktop-command return
Terminal=false
Categories=System;
EOF

cat > "$home/Desktop/Steam-Game-Mode.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Steam Game Mode
Comment=Open the Steam Deck controller interface
Icon=steam
Exec=/usr/local/bin/batocera-desktop-command steam-gamepadui
Terminal=false
Categories=Game;
EOF

cat > "$home/Desktop/Steam-Desktop.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Steam
Comment=Open the Steam desktop client and installed game library
Icon=steam
Exec=/usr/local/bin/batocera-desktop-command steam-desktop
Terminal=false
Categories=Game;
EOF

cat > "$home/Desktop/Steam-Big-Picture.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Steam Big Picture
Comment=Open Steam Big Picture
Icon=steam
Exec=/usr/local/bin/batocera-desktop-command steam-bigpicture
Terminal=false
Categories=Game;
EOF

cat > "$home/Desktop/ROM-Library.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=ROM Library
Icon=folder-games
Exec=dolphin /mnt/roms
Terminal=false
Categories=Game;FileTools;
EOF

cat > "$home/Desktop/Steam-SD-Library.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Steam SD Library
Icon=drive-removable-media
Exec=dolphin /mnt/steam-sd
Terminal=false
Categories=Game;FileTools;
EOF

cat > "$home/Desktop/Batocera-Storage.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Batocera Storage
Icon=folder
Exec=dolphin /mnt/batocera
Terminal=false
Categories=System;FileTools;
EOF

cat > "$home/Desktop/Software-Center.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Discover Software Center
Icon=plasmadiscover
Exec=/usr/local/bin/plasma-discover-deck --mode Browsing
Terminal=false
Categories=System;
EOF

cat > "$home/.local/share/applications/org.kde.discover.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Discover Software Center
GenericName=Software Center
Icon=plasmadiscover
Exec=/usr/local/bin/plasma-discover-deck --mode Browsing
Terminal=false
Categories=Qt;KDE;System;
Keywords=program;software;repository;package;install;remove;update;apps;Flatpak;
StartupNotify=true
EOF

cat > "$home/Desktop/System-Updates.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=System Updates
Comment=Update the persistent Arch userspace and Plasma Flatpak applications
Icon=system-software-update
Exec=/usr/local/bin/arch-plasma-update
Terminal=false
Categories=System;
EOF

chmod 755 "$home/Desktop"/*.desktop

for launcher in \
    Return-to-Batocera.desktop \
    Steam-Game-Mode.desktop \
    Steam-Desktop.desktop \
    Steam-Big-Picture.desktop \
    ROM-Library.desktop \
    Steam-SD-Library.desktop \
    Batocera-Storage.desktop \
    Software-Center.desktop \
    System-Updates.desktop; do
    install -m 644 "$home/Desktop/$launcher" \
        "$home/.local/share/applications/batocera-$launcher"
done

chown -R 1000:1000 "$home"

chroot "$rootfs" /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups \
    /usr/bin/env HOME=/home/deck USER=deck XDG_CURRENT_DESKTOP=KDE \
    XDG_DATA_DIRS=/home/deck/.local/share/flatpak/exports/share:/var/lib/flatpak/exports/share:/usr/local/share:/usr/share \
    /usr/bin/kbuildsycoca6 --noincremental || true

chroot "$rootfs" /usr/bin/setpriv --reuid=1000 --regid=1000 --init-groups \
    /usr/bin/env HOME=/home/deck USER=deck \
    flatpak --user remote-add --if-not-exists flathub \
    https://dl.flathub.org/repo/flathub.flatpakrepo || true

echo "Configured persistent Plasma home at $home"
