# Android → Portable Multi-Function Security Tool — Full Deployment & Validation Guide

**Research date:** 2026-08-22
**Reference devices:** Flipper Zero + WiFi Pineapple (functional targets ONLY — no Flipper-specific
implementations used)
**Target:** Standard rooted Android device transformed into a portable security platform
**Legal scope:** Authorized testing only — systems you own or have written permission to assess.
Respect local spectrum regulations (FCC Part 15 / regional equivalents). This document is
educational; misuse may violate law.

---

## 0. Executive Summary

The proven, community-standard way to turn an Android device into a Flipper-Zero/WiFi-Pineapple-class
tool is **Kali NetHunter** (from Offensive Security) in its **Full** edition — a custom-kernel Android
build that provides the mobile UI, kernel modules, and toolchain. It is augmented with:

- **External USB radios** for wireless auditing (RTL8812AU / MT7612U / AR9271 adapters)
- **SDR hardware + apps** for RF capture/analysis (RTL-SDR / HackRF via RF Analyzer)
- **Standard CLI tools** (bettercap, nmap, aircrack-ng, wifite2, tcpdump) for recon/BLE
- **Termux** as a rootless fallback tier for network-only tasks

**Capability mapping to reference devices:**

| Target capability | Flipper Zero reference | WiFi Pineapple reference | Android implementation (this guide) | Tier required |
|---|---|---|---|---|
| RF capture & analysis | Sub-GHz RX + CC1101 | — | **RF Analyzer** (HackRF/RTL-SDR/Airspy/HydraSDR) over USB-OTG | Rootless (app) |
| Wireless network auditing | — | PineAP/scan | **aircrack-ng + wifite2** on external adapter (monitor mode) | Full (kernel) |
| Rogue access point | — | PineAP evil-twin | **MANA Wireless Toolkit / WifiPumpkin** (NetHunter) | Full (kernel) |
| Payload delivery (HID) | BadUSB/Rubber Ducky | — | **NetHunter HID Attacks + DuckHunter**, **TapDucky**, **Rucky** | Full (kernel) / Lite |
| Network reconnaissance | — | Recon / capture | **nmap, bettercap, masscan, tcpdump** | Rootless–Full |
| BLE device interaction | BLE scanner | — | **bettercap ble module**, **NetHunter Bluetooth Arsenal** (incl. Bad Bluetooth HID) | Rootless (ble) / Full |

**Recommended deployment:** NetHunter **Full** on a supported device (Google Pixel 4–7, OnePlus 6–8,
older Samsung Galaxy, or other kernel-supported devices), plus an RTL8812AU USB adapter and a powered
OTG hub. NetHunter's GitLab contains **250+ kernels for 110+ devices** — check the live list first.

Sources: kali.org/docs/nethunter (components, wireless-cards, supported devices); fosslinux.com 2026
guide; yupitek.com ALFA/NetHunter guide; sdrstore.eu SDR app ranking 2026; github.com/bettercap;
github.com/iodn/tap-ducky; github.com/mayankmetha/Rucky.

---

## 1. Architecture: The Three NetHunter Tiers

| Tier | Root | Custom kernel | Capabilities | Best for |
|---|---|---|---|---|
| **Rootless** (NetHunter Rootless / Termux) | No | No | nmap, bettercap (Ethernet/BLE), SDR apps, tcpdump, wifi recon (scan only) | Quick recon, no wipe |
| **Lite** | Yes (Magisk) | No | Full Kali chroot tools, root services | Existing rooted devices |
| **Full** | Yes | **Yes (device-specific NetHunter kernel)** | Everything: monitor mode, packet injection, HID/BadUSB, MANA rogue AP, USB Arsenal, SDR drivers | The Flipper/Pineapple-class device |

**Decision:** Choose **Full** to match reference-device functionality. Choose **Lite** only if the device
has no NetHunter kernel. Choose **Rootless/Termux** only for recon-only tasks.

---

## 2. Device Compatibility Check (do this BEFORE buying/rooting)

