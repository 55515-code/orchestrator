# CachyOS COSMIC workstation audit

Audit date: 2026-07-28  
Host: `cachyos-x8664`  
Scope: read-only live-system audit plus an implementation plan. No packages,
services, boot settings, or user configuration were changed.

## Executive result

The workstation already has a good CachyOS performance base: the current
`linux-cachyos` kernel, Btrfs with `noatime`, zstd compression and async
discard, 62.5 GiB zram, `systemd-oomd`, `power-profiles-daemon`, Ananicy,
bpftune, weekly trim, Snapper cleanup, and a complete COSMIC 1.4 stack.

The largest gains will come from correcting configuration conflicts and
removing obsolete desktop stacks, not from adding more kernel tweaks:

1. A failed firmware TPM probe blocks `tpm2.target` for about 90 seconds.
   Boot takes 2m18s, with userspace reaching `graphical.target` at 1m35s.
2. COSMIC Greeter and `ly@tty2` are both enabled, while the active COSMIC
   session was launched manually from TTY6. There should be one login path.
3. Plasma, Xfce, and Wayfire sessions are installed alongside COSMIC. Their
   portals, notification providers, policies, and autostarts produce duplicate
   D-Bus providers and unnecessary background processes.
4. Avahi and systemd-resolved are both responding to mDNS. Avahi logs that
   discovery is unreliable because another IPv4 and IPv6 mDNS stack exists.
5. The package cache is 19 GiB (5,590 files), the root filesystem is 81% full,
   and Btrfs data chunks are 98.66% allocated. Safe cache cleanup is the first
   storage action; blind Btrfs balancing is not.
6. A CachyOS-provided NVIDIA option,
   `NVreg_UsePageAttributeTable=1`, is rejected by driver 610.43.03. COSMIC
   also reports hybrid-GPU EGL/import and display-mode errors. This needs a
   current driver/CachyOS compatibility check before overriding packaged
   defaults.
7. COSMIC currently starts redundant `blueman-applet`, `blueman-tray`,
   `nm-applet`, and the GeoClue demo agent. COSMIC already supplies Bluetooth
   and network applets.

## System profile

- Dell mobile workstation, Intel Core i7-12800H (14 cores/20 threads)
- Intel Iris Xe plus NVIDIA RTX A2000 Laptop GPU (8 GiB)
- 62 GiB RAM; 62.5 GiB zram using zstd
- Samsung PM9A1 512 GB NVMe
- CachyOS kernel 7.1.5; NVIDIA 610.43.03
- Limine boot loader; Secure Boot disabled
- Btrfs root, approximately 379 GiB used and 93 GiB available
- 1,441 native packages, 249 explicit, 10 foreign/AUR packages
- No failed system units and no missing packaged files reported by `pacman -Qk`

## Desktop inventory

Installed login sessions:

- COSMIC (keep)
- Plasma (remove after dependency review)
- Xfce X11 and experimental Wayland (remove)
- Wayfire (remove)
- Steam Big Picture (keep if it is an intentional gaming session)

Enabled display/login services:

- `cosmic-greeter.service` on TTY1 (keep)
- `ly@tty2.service` (disable and remove)
- SDDM is installed but disabled (remove)

The dependency simulation for representative Plasma, Xfce, Wayfire, SDDM, and
Ly roots selects 165 packages and about 631 MiB installed size. It also selects
shared or useful packages—including `gnome-keyring`, `ripgrep-all`, fonts, and
some developer Python packages—so the simulated list must be reviewed and
allowlisted before executing. Do not copy a group-removal command blindly.

`gnome-keyring`, GTK, Qt, GVFS, XWayland, and some KDE libraries are not by
themselves evidence of an unwanted desktop. COSMIC has no native secrets
store, COSMIC Files uses GVFS for several network protocols, XWayland is a
COSMIC dependency, and developer applications may require GTK or Qt.

## Service disposition

