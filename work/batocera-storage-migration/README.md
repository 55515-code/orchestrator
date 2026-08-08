# Batocera Steam Deck Plasma Derivative

This directory contains a Steam Deck-specific Plasma desktop prototype for
Batocera. Batocera remains the host and the sole owner of DRM, outputs, Labwc,
EmulationStation, emulator launch/exit, and controller hotkeys.

## Runtime Contract

- `Desktop Mode.sh` stays a normal Batocera Ports title.
- `emulatorlauncher` owns the complete synchronous lifecycle. Plasma is never
  detached, supervised in the background, or allowed to overlap another game.
- Plasma runs as UID 1000 from the persistent Arch userspace and KWin runs as a
  single fullscreen Wayland client nested under Batocera's existing Labwc.
- KWin receives no DRM or connector access. Batocera alone handles the Deck
  panel, rotation, HDMI selection, resolution changes, and restoration.
- The controller-to-KWin EIS bridge starts only after the desktop transaction
  is active and is stopped and waited for before `emulatorlauncher` returns.
- Logout, the Return shortcut, a KWin failure, and a shell signal all converge
  on the same foreground cleanup path.

## Components

- `device-config/desktop`: guarded foreground Ports launcher.
- `arch-plasma-session.sh`: nested Plasma process-group owner and cleanup.
- `device-config/kwin-wayland-wrapper`: adds KWin's supported nested fullscreen
  arguments to Plasma's own `kwin_wayland_wrapper` launch.
- `device-config/desktop-controller.sh`: desktop-scoped EIS controller mapper.
- `arch-plasma-mounts.sh`: explicit host storage bind mounts.
- `configure-arch-plasma.sh`: unprivileged Plasma, Discover, Flatpak, OSK, and
  desktop defaults.

The derivative intentionally does not ship a replacement Labwc configuration,
an ES restart watchdog, a direct EmulationStation launcher, AntiMicroX
autostart, a generated `es_features.cfg`, or a custom Steam process killer.

## Validated On Deck

- Desktop launched through the ES HTTP launch path as a Ports title.
- Exactly one nested KWin surface ran fullscreen at 1280x800 logical size.
- Built-in Deck controller connected to the KWin EIS bridge.
- Return completed with status 0 and restored ES.
- No KWin, Plasma, portal, mapper, emulatorlauncher, ACL, or runtime mount
  remained after return.
- Batocera retained `eDP-1` at 800x1280, transform 270 before and after.
- A RetroArch NES launch and standard Batocera exit completed `gameStop` with
  no Plasma processes and returned to ES.

Still required before an upstream-ready claim: DualSense Bluetooth reconnect,
HDMI hotplug/return on a television, sleep/resume during Plasma, and recovery
from a deliberately killed KWin process.

Do not commit device credentials, ROMs, BIOS files, firmware, Steam account
state, generated caches, screenshots, or `/userdata` backups.
