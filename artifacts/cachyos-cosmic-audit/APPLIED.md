# Applied CachyOS COSMIC optimization

Applied: 2026-07-28

## Completed

- Created manual pre-change Snapper snapshot 160 and transaction snapshots
  161–168.
- Made `cosmic-greeter.service` the sole display manager.
- Removed Ly, SDDM, Plasma, Xfce session/components, Wayfire, their redundant
  portals/notification providers, and recursively unused dependencies.
- Retained COSMIC, GNOME Keyring, GVFS, COSMIC/GTK portals, XWayland, Thunar,
  and xfwm4 for Steam-session compatibility.
- Reduced available desktop sessions to COSMIC and the intentional Steam Big
  Picture session.
- Added user-local autostart overrides for Blueman, nm-applet, and the GeoClue
  demo agent; stopped their duplicate processes in the current session.
- Activated `xdg-desktop-portal-cosmic` in the current session.
- Configured Avahi as the sole mDNS/DNS-SD owner for WiVRn and
  `nss-mdns` for `.local` lookup; disabled systemd-resolved mDNS.
- Completed a full CachyOS update.
- Restored Python setuptools/wheel and Qt5 Wayland developer support.
- Installed `arch-audit`, `rustup`, `cargo-audit`, `cargo-deny`, `fwupd`,
  mold, and sccache.
- Installed Rust stable 1.97.1 through rustup.
- Enabled weekly paccache cleanup with two installed versions retained and
  removed several GiB of obsolete package cache.
- Bounded coredump storage at 2 GiB while retaining developer debugging.
- Removed the reviewed true orphans `ninja` and `wdisplays`.
- Verified UFW is active with default-deny inbound policy.
- Verified no available package upgrades, no failed system/user units, no
  Btrfs scrub errors, and no remaining package orphans.

## Firmware and visual identity follow-up

- Forced and successfully flashed the trusted LVFS Dell Precision 5570 BIOS
  update from 1.27.1 to 1.42.0 while connected to AC.
- Rebooted into CachyOS kernel 7.1.5-1 and confirmed fwupd reports
  `Update State: Success`.
- Applied the versioned LuigiOS visual identity from
  `LuigiOS/branding/cosmic-rice` to Limine, Plymouth, AccountsService/COSMIC
  Greeter, the COSMIC shell, wallpaper, dock/panel, and COSMIC Terminal.
- Rebuilt the normal and LTS CachyOS initramfs images through
  `limine-mkinitcpio`; both include the LuigiOS Plymouth assets.
- Installed `xorg-xrdb` so COSMIC can propagate the themed Xresources into
  retained XWayland applications.
- Created pre-reboot recovery snapshot 169; xorg-xrdb transaction snapshots
  are 170–171.

## Security tracker status

The final `arch-audit` refresh lists advisories for several fully updated
repository packages. `arch-audit --json` reports `fixed: null` for every listed
advisory, `arch-audit --upgradable` is empty, and `checkupdates` reports no
available builds. These are tracked upstream issues, not withheld local
updates. Removing foundational packages such as systemd, OpenSSL, PAM, or
coreutils would make the workstation less secure and unusable, so no unsafe
package substitution was attempted.

## Rollback

Use the Limine snapshot entry corresponding to Snapper snapshot 160 for the
manual pre-optimization state or snapshot 169 for the pre-firmware-reboot
state. Package/service/config baselines and transaction logs are stored in
[`applied/`](applied/). LuigiOS rice backups are under
`~/.local/state/luigios-rice/backups` and `/var/lib/luigios-rice/backups`.