| Unit | Decision | Reason |
|---|---|---|
| `cosmic-greeter` | Keep | Selected COSMIC login manager |
| `ly@tty2` | Remove | Second active login manager |
| `NetworkManager`, `systemd-resolved` | Keep | Active supported network/DNS path |
| `wpa_supplicant` | Keep | NetworkManager backend currently in use |
| `avahi-daemon` | Choose | Disable unless printer/DNS-SD advertising is needed; conflicts with resolved mDNS |
| `bluetooth` | Keep if used | Needed for Bluetooth devices; cheap when idle |
| `power-profiles-daemon` | Keep | Correct Intel P-state/platform profile integration |
| `switcheroo-control` | Keep | Useful and required by COSMIC session for hybrid GPU handling |
| `nvidia-powerd` | Keep, verify | Appropriate for a supported mobile NVIDIA GPU; verify driver logs after update |
| `ananicy-cpp` | Keep provisionally | CachyOS-supported application priority rules |
| `bpftune` | Benchmark | Uses about 84 MiB; validate benefit rather than stacking tuning daemons by assumption |
| `systemd-oomd` | Keep | Appropriate with large zram and desktop/developer workloads |
| `ollama` | Make on-demand if occasional | Adds network-online boot ordering and a persistent local API on 127.0.0.1:11434 |
| `iio-sensor-proxy` | Keep if auto-rotate/sensors used | Hardware-activated and under 1 MiB |
| `snapper` timers/integration | Keep | Rollback safety for a rolling distribution |
| `ufw` | Keep | Enabled firewall; no failed unit |

## Phased optimization plan

### Phase 0 — Snapshot and capture a root-complete baseline

The current audit ran without sudo because non-interactive sudo requires a
password. Before modifying the machine:

```bash
sudo snapper create --description "pre-cosmic-only-optimization" --cleanup-algorithm number
sudo btrfs filesystem usage /
sudo btrfs subvolume list -t /
sudo journalctl -b -p warning..alert --no-pager
systemd-analyze time
systemd-analyze critical-chain
```

Export explicit packages and enabled units to a dated directory. Keep the LTS
kernel and its matching NVIDIA module as the recovery boot option.

### Phase 1 — Make COSMIC the only login path

From a TTY, not from inside a package transaction:

```bash
sudo systemctl disable --now ly@tty2.service
sudo systemctl enable --now cosmic-greeter.service
systemctl is-enabled cosmic-greeter.service
systemctl is-active cosmic-greeter.service
```

Reboot and prove that COSMIC Greeter can log in, lock/unlock, log out, suspend,
resume, and start a second session before removing `ly` or SDDM.

### Phase 2 — Remove non-COSMIC desktop roots safely

First generate and archive the resolver output:

```bash
pacman -Rs --print-format '%n\t%v\t%s' \
  plasma-desktop sddm cachyos-kde-settings \
  xfce4-session xfdesktop xfwm4 \
  ly wayfire-desktop-git
```

Explicitly retain the shared functions that are intentional:

```bash
sudo pacman -D --asexplicit \
  cosmic-session cosmic-greeter gnome-keyring gvfs \
  xdg-desktop-portal-cosmic xdg-desktop-portal-gtk \
  xorg-xwayland ripgrep-all
```

Review every selected package against explicitly installed developer and gaming
applications. Then remove the approved desktop roots with `pacman -Rns`. Run
`pacman -Qdt` again and review each orphan; do not pipe it directly into a
removal command on the first pass.

Keep `steam-session-git` and `xfwm4` together if Steam Big Picture still relies
on that optional window manager. If the Steam session works without it, remove
`xfwm4` in a later transaction.

Validation gate:

```bash
find /usr/share/xsessions /usr/share/wayland-sessions -maxdepth 1 -type f -print
systemctl --failed
systemctl --user --failed
systemctl --user status 'xdg-desktop-portal*' --no-pager
journalctl --user -b | rg -i 'portal|notification|polkit|keyring'
```