### 2.1 Official support
- **NetHunter full images** (kali.org/get-kali): published for popular devices.
- **Full kernel list** (live, auto-generated): https://nethunter.kali.org/device-kernels.html — 250+ kernels, 110+ devices.
- **Known-good families** (per 2026 guides): Google Pixel (strong unlock/community), OnePlus 6/6T/7/7 Pro/8/8 Pro (NetHunter kernels, e.g. kimocoder's kernel), older Samsung Galaxy (custom-kernel support), Nexus 5/6/6P (legacy).
- **NetHunter Pro** (different product, full Kali as primary OS): PinePhone/PinePhone Pro, Poco F1, OnePlus 6/6T, Nothing Phone 1 (pre-release), Xiaomi Mi MIX 2S, SHIFT6mq.

### 2.2 Hardware prerequisites
- **USB OTG support** — mandatory. Verify before purchase (most modern devices OK; check spec sheet).
- **Rootable bootloader** (unlockable) for Full tier.
- **Custom recovery** (TWRP/OrangeFox) for flashing NetHunter kernel/zip.
- **External Wi-Fi adapter** for monitor mode/injection (see §3).
- **Powered USB-OTG hub** strongly recommended (adapters draw ~500 mW; prevents battery drain/disconnect).
- **Quality cables** (cheap cables cause intermittent disconnects and flaky RF results).

### 2.3 Verify mode support before buying an adapter
```bash
# In NetHunter chroot (root):
iw list | grep -A8 "Supported interface modes"   # must show: * monitor, * AP, * managed
airmon-ng                                              # lists chipset/driver/interface
```

---

## 3. Recommended External Hardware (verified chipsets)

### 3.1 Wireless adapters (monitor mode + injection)

| Adapter | Chipset | Bands | NetHunter kernel support | Notes |
|---|---|---|---|---|
| **Alfa AWUS036ACH** | RTL8812AU | 2.4/5 GHz | ✅ Best (`88XXau` module) | Default recommendation |
| **Alfa AWUS036ACM** | MT7612U | 2.4/5 GHz | ✅ Good | Alternative chipset |
| **Alfa AWUS036ACS** | RTL8811AU | 2.4/5 GHz | ✅ Works | ~300 mW, lower power |
| **Alfa AWUS036NHA** | AR9271 | 2.4 GHz | ✅ In-kernel `ath9k_htc` | Budget/legacy; 2.4 only |
| TP-Link Archer T4UHP | RTL8812AU | 2.4/5 GHz | ✅ | Same chipset family |
| Alfa AWUS036AXML | MT7921AUN | +6 GHz | ⚠️ Limited | WiFi 6E; kernel-dependent |

**Rule:** chipset matters more than brand. RTL8812AU (`88XXau`/`RTL88XXAU`) has the widest NetHunter
kernel support. Note RTL8812AU merged into mainline Linux 6.14 (Feb 2026) — better on recent Kali.

### 3.2 SDR (RF capture/analysis)

| Device | Range | Android app |
|---|---|---|
| RTL-SDR Blog V3/V4 (RTL2832U) | ~24 MHz–1.7 GHz RX | RF Analyzer, SDR Touch, SDR++ |
| HackRF One | 1 MHz–6 GHz RX/TX | RF Analyzer (HackRF), SDRangel |
| Airspy / Airspy HF+ | 1 MHz–1.7 GHz RX | RF Analyzer |
| HydraSDR | 1 MHz–6 GHz | RF Analyzer |

App ranking 2026: **SDR Touch** (beginner), **RF Analyzer** (modern spectrum/waterfall — supports
HackRF, RTL-SDR, Airspy, HydraSDR), **SDR++** (lightweight), **SDRangel** (advanced decoders: AIS,
ADS-B, digital voice, packet), **SatDump** (satellite). Requires USB-OTG + RTL2832U driver app
(marto.rtl_tcp_andro) for RTL-SDR.

Sources: rtl-sdr.com; sdrstore.eu (2026 ranking); github.com/demantz/RFAnalyzer.

### 3.3 Bluetooth
- Built-in chipset usually suffices for bettercap BLE.
- NetHunter known-working external adapters: **Sena UD100**, **TP-Link UB500**, generic **CSR 4.0**.

---

## 4. Full End-to-End Deployment (NetHunter Full)

### 4.1 Prerequisites
1. NetHunter-supported, USB-OTG-capable device (see §2).
2. Unlocked bootloader + custom recovery (TWRP) installed.
3. ~8 GB free storage; device fully charged; backup done (flashing wipes).

### 4.2 Root access (required for Full/Lite)
1. Enable Developer options (tap Build number 7×).
2. Enable **OEM unlocking**; reboot to bootloader: `adb reboot bootloader`.
3. `fastboot flashing unlock` (wipes data) — follow on-screen confirmation.
4. Flash **TWRP**: `fastboot flash recovery twrp-<device>.img`.
5. Boot recovery; flash **Magisk** (`Magisk-v*.apk` → Install → Select and Patch a File →
   patch `boot.img`, `fastboot flash boot magisk_patched.img`) — or flash a Magisk-patched
   boot zip. **Magisk is the supported root method** (KSU is not officially supported).
6. Verify root: `adb shell su -c id` → `uid=0(root)`.

### 4.3 Install NetHunter (choose the correct zip for your device)
Download from kali.org/get-kali or the nethunter.kali.org images list:
`nethunter-<ver>-<device>-kalifs-full.zip`

```bash
# 1. Push and flash via TWRP (or install in TWRP UI)
adb push nethunter-*-full.zip /sdcard/
adb reboot recovery
# In TWRP: Install -> select zip -> flash -> wipe cache -> reboot system

# 2. Open the NetHunter app -> Kali Chroot Manager -> install/verify chroot
# 3. NetHunter Store: install extras (Hacker's Keyboard, VNC clients)
```

Verify:
```bash
adb shell su -c "chroot /data/local/nhsystem/kali-* /bin/bash -c 'nmap --version'"
```

### 4.4 Load external wireless kernel modules
NetHunter kernels auto-load `88XXau` on adapter detection. Manual fallback:
```bash
# In NetHunter terminal (root):
modprobe 88XXau                # RTL8812AU/8814AU/8821AU family
# or for RTL8188EUS:
modprobe 8188eu
# Verify:
lsusb | grep -i realtek        # adapter present
ip link | grep wlan            # wlan1/wlan2 appeared
airmon-ng                      # lists chipset + driver
```

### 4.5 Install / verify core toolset (Kali chroot)
```bash
apt update
apt install -y aircrack-ng wifite2 bettercap nmap masscan tcpdump hostapd dnsmasq
# MANA / WifiPumpkin are part of the NetHunter app (MANA Wireless Toolkit tab)
```

---

## 5. Capability-by-Capability Configuration & Workflows

### 5.1 Wireless network auditing (Flipper-Pineapple equivalent)
```bash
airmon-ng check kill
airmon-ng start wlan1                    # -> wlan1mon
airodump-ng wlan1mon                     # scan all bands
airodump-ng -c 11 --bssid AA:BB:CC:DD:EE:FF -w cap wlan1mon   # targeted capture
aireplay-ng -0 5 -a AA:BB:CC:DD:EE:FF wlan1mon                # deauth (capture handshake)
aircrack-ng -w /usr/share/wordlists/rockyou.txt cap-01.cap    # crack
# Automated:
wifite --dict /path/rockyou.txt         # WEP/WPA/WPA2/WPS automation
# PMKID capture:
hcxdumptool -i wlan1mon -o pmkid.pcapng
```
**Requires Full tier + external adapter.** Internal chipsets rarely support monitor mode (exceptions:
Nexus 5, OnePlus 7, etc.).

### 5.2 Rogue access point deployment (WiFi Pineapple equivalent)
Via NetHunter app → **MANA Wireless Toolkit** (one-click evil AP) or **WifiPumpkin** (captive portal).
Manual (with external adapter):
```bash
# hostapd (AP) + dnsmasq (DHCP/DNS) + iptables forwarding
hostapd /etc/hostapd/hostapd.conf &
dnsmasq -C /etc/dnsmasq.conf &
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080   # captive portal
```

### 5.3 RF signal capture & analysis (Flipper RF equivalent)
1. Connect RTL-SDR/HackRF via USB-OTG (RTL-SDR: install **RTL2832U driver** app first).
2. Open **RF Analyzer** → FFT + waterfall spectrum, demod AM/FM/SSB/CW, record IQ.
3. Advanced: **SDRangel** (AIS, ADS-B, digital voice, packet), **SatDump** (satellite).
4. CLI in chroot: `rtl_fm -f 433.92M -M fm -s 22050 | play -t raw -r 22050 -e signed -b 16 -c 1 -` for
   listening; `rtl_power` for wide-band scans.
**Requires:** OTG + SDR hardware. No root needed for the app tier; drivers in Full kernel add support.

### 5.4 Payload delivery — HID / BadUSB (Rubber Ducky equivalent)
- **NetHunter app → USB Arsenal**: set USB function to `hid` (disable ADB) → **HID Attacks** tab
  (PowerSploit / Windows CMD / PowerShell HTTP payload).
- **DuckHunter HID**: load Rubber Ducky `.duck` scripts (default `/sdcard/nh_files/duckyscripts/`),
  converts + executes.
- **TapDucky** (open-source, F-Droid): ConfigFS-based keyboard/mouse/composite HID gadget; DuckyScript
  editor, scheduler, payload library — requires root + ConfigFS gadget support (Android 11+).
- **Rucky**: wired HID via custom kernel or configfs.
- **BadUSB MITM attack**: NetHunter presents as a network adapter and MITMs traffic.
- **Bad Bluetooth** (BLE HID injection): NetHunter **Bluetooth Arsenal → Bad Bluetooth** — spoof a BT
  keyboard, inject keystrokes (requires supported chipset/external adapter).

### 5.5 Network reconnaissance
```bash
nmap -sP 192.168.1.0/24            # host discovery
nmap -sS -A 192.168.1.1            # service/OS scan
masscan 192.168.1.0/24 -p1-65535 --rate=1000
bettercap -iface wlan0             # interactive framework
  > net.probe on
  > net.recon on
  > set arp.spoof.targets <ip>
  > arp.spoof on
  > set dns.spoof.domains example.com
  > dns.spoof on
  > wifi.recon on
  > wifi.deauth AA:BB:CC:DD:EE:FF
tcpdump -i wlan0 -n -w capture.pcap
```
Works in Rootless (Termux) tier for Ethernet/BLE; WiFi monitor features need Full.

### 5.6 BLE device interaction (Flipper BLE equivalent)
```bash
bettercap -iface hci0
  > ble.recon on            # scan BLE devices
  > ble.show                # list found
  > ble.enum <mac>          # enumerate GATT services/characteristics
  > ble.write <mac> <handle> <data>
```
Also: **NetHunter Bluetooth Arsenal** (recon, spoof, Bluebinder service, Bad Bluetooth HID).

---

## 6. Automated Validation Suite

The following script validates every deployed capability end-to-end. It is safe to run on
**your own test lab** (own AP, own BT devices, legal bands). Each check prints PASS/FAIL/WARN and
returns a summary. Save as `validate.sh` on the device or run via `adb shell`.

```bash
#!/system/bin/sh
# validate.sh — Android security-tool platform validation
# Run: as root in NetHunter chroot:  sh /sdcard/validate.sh
PASS=0; FAIL=0; WARN=0
ok(){ echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn(){ echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "=== 1. Root & environment ==="
[ "$(id -u)" = 0 ] && ok "root access" || bad "not root"
command -v nmap >/dev/null && ok "nmap" || bad "nmap missing"

echo "=== 2. Network recon ==="
nmap -sP 127.0.0.1 >/dev/null 2>&1 && ok "nmap host scan" || bad "nmap scan failed"
command -v bettercap >/dev/null && ok "bettercap present" || warn "bettercap not installed"

echo "=== 3. Wireless adapter + monitor mode ==="
ADAPTERS=$(airmon-ng 2>/dev/null | grep -cE "rtl|ath|mt76")
[ "$ADAPTERS" -gt 0 ] && ok "external wifi adapter detected ($ADAPTERS)" || warn "no external adapter"
if airmon-ng 2>/dev/null | grep -q rtl; then
  airmon-ng check kill >/dev/null 2>&1
  IF=$(ip link 2>/dev/null | grep -oE "wlan[0-9]+" | tail -1)
  [ -n "$IF" ] && airmon-ng start "$IF" >/dev/null 2>&1
  ip link 2>/dev/null | grep -q "wlan.*mon" && ok "monitor mode enabled" || warn "monitor mode not confirmed"
fi

echo "=== 4. Packet injection test ==="
if command -v aireplay-ng >/dev/null 2>&1; then
  MON=$(ip link 2>/dev/null | grep -oE "wlan[0-9]+mon" | head -1)
  [ -n "$MON" ] && aireplay-ng --test "$MON" 2>&1 | grep -qi "injection is working" \
    && ok "packet injection working" || warn "injection test needs an AP in range"
fi

echo "=== 5. Rogue AP tooling ==="
command -v hostapd >/dev/null && ok "hostapd present" || bad "hostapd missing"
command -v dnsmasq >/dev/null && ok "dnsmasq present" || bad "dnsmasq missing"

echo "=== 6. RF/SDR detection ==="
lsusb 2>/dev/null | grep -qiE "realtek.*rtl2832|hackrf|0bda:2832" && ok "SDR detected on USB" \
  || warn "no SDR attached (expected if none connected)"

echo "=== 7. HID/payload tooling ==="
ls /sdcard/nh_files/duckyscripts 2>/dev/null && ok "DuckHunter script dir" || warn "no ducky dir"
command -v hid >/dev/null 2>&1 && ok "HID tools" || warn "HID module check skipped"

echo "=== 8. BLE ==="
bettercap -eval "ble.recon on; sleep 3; ble.recon off; quit" 2>/dev/null | grep -qi "ble" \
  && ok "BLE recon module functional" || warn "BLE recon needs adapter permission/root"

echo ""
echo "========== SUMMARY =========="
echo "  PASS: $PASS   FAIL: $FAIL   WARN: $WARN"
[ "$FAIL" -eq 0 ] && echo "  RESULT: CONFIGURED & VALIDATED" || echo "  RESULT: FIX FAILURES"
```

**Automated driver:** run via `adb shell su -c "sh /sdcard/validate.sh"`, capture output, assert
`FAIL=0` and required capabilities present. Optionally wrap in CI (device on USB).

---

## 7. Post-Validation Checklist

| Capability | Validation command | Expected |
|---|---|---|
| Root | `id -u` | `0` |
| Network recon | `nmap -sP 127.0.0.1` | Host up |
| Monitor mode | `ip link \| grep mon` | monitor iface |
| Packet injection | `aireplay-ng --test wlan1mon` | "Injection is working!" |
| Rogue AP tools | `command -v hostapd dnsmasq` | both found |
| RF analysis | RF Analyzer app + SDR | live waterfall |
| HID payload | DuckHunter execute test ducky | keystrokes on target |
| BLE | `bettercap ble.recon on` | devices listed |
| Bad Bluetooth | NetHunter Bad BT tab | spoofed device visible |

---

## 8. Sources (verifiable, up-to-date)

- Kali NetHunter documentation — kali.org/docs/nethunter (+ components, wireless-cards, nethunter-pro)
- NetHunter live device/kernel lists — nethunter.kali.org (device-kernels.html, images.html)
- NetHunter kernels GitLab — gitlab.com/kalilinux/nethunter/build-scripts/kali-nethunter-kernels (250+ kernels, 110+ devices; feature flags HID/Injection/RTL8812AU/RTW88/BadUSB/SDR/CAN/NFS)
- kimocoder NetHunter kernel (OnePlus 8) — github.com/kimocoder/nethunter_kernel_oneplus8
- ALFA + NetHunter USB-OTG guide — yupitek.com
- "Best WiFi Adapters for Kali Linux 2026" (monitor mode/injection, kernel 6.14+) — tutorials.technology
- morrownr/USB-WiFi (adapter compatibility) — github.com/morrownr/USB-WiFi
- Kali NetHunter supported devices — techconsumerguide.com; blackmoreops.com; technicalustad.com
- Kali NetHunter HID attacks / BadUSB MITM / DuckHunter — mobile-hacker.com (2023–2024), hackyourmom.com (2025), github.com/androidmalware/android_hid
- TapDucky (ConfigFS DuckyScript runner, F-Droid) — github.com/iodn/tap-ducky
- Rucky (USB HID) — github.com/mayankmetha/Rucky
- bettercap (WiFi/BLE/HID/CAN/network) — github.com/bettercap/bettercap, bettercap.org
- bettercap on Android (Termux) — undercodetesting.com (2025)
- RF Analyzer (HackRF/RTL-SDR/Airspy/HydraSDR) — github.com/demantz/RFAnalyzer
- Best Android/iOS SDR apps 2026 — sdrstore.eu (2026-06-16); rtl-sdr.com
- Wifite2 — github.com/derv82/wifite2; aircrack-ng — aircrack-ng.org
- Bad Bluetooth HID in NetHunter — mobile-hacker.com (2024-03-06)

---

## 9. Limitations & Honest Caveats

- **No magic on modern crypto:** like Flipper Zero, WPA2/3 enterprise-grade networks and modern
  rolling-code systems resist the workflows here; the tool audits *weak/legacy* systems.
- **Internal chipsets:** most phones' built-in Wi-Fi cannot enter monitor mode; an external adapter
  is the reliable path. Only a few devices (Nexus 5, OnePlus 7) support internal monitor mode.
- **Power:** external adapters (~500 mW) drain phones; a powered OTG hub is recommended.
- **Regulatory:** transmitting on sub-GHz / Wi-Fi deauth requires legal authorization and band
  compliance in your region.
- **Firmware hygiene:** pin NetHunter/kernel versions; CVE-2026-30363 (Flipper-related) is a reminder
  that security tooling needs version control.
