# LuigiOS COSMIC Workstation Rice — Applied

Applied on 2026-07-28 to the CachyOS COSMIC workstation.

## Boot-to-desktop identity

- Limine: LuigiOS black boot menu wallpaper, green identity and selection
  palette, three-second recoverable menu.
- Plymouth: quiet black LuigiOS core-mark splash included in both installed
  CachyOS kernel initramfs images.
- COSMIC Greeter: LuigiOS account avatar through AccountsService.
- COSMIC shell: LuigiOS dark theme, workstation wallpaper, compact floating
  top panel, medium intelligent-hide dock, and developer-first favorites.
- Icons: installed a native `LuigiOS` icon theme for COSMIC, GTK 3, GTK 4, and
  GSettings. It provides 26 branded core application aliases, 78 green
  folder/place overrides, and complete Papirus Dark, COSMIC, and hicolor
  fallback coverage.
- COSMIC Terminal: JetBrains Mono Nerd Font, 96% opacity, pane boundaries, and
  bright-bold ANSI colors over the LuigiOS system palette.
- Code - OSS: deployed the local `LuigiOS Workstation` extension with a
  black/charcoal editor hierarchy, LuigiOS green focus/Git states, semantic
  syntax colors, matching ANSI terminal palette, JetBrains Mono typography,
  and purpose-built file/folder icons. Existing Podman settings were preserved.

## Verified live values

- theme accent: `#22C55E`
- theme background: `#121416`
- theme foreground tint: `#F5F7FA`
- wallpaper source checksum:
  `83ebfc9ee9679f9b049fcaf5f0f8db24e75051d4698162fb54c6e9a2554b3c93`
- boot kernels rebuilt: `linux-cachyos 7.1.5-1` and
  `linux-cachyos-lts 6.18.40-1`
- brand manifest: valid, no missing required assets
- live shell restart: clean, zero panel errors with LuigiOS icons rendered
- Code renderer: local theme registered and visually verified in an isolated
  preview and the active window without interrupting the Codex session

## Recovery

User backups live under `~/.local/state/luigios-rice/backups`. System backups
live under `/var/lib/luigios-rice/backups`. The deploy and rollback tooling is
versioned at `LuigiOS/branding/cosmic-rice`.