Expected desktop entry: COSMIC, plus Steam Big Picture only if intentionally
retained. Expected portal: COSMIC with GTK only as fallback.

### Phase 3 — Remove COSMIC-session redundancies

Disable per-user autostart of Blueman, nm-applet, and the GeoClue demo agent
using user-local desktop overrides (do not edit files in `/etc/xdg/autostart`).
Confirm COSMIC's network and Bluetooth applets handle all required functions
first. Removing the packages can wait until dependent applications are known.

After the desktop removal, verify that duplicate notification D-Bus service
warnings from Plasma, Xfce, and Mako are gone.

### Phase 4 — Resolve mDNS ownership

Preferred minimalist path when printer/service advertisement is not needed:

```bash
sudo systemctl disable --now avahi-daemon.socket avahi-daemon.service
```

If Avahi is needed for CUPS/DNS-SD, retain Avahi and set systemd-resolved to
`MulticastDNS=resolve` in an `/etc/systemd/resolved.conf.d/` drop-in so it
resolves/caches but does not respond. Validate `.local` lookup and printer
discovery after either choice.

### Phase 5 — Fix the 90-second TPM boot stall

This is the highest-impact change but must be firmware-led:

1. Update Dell BIOS/UEFI and confirm whether TPM/PTT is intended to be enabled.
2. In firmware, either enable a working TPM/PTT or explicitly disable the
   broken device if TPM-backed disk unlock, measured boot, and attestation are
   not used.
3. Confirm `/dev/tpm0` and `/dev/tpmrm0` either appear promptly or are no longer
   advertised by firmware.
4. Reboot twice and compare `systemd-analyze time`, `critical-chain`, and the
   boot journal.

Do not mask the packaged `tpm2.target` as a first fix. Systemd is waiting
because firmware advertises a TPM while the kernel driver fails to initialize;
the firmware/driver state should be corrected at its source. A temporary
systemd timeout override is acceptable only after documenting the lack of TPM
use and testing rollback.

### Phase 6 — Storage hygiene

The package cache is the safe, immediate target:

```bash
sudo paccache -rk2
sudo paccache -ruk1
sudo systemctl enable --now paccache.timer
```

This keeps two installed-package versions and one uninstalled-package version.
Do not use `pacman -Scc`; retaining rollback packages is valuable on CachyOS.

Investigate the 394 GiB workspace separately with repository-aware tools.
Because Btrfs reflinks and snapshots distort ordinary `du`, do not bulk-delete
or run a full balance based on `du` alone. After cache and package cleanup,
recheck allocation. If metadata or data chunks remain tightly allocated,
perform a filtered, low-impact balance only after a fresh snapshot and a
root-level Btrfs assessment.

### Phase 7 — GPU and COSMIC stability

1. Fully update CachyOS packages and reboot into matching kernel/NVIDIA modules.
2. Verify the rejected packaged NVIDIA option against current CachyOS guidance
   and driver release notes; report it upstream if still reproducible.
3. Capture `journalctl -b _COMM=cosmic-comp` and test internal/external displays,
   suspend/resume, GPU offload, Electron/Chromium Wayland, and hardware video.
4. Retain `switcheroo-control`, the Intel iGPU stack, NVIDIA modules, and
   XWayland. They are functional parts of this hybrid COSMIC workstation.

Do not add generic NVIDIA environment variables or disable GSP firmware without
a reproduced symptom and current, model-specific evidence.

### Phase 8 — Workload-driven service tuning

- Convert Ollama from always-enabled to manually/socket/container managed if it
  is not used daily. This removes its dependency on `network-online.target`.
- Benchmark bpftune on/off for compile time, UI latency, battery/idle power, and
  thermals. Keep only if measurements show benefit.
- Keep `balanced` as the default power profile; use performance per build/game,
  not permanently on a mobile workstation.
- Keep CachyOS sysctl/zram defaults unless a measured workload demonstrates a
  regression. Avoid stacking random sysctl collections over
  `cachyos-settings`.

