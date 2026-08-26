# Nothing OS Stock Restore & Bootloader Relock — Fail-Safe Runbook

**Verified target:** Nothing Phone (3a) / (3a) Pro — codename `asteroids`
**Also supported (same community-confirmed flow):** `metroid`, `pacman`/`pacmanpro`, `pong`, `spacewar`, `tetris`, `galaga`
**Companion tool:** `scripts/nothing_stock_restore.sh` (automates this entire runbook)

This document defines a **fail-safe** procedure to take a Nothing/CMF device that
runs a custom ROM, root (Magisk/KernelSU), or any other modified software back to
**official stock Nothing OS** and, optionally, **re-lock the bootloader** — entirely
over ADB/fastboot.

---

## 0. Safety model — what "fail-safe" means here

Flashing firmware is never *literally* zero-risk, but this procedure is designed to
make each step individually safe and every failure recoverable:

1. **Stock-only images.** The only firmware source used is
   [`spike0en/nothing_archive`](https://github.com/spike0en/nothing_archive) — an
   unmodified mirror of Nothing's own OEM-signed firmware (also mirrored on
   archive.org). No custom kernels, no re-signed images, no avbroot tricks.
2. **Both A/B slots.** Every partition is written to both slots, so neither slot can
   be left stale-modified (a known cause of post-relock boot loops on `asteroids`,
   see [avbroot issue #602](https://github.com/chenxiaolong/avbroot/issues/602)).
3. **Lock only at the very end.** The bootloader is never locked until every flash
   and wipe has succeeded. Locking with any modified partition on this device sends
   it straight to the bootloader screen (verified in the same avbroot issue).
4. **Verified claims.** The script only reports "locked" after an authoritative
   `fastboot getvar unlocked` returns `no`. It never assumes.
5. **Fail-open abort.** Any failed step aborts with the device left **unlocked and
   bootable**, plus a log of exactly what happened. Nothing is half-locked.
6. **Emergency net.** If partition flashing is ever interrupted badly, the documented
   EDL (Emergency Download Mode) path with the Nothing Flash Tool restores the
   factory partition table (see §7 — marked optional).

Why this matters on `asteroids`: the bootloader enforces signature verification once
locked. A custom ROM (e.g. Infinity X) or Magisk-patched `init_boot` will **not** boot
with a locked bootloader. Stock Nothing OS is the only relockable state.

---

## 1. Pre-flight checklist

Run these before touching anything. All are enforced automatically by the script
(§3), which **refuses to proceed** if any fails.

| # | Check | Command / how the script verifies | Failure → |
|---|---|---|---|
| 1 | ADB debugging enabled + computer authorized | `adb devices` shows exactly one `device` entry | Script aborts with USB-debugging instructions |
| 2 | Device is a supported Nothing/CMF model | `adb shell getprop ro.product.vendor.device` (e.g. `asteroids`) | Script aborts: "unsupported device codename" |
| 3 | Battery ≥ 80% | `adb shell dumpsys battery` → `level:` | Script aborts (power loss during flash is the main brick risk) |
| 4 | Firmware matches exact model/variant | model number (e.g. `24111`) and `ro.build.fingerprint` region variant (`Asteroids`, `AsteroidsEEA`, `AsteroidsIND`, `AsteroidsJPN`, `AsteroidsTUR`, `*Pro*`) | Manual verification against `nothingarchive.tech` |
| 5 | No downgrade below current build | build date parsed from `ro.build.version.incremental` / tag | Script warns + requires `--allow-downgrade` |
| 6 | User backup acknowledged | typed confirmation `ERASE MY DEVICE` | Script aborts |

> ⚠️ **DATA LOSS WARNING — read twice:**
> This procedure **permanently erases all on-device data, twice** (once at `fastboot -w`,
> once again when the bootloader is re-locked). Back up photos, messages, 2FA /
> authenticator seeds, app data, and any files on internal storage. There is no
> partial-recovery path.

---

## 2. Firmware acquisition

**Option A — automatic (recommended).** The script resolves the latest release for
your codename from `spike0en/nothing_archive` via the GitHub API, downloads the
`-image-boot.7z`, `-image-firmware.7z`, `-image-logical.7z` assets, verifies
`.sha256` checksums when present, and extracts them. Requires `curl` or `wget`, `jq`,
`7z`, `unzip`.

**Option B — manual.** Go to `https://nothingarchive.tech`, pick **Nothing Phone (3a)**,
and download the **latest full stock build** (Nothing OS 4.x / Android 16 — same
generation as Infinity X, so rollback protection is satisfied). You need three
archives per build:

| Archive | Contents (flashed in bootloader fastboot) |
|---|---|
| `-image-boot.7z` | `boot`/`init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `vbmeta_system`, `vbmeta_vendor` |
| `-image-firmware.7z` | `modem`, `bluetooth`, `dsp`, `qupfw`, … |
| `-image-logical.7z` | dynamic partitions: `system`, `system_ext`, `vendor`, `product`, `odm`, `vendor_dlkm`, `system_dlkm` |

Extract all three into one folder. Use it with `-i <folder>` to skip auto-download.

**Build-version rule (rollback protection):** flash the **same or newer** stock build
than the device has seen. Rollback indices are embedded in `vbmeta`/`vbmeta_system`/
`vbmeta_vendor`; flashing older firmware can be refused by the bootloader.

---

## 3. Automated workflow — `scripts/nothing_stock_restore.sh`

```bash
# full restore + relock, auto-downloading the latest stock images:
bash scripts/nothing_stock_restore.sh

# restore only (bootloader stays unlocked), from already-extracted images:
bash scripts/nothing_stock_restore.sh -i ~/asteroids-images --no-lock

# pin a specific archive release tag:
bash scripts/nothing_stock_restore.sh -b Asteroids_B4.1-260414-1749
```

### What it does, step by step

| Phase | Action | Command pattern |
|---|---|---|
| Pre-flight | tools, single device, model whitelist, battery ≥ 80%, build info, typed data-wipe confirmation | `adb` queries + interactive prompt |
| Firmware | resolve latest release for codename → download `-image-*` assets → verify `.sha256` → extract | GitHub API + `curl`/`wget` + `7z` |
| **1/4** physical | reboot to bootloader fastboot, flash `boot`/`init_boot`, `vendor_boot`, `dtbo`, firmware set, then `vbmeta*` last — **both slots** | `fastboot flash <part>_a` / `fastboot flash <part>_b` |
| **2/4** logical | `fastboot reboot fastboot` (fastbootd), flash dynamic partitions to slot A, `set_active b`, reboot, flash again, restore slot A | `fastboot flash <part> <img>` in fastbootd |
| **3/4** wipe | reboot to bootloader, `fastboot -w` (falls back to fastbootd wipe if needed) | `fastboot -w` |
| **4/4** lock | interactive confirmation → `fastboot flashing lock` (fallback `fastboot oem lock`), confirm **on the phone** | `fastboot flashing lock` |
| Verify | wait for device, stock fingerprint + `vbmeta device_state=locked` + no Magisk/`su`; then reboot to bootloader and confirm `getvar unlocked=no`; final boot check | `getprop` + `fastboot getvar` |

The script is **dry-run safe** (`--dry-run` prints every command without executing),
**multi-device safe** (`--serial`), and logs everything to `state/nothing-restore/restore.log`.

### Safety behavior baked in

- Every `fastboot` command is retried once, then **aborts** (never continues past a
  failure). A failed flash never reaches the lock step.
- Name-ambiguous partition images are probed against the live device
  (`fastboot getvar partition-type:<name>`) before flashing; images for partitions
  that don't exist on the device are skipped with a warning instead of bricking.
- The lock step requires a second interactive confirmation and an on-phone
  confirmation (volume keys). Declining leaves the device **unlocked and bootable**.
- `--no-lock` runs the identical restore without the lock phase.

---

## 4. Manual reference — the exact verified command sequence

Use this only if you prefer to drive every command yourself. It mirrors the script.

```bash
# 0) pre-flight (see §1); reboot to bootloader
adb reboot bootloader
fastboot devices

# 1) physical partitions, BOTH slots — boot images first, vbmeta last
fastboot flash init_boot_a init_boot.img && fastboot flash init_boot_b init_boot.img
fastboot flash vendor_boot_a vendor_boot.img && fastboot flash vendor_boot_b vendor_boot.img
fastboot flash dtbo_a dtbo.img           && fastboot flash dtbo_b dtbo.img
#   ...firmware set (modem, bluetooth, dsp, qupfw) to both slots...
fastboot flash vbmeta_a vbmeta.img       && fastboot flash vbmeta_b vbmeta.img
fastboot flash vbmeta_system_a vbmeta_system.img && fastboot flash vbmeta_system_b vbmeta_system.img
fastboot flash vbmeta_vendor_a vbmeta_vendor.img && fastboot flash vbmeta_vendor_b vbmeta_vendor.img

# 2) dynamic partitions via fastbootd (userspace fastboot)
fastboot reboot fastboot
fastboot flash system system.img
fastboot flash system_ext system_ext.img
fastboot flash vendor vendor.img
fastboot flash product product.img
fastboot flash odm odm.img
fastboot flash vendor_dlkm vendor_dlkm.img
fastboot flash system_dlkm system_dlkm.img
#   (repeat the logical flashes for the other slot: set_active b; reboot fastboot; flash; set_active a)

# 3) wipe userdata + cache (avoids boot loops)
fastboot reboot bootloader
fastboot -w

# 4) re-lock — confirm on the phone
fastboot flashing lock          # fallback: fastboot oem lock

# 5) verify
fastboot getvar unlocked        # must print: unlocked: no
fastboot reboot
```

**Key subtleties (all community-verified for `asteroids`):**

- **Two different fastboot modes.** `adb reboot bootloader` = bootloader fastboot
  (unlock/lock, physical partitions). `adb reboot fastboot` = **fastbootd**
  (dynamic partitions only). `fastboot flashing lock` only works in bootloader mode.
- **`init_boot`, not `boot`, is the ramdisk partition** on Android 13+ GKI devices.
  The Nothing 3a boots from `init_boot`. (Patching the wrong image is a classic
  source of "no root" or boot loops; stock restore fixes it.)
- **`fastboot -w` wipes userdata and cache.** There is no separate `cache` partition
  on modern A/B devices; `-w` covers it.
- **TEE / Widevine.** Unlocking breaks the Qualcomm TEE keybox (Play Integrity +
  Widevine L1). Relocking **restores** it — this is the intended "no SafetyNet /
  verification failure" outcome, because the stock images restore the original AVB
  chain and the relock re-enables the original keybox. No spoofing modules involved.

---

## 5. Post-execution verification

Run the script and additionally confirm:

| Check | Expected | Command |
|---|---|---|
| Bootloader state | no boot warning ("Orange State"), straight to Nothing OS setup | `fastboot getvar unlocked` → `no` |
| Build authenticity | `release-keys` in fingerprint | `adb shell getprop ro.build.fingerprint` |
| AVB enforcement | `locked` | `adb shell getprop ro.boot.vbmeta.device_state` |
| Root removed | no Magisk package, no `su` | `adb shell pm list packages` \| `grep -i magisk` ; `adb shell command -v su` |
| OTA health | normal | Settings → System → System update |

If the device boots to setup with **no** "Orange State" warning and the above rows
pass, the relock is complete and the device behaves as factory stock.

---

## 6. Troubleshooting — common failure points

### 6.1 ADB connection drops mid-procedure

- **Symptoms:** `adb devices` goes empty; script's `wait_for_device` times out.
- **Causes/fixes:** faulty USB cable or port (use the OEM cable), USB driver issue
  (Windows: reinstall platform-tools USB driver; the community-reported working
  driver is the Huawei ADB interface driver for fastboot detection on `asteroids`),
  or the phone's "Allow USB debugging" prompt needs re-authorizing.
- **Recovery:** the device does not brick from a dropped ADB link. Reconnect,
  re-run the script — every step is idempotent (already-flashed partitions are
  simply re-flashed with the same stock image).

### 6.2 Fastboot device not detected (but ADB works)

- **Cause:** you ran `adb reboot fastboot` (fastbootd) instead of `adb reboot
  bootloader`, or the bootloader-mode driver isn't installed. fastbootd cannot run
  `flashing lock`/`flashing unlock`.
- **Fix:** use `adb reboot bootloader` for all lock/unlock and physical flashing;
  use `fastbootd` only for dynamic partitions (§4). Check `fastboot devices`.

### 6.3 Failed fastboot flash

- **Symptoms:** `FAILED (remote: ...)`; script aborts with the failing command in
  `state/nothing-restore/restore.log`.
- **`partition not found`** → you are flashing a dynamic partition from bootloader
  fastboot (or vice versa). Use fastbootd for `system*`/`vendor`/`product`/`odm`,
  bootloader fastboot for `boot`/`init_boot`/`vbmeta*`/firmware.
- **`not allowed` / permission** → confirm you're in the correct mode; re-authorize
  USB debugging; use the OEM cable.
- **Transient USB error** → the script retries once; on persistent failure, reboot
  the phone to bootloader (`fastboot reboot bootloader`), re-run.
- **Never continue after a failed flash.** Re-flash the failed partition before any
  further step. An interrupted flash never bricks by itself; **locking over a
  failed/incomplete flash is what bricks.**

### 6.4 Bootloader lock verification failure (`getvar unlocked` ≠ `no`)

- **Cause:** the lock command was refused (device still unlocked) — usually because
  a partition is not stock.
- **Fix:** do **not** reboot to system from fastboot if you want the lock. Re-run the
  script; it re-flashes every partition to both slots and retries the lock. If you
  used `--images-dir`, confirm you supplied the *complete* image set for the exact
  variant (GLO/EEA/IND/JPN/TUR) and build.
- If the lock *appeared* to succeed but `getvar unlocked` still reads `yes`, the
  device simply stayed unlocked — it remains fully bootable. Nothing to panic about.

### 6.5 Boot loop / "Orange State" / stuck at Nothing logo after relock

- **Cause:** a modified partition survived (stale inactive slot, custom `vbmeta`,
  Magisk-patched `init_boot` on the other slot, or a downgrade blocked by rollback
  protection).
- **Recovery:** unlock again (`fastboot flashing unlock`, confirm on phone), let it
  wipe, re-run the full restore so **both** slots are stock, then lock again.
  This device is known to recover from this state; it is not a hard brick.

### 6.6 Rollback-protection error on boot (`anti-rollback` / bootloader screen)

- **Cause:** flashing a build older than the bootloader's stored rollback index.
- **Fix:** download the **latest** stock build for your region variant and re-flash.
  Do not attempt to downgrade further.

### 6.7 Script prerequisites missing (`jq`, `7z`, `unzip`)

- Install them (`sudo apt install jq p7zip-full unzip`, or equivalent), or bypass
  auto-download entirely with `-i <extracted-images-folder>`.

---

## 7. Emergency recovery — EDL mode *(optional; last resort)*

If a flashing interruption ever leaves the partition table unusable, `asteroids`
supports Qualcomm **EDL (Emergency Download) mode**: power off, hold **Volume Up +
Volume Down**, connect USB, then flash the factory `24111_...` firmware with the
**Nothing Flash Tool** (Windows-only tool, community-archived; scan the binary first).
This repartitions and restores the factory state and is the documented unbrick path
for the 3a/3a Pro ([XDA guide](https://xdaforums.com/t/stock-rom-edl-flashing-for-bricked-nothing-phone-3a-pro-devices.4754702/)).
This is an **emergency-only** procedure, marked optional: the §1–§5 workflow is
designed so you never need it.

---

## 8. What this procedure deliberately excludes

- **Custom-key / re-signed images** (avbroot-style self-signed ROMs): on `asteroids`
  these do **not** boot with a locked bootloader (verified upstream in
  [avbroot #602](https://github.com/chenxiaolong/avbroot/issues/602)).
- **Keeping a modified OS with a locked bootloader**: impossible on this device —
  the bootloader only accepts Nothing's release-signed images when locked.
- **Carrier-locked / FRP workarounds**: out of scope and excluded by design; this
  procedure is for unlocking-approved, user-controlled devices.
- **Widevine/TEE reprovisioning hacks**: unnecessary — stock restore + relock
  restores the original keybox.

---

## 9. Sources

- Nothing OS firmware archive (canonical, OEM-sourced): `github.com/spike0en/nothing_archive` · `nothingarchive.tech`
- Relock feasibility evidence for `asteroids`: `github.com/chenxiaolong/avbroot/issues/602` (stock B4.1 boots and locks; self-signed images do not)
- Unlock/root/relock guide, all Nothing/CMF models: `awesome-android-root` / `awesome-android-root.pages.dev/rooting-guides/how-to-root-nothing-phone`
- fastboot vs fastbootd on `asteroids` (3a Pro): XDA thread `4768104`
- EDL unbrick / Nothing Flash Tool (emergency): XDA thread `4754702`
- TEE behavior on unlock/relock (Qualcomm/BBK, incl. Nothing): `github.com/melontini/bootloader-unlock-wall-of-shame/issues/92` · `github.com/Ubuntuify/nothing-widevine`