### Phase 9 — Modernization and developer-friendly security

The current baseline is stronger than a default desktop in several important
ways. ASLR and protected links/FIFOs are enabled, kernel pointers and dmesg are
restricted, Yama uses `ptrace_scope=1`, unprivileged BPF is restricted,
rootless Podman uses cgroup v2/OverlayFS/seccomp, UFW is enabled, and SSH is
not running. CachyOS makepkg flags already include `_FORTIFY_SOURCE=3`,
format-security errors, stack-clash protection, control-flow protection, full
RELRO/immediate binding, assertions for libstdc++, and LTO. Preserve these
defaults.

Use the following compatibility-first modernization order:

1. **Firmware and trusted boot:** install/use `fwupd` only if this Dell model is
   supported, update BIOS/UEFI, and repair the TPM first. After the COSMIC and
   NVIDIA stack is proven stable, evaluate Secure Boot with `sbctl` and signed
   CachyOS kernels/modules. Treat this as a separate project with a tested LTS
   fallback; do not enable lockdown or Secure Boot mid-cleanup.
2. **Memory-safe defaults for new code:** prefer stable Rust for native agents,
   CLIs, parsers, and network-facing helpers; Go is a reasonable GC-based
   option for services. Do not rewrite stable C/C++ merely to satisfy a label.
   Keep toolchains project-pinned (`rust-toolchain.toml`, package-manager
   lockfiles, container image digests) instead of replacing system packages
   with globally installed “latest” binaries.
3. **Unsafe-language testing:** for C/C++, add opt-in developer presets using
   Clang AddressSanitizer and UndefinedBehaviorSanitizer:

   ```bash
   CFLAGS="-O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined"
   CXXFLAGS="$CFLAGS"
   LDFLAGS="-fsanitize=address,undefined"
   ```

   Use these in CI/tests, not production binaries. Keep the hardened CachyOS
   release flags for normal packaging.
4. **Rust supply-chain checks:** install the supported Rust toolchain path, then
   use locked dependencies, `cargo audit` for known vulnerabilities, and
   `cargo deny` for license/source/advisory policy where a Rust project exists.
   Adopt `#![forbid(unsafe_code)]` in crates that need no unsafe operations;
   otherwise isolate and document small unsafe modules. Avoid global
   `RUSTFLAGS` that change every project or break binary dependencies.
5. **Rootless development:** make rootless Podman the default for disposable
   build/test services. It is already correctly mapped in `/etc/subuid` and
   `/etc/subgid`, uses cgroup v2, and has seccomp enabled. Prefer project-local
   Compose/Containerfiles and bind only required paths. Do not disable user
   namespaces globally: that would break rootless containers and browser/
   Electron sandboxes.
6. **Dependency automation:** add language-native update and audit jobs inside
   each repository rather than a global background daemon. Use lockfile-aware
   tools and review major upgrades. For Arch itself, add `arch-audit` if
   available in the enabled repositories and run it after updates; do not
   partially upgrade the rolling system.
7. **Core dumps:** cap persistent dump storage because one Electron crash
   already produced a truncated 737.5 MiB dump. Keep dumps available for
   developer debugging, but set bounded `MaxUse`/`KeepFree` in a
   `coredump.conf.d` drop-in rather than disabling them.
8. **Firewall/local services:** retain UFW and default-deny inbound policy.
   Ollama currently binds only to loopback, which is appropriate. Review rules
   after Avahi removal and expose development servers with explicit temporary
   rules, not broad permanent LAN access.
9. **Debugging compatibility:** retain `ptrace_scope=1`. Raising it to 2/3
   breaks ordinary IDE debuggers, sanitizers, Wine/anti-cheat, and profiling.
   Likewise, do not enable `hidepid`, disable all user namespaces, or enforce
   kernel lockdown until their impact on Polkit, Bluetooth, Electron, Podman,
   NVIDIA, hibernation, and performance tooling is tested.
10. **Optional security kernel:** the existing `linux-cachyos-lts` is the right
    recovery kernel. A hardened kernel may be tested as an additional boot
    entry for security-sensitive work, but should not replace the optimized
    CachyOS kernel on this hybrid-GPU developer workstation without benchmark
    and driver validation.

Modern does not mean globally chasing every newest version. For a rolling
CachyOS workstation, the reliable model is full system upgrades, project-pinned
toolchains, reproducible lockfiles, rootless isolation, and CI security checks.
This keeps the host current without making unrelated projects move together.

## Acceptance criteria

- COSMIC Greeter is the sole display manager and reliably starts COSMIC.
- Only intentional session entries remain.
- No failed system or user units.
- Boot has no 90-second TPM device timeout; measured userspace boot is reduced
  from approximately 96 seconds to a single-digit or low-double-digit target.
- No duplicate mDNS responder warning.
- No duplicate Plasma/Xfce/Mako notification providers in the COSMIC journal.
- COSMIC portal, file picker, screenshots/screen sharing, keyring, Polkit,
  network, Bluetooth, audio, suspend/resume, hybrid graphics, and Steam session
  all pass.
- At least one known-good LTS kernel and Snapper rollback point remain.
- Package cache is bounded automatically and Btrfs has healthy allocation
  headroom.
- Rootless Podman smoke tests pass and browser/IDE sandboxes remain enabled.
- C/C++ sanitizer presets and Rust audit/unsafe-code policy are project-local,
  reproducible, and do not alter production package flags.
- Firmware, Secure Boot, and kernel-lockdown decisions are documented and
  tested independently from desktop removal.

## Research basis

- [CachyOS settings](https://wiki.cachyos.org/features/cachyos_settings/) —
  packaged sysctl, zram, Ananicy, resolver, and systemd defaults
- [CachyOS kernel](https://wiki.cachyos.org/features/kernel/) — current kernel
  performance design; avoid redundant folklore tweaks
- [CachyOS general system tweaks](https://wiki.cachyos.org/configuration/general_system_tweaks/) —
  hardware-specific power/performance guidance
- [ArchWiki COSMIC](https://wiki.archlinux.org/title/COSMIC) — COSMIC packages,
  greeter, GVFS, and keyring limitations
- [ArchWiki systemd-resolved](https://wiki.archlinux.org/title/Systemd-resolved) —
  Avahi/mDNS coexistence rules
- [ArchWiki pacman](https://wiki.archlinux.org/title/Pacman) — cache retention
  and safe cleanup
- [ArchWiki pacman tips](https://wiki.archlinux.org/title/Pacman/Tips_and_tricks) —
  orphan and package-reason handling
- [ArchWiki security](https://wiki.archlinux.org/title/Security) — kernel,
  ptrace, namespaces, lockdown, and developer compatibility tradeoffs
- [Podman rootless mode](https://docs.podman.io/en/stable/markdown/podman.1.html#rootless-mode) —
  user namespaces and rootless storage/network requirements
- [Clang AddressSanitizer](https://clang.llvm.org/docs/AddressSanitizer.html) and
  [UndefinedBehaviorSanitizer](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html) —
  memory-safety testing for C/C++
- [Rust exploit mitigations](https://doc.rust-lang.org/nightly/rustc/exploit-mitigations.html) —
  official Rust compiler mitigation guidance

## Evidence and limitations

Raw command outputs are in [`evidence/`](evidence/). The collector is
[`collect-audit.sh`](collect-audit.sh) and is safe to rerun as a normal user.
It inventories config paths and sizes but deliberately does not copy the
contents of home configuration, credentials, tokens, browser profiles, SSH
keys, or keyrings.

Because sudo was unavailable non-interactively, unreadable root-only Btrfs
subvolumes/snapshots, firmware files, `/root`, full package cache details, and
some security attributes were not deeply inspected. Those items are explicitly
covered by Phase 0 rather than being represented as verified.
