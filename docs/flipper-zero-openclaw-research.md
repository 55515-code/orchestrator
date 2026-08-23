# Flipper Zero Ecosystem & OpenClaw Hardware Agent — Research Report

**Research date:** 2026-08-22
**Scope:** Native Flipper Zero hardware/radio subsystems, compatible add-ons, firmware
mods & security tools, and OpenClaw persistent hardware-agent integration.
**Sources:** Flipper official docs (docs.flipper.net), TI CC1101 datasheet, ST ST25R3916,
Flipper community wiki, GitHub (FlipperAgent, flipper-rf-lab, ESP32 Marauder, esp-openclaw-node,
Momentum/Unleashed/RogueMaster), Bastille research, Sapsan/PINGEQUA/Lab401 vendor catalogs,
OSMOCON/IEEE papers. All claims labeled PROVEN / COMMUNITY-SUPPORTED / EXPERIMENTAL.

> **Legal/ethical note:** All capabilities below are for **authorized security testing
> and research** on systems you own or have written permission to assess. Transmission
> must comply with local spectrum regulations (e.g., FCC Part 15 in the US). Several
> jurisdictions (e.g., Canada) have considered or enacted restrictions on RF testing
> tools. Use within the law and scope of your engagement.

---

## 1. Native Flipper Zero Hardware & Radio Subsystems

### 1.1 Core platform

| Component | Specification |
|-----------|--------------|
| MCU | **STM32WB55RG** (dual-core: Arm Cortex-M4 @ 64 MHz + Cortex-M0+ @ 32 MHz) |
| Memory | 256 KB SRAM (shared app/radio), 1 MB flash |
| Storage | microSD (up to 64 GB) |
| Display | 1.4" monochrome LCD 128×64, 5-button D-pad, status LED |
| Connectivity | USB 2.0 Type-C, BLE |
| Power | Built-in battery, standby-optimized firmware |
| Openness | Fully open-source firmware + open hardware schematics |

Source: docs.flipper.net/zero/development/hardware/tech-specs; cybersteps.de.

### 1.2 Radio subsystems (native)

| Subsystem | Chip | Bands/Standards | Capabilities | Whitehat use cases |
|-----------|------|-----------------|--------------|--------------------|
| **Sub-GHz** | TI CC1101 | 300–348, 387–464, 779–928 MHz (common: 315/433/868/915); TX ~0 dBm, ~50 m | OOK/ASK/2FSK/GFSK; raw RX/TX, capture, replay, frequency analyzer | RF remote/gate/garage-door auditing; wireless sensor analysis; signal replay testing on owned systems |
| **NFC 13.56 MHz** | ST25R3916 | ISO-14443A/B, MIFARE Classic/Ultralight/DESFire, FeliCa, HID iClass (Picopass), NFC Forum | Read/write/emulate, key extraction (where algorithmically possible), LibNFC-compatible as USB device | Access-control auditing; NFC tag fuzzing; card-emulation testing |
| **RFID 125 kHz** | — (built-in LF) | EM4100, HID H10301/Prox, Indala 26, AWID, FDX-A/B, IoProx, Pyramid, Viking, Paradox, Gallagher, etc. | AM/OOK/ASK/PSK; read/write/clone/emulate T5577 and listed tags | Legacy proximity-card auditing (note: cannot defeat modern crypto — DESFire/HID iClass SE) |
| **Bluetooth LE** | Integrated in STM32WB55 | BLE 5.0, TX 0 dBm, RX −96 dBm, 2 Mbps | Host + peripheral modes, simultaneous connections | BLE device discovery/enumeration, peripheral emulation, mobile-app interaction |
| **Infrared** | — | RX 950 nm (±100), 38 kHz carrier; TX 940 nm, 300 mW, 0.2 MHz | Universal-remote library, capture/replay, raw IR | TV/AC/AV control-system assessment; IR remote auditing |
| **iButton / 1-Wire** | — | Dallas DS1990A, Cyfral | Read/write/emulate | TouchMemory key auditing (physical access) |
| **GPIO** | 13 user pins, 2.54 mm | 3.3 V CMOS (5 V tolerant), ~20 mA/pin; UART/SPI/I²C | Host-side debugging, UART/SPI/I²C bridge, fuzzing, module interface | Hardware debug, firmware flashing of attached boards, sensor/logic probing |
| **USB** | Type-C 2.0 | HID (keyboard/Ethernet), U2F, serial, qFlipper | BadUSB/Rubber Ducky scripts, U2F security key, CLI | Authorized HID testing, U2F assessment, automation via CLI |
| **2.4 GHz (Wi-Fi etc.)** | ❌ NONE natively | — | Requires external module (see §2) | — |

**Key limitation (important):** The Flipper Zero has **no Wi-Fi radio** and no general
2.4 GHz radio beyond BLE. Firmware cannot add radios; only hardware modules can.
Custom firmware unlocks *frequencies/features* the existing hardware already supports.

Sources: docs.flipper.net; flipper.wiki; jamisonderek/flipper-zero-tutorials (Sub-GHz wiki);
Bastille Wireless Research (bastille.net/research/flipper-zero); cybersteps.de spec table.

---

## 2. Compatible Hardware Add-Ons & Expansion Modules

### 2.1 Official

| Module | Chip | Adds | Setup |
|--------|------|------|-------|
| **Wi-Fi Devboard** | ESP32-S2 | 2.4 GHz 802.11 b/g/n Wi-Fi (scan/monitor/beacon/PCAP) | Dock on GPIO header (18-pin), open Wi-Fi app; pre-flashed; browser reflash (flash.pingequa.com) |

### 2.2 All-in-one multi-radio boards

| Board | Radios | Notes | Vendor/source |
|-------|--------|-------|---------------|
| **Feberis Pro** | 2× CC1101 (433/868), nRF24 (2.4 GHz), ESP32 Wi-Fi, GPS | Jumper-switched per band, tuned antennas; Marauder preinstalled | Sapsan (sapsan-sklep.pl) |
| **TwinWave** | ESP32-PICO-V3-02 (2.4 GHz) + CC1101 (433) | Dual radio, 2× SMA, independent power switches; Marauder v1.12.1; open hardware | 0xMartin/TwinWave (GitHub) |
| **End Game** | ESP32-S3 + CC1101 + nRF24 | 3-in-1, SD reader for PCAP, USB-UART bridge for flashing | ruckus // section80 (Tindie) |
| **WiFi 3-in-1 / 4-in-1** (various) | nRF24 + ESP32 + CC1101 | Budget Chinese multiboards, ~$10–56 | Tindie / AliExpress |
| **Scout Lite** | ESP32-C5 + L86 GPS | Wi-Fi 6 dual-band wardriving + WiGLE logging | PINGEQUA |
| **5Ghost** | BW16 RTL8720DN | Dual-band 2.4/5 GHz Wi-Fi | PINGEQUA |

### 2.3 Single-purpose radio modules

| Module | Purpose | Notes |
|--------|---------|-------|
| **External CC1101** (various) | Extended Sub-GHz range | Wired to SPI pins; firmware must detect it; data rates limited ~15–20 K vs 115 K internal |
| **Horizon 433 Pro** | Long-range 433 MHz | CC1101 + PA/LNA + SMA antenna |
| **nRF24 module** | 2.4 GHz peripherals | MouseJack testing, 2.4 GHz protocol analysis |
| **MAXIMUS CC1101 amplifier** | Sub-GHz TX amplification | Attaches to CC1101 |
| **GPS module** | Wardriving coordinates | Works with WiFi devboard/wardriving firmware |
| **IR Stealth / IR blaster** | Extended IR | Community boards (TehRabbitt etc.) |

### 2.4 Complementary (companion, not GPIO plug-ins)

| Device | Role |
|--------|------|
| **HackRF One + PortaPack H4M (Mayhem)** | 1 MHz–6 GHz SDR for full-spectrum analysis; pairs with Flipper for deep RF work |
| **Proxmark3** | Advanced LF/HF RFID/NFC tool; complements Flipper's card work |
| **RTL-SDR** | Cheap receive-only SDR for spectrum observation |
| **Prototype boards / GPIO breakout** | Custom hardware integration, breadboarding |

**Compatibility notes:** Most modules need **custom firmware** (Unleashed/Momentum/
RogueMaster) for full protocol support and external-radio detection. Match firmware
app version to board firmware. GPIO orientation matters (18-pin header); power off
Flipper before docking. Antenna choice is band-specific.

Sources: PINGEQUA catalog, Sapsan catalog, Tindie listings, TwinWave GitHub, hackmag.com
"Expanding Flipper Zero" (2026-06-18), cybersteps.de, lab401.com.

---

## 3. Firmware Mods & Authorized Security Tools

### 3.1 Firmware comparison (as of 2026-07)

| Firmware | Version | Base | Character |
|----------|---------|------|-----------|
| **Official** | 1.4.3 (2025-12-05) | — | Max stability, fewest extras, region-locked Sub-GHz TX |
| **Unleashed** | unlshd-090 (2026-07-30) | OFW | Stable community baseline; unlocked Sub-GHz range, extra protocols, external CC1101/nRF24 support |
| **Momentum** | mntm-012 (2025-12-31) | OFW+Unleashed features | Successor to Xtreme; most polished UI, JS app SDK, on-device customization |
| **RogueMaster** | RM0722 (2026-07-22) | Unleashed | "Kitchen sink" — most apps/plugins, least predictable stability |
| **Xtreme** | (archived 2024-11) | — | **Discontinued**; use Momentum (same devs) |
| **SquachWare / Xvirus** | — | OFW/Unleashed | Niche forks |

**Selection guidance:** Beginner/safety-first → Official. Balance → Unleashed.
UI/customization → Momentum. Everything bundled → RogueMaster (accept instability).
Firmware never adds radios — it unlocks frequencies and adds apps. Xtreme is dead;
Momentum is its successor.

### 3.2 Authorized security tooling / apps

| Tool | Purpose |
|------|---------|
| **flipper-rf-lab** (tworjaga) | Lab-grade RF analysis: device fingerprinting, protocol inference, threat scoring, 300–928 MHz spectrum monitoring, <1 μs timing, K-means clustering; MIT license |
| **Wi-Fi Marauder (ESP32)** | Wi-Fi scan/monitor/deauth/beacon/PCAP on ESP32-based modules (official devboard, Feberis, TwinWave, etc.); `FZEasyMarauderFlash` simplifies flashing |
| **flipperzero-bruteforce** | Sub-GHz brute-force replay on selected protocols |
| **FlipperAgent** (jonastbrg) | **MCP server + AI agent framework** for autonomous authorized pentest cycles with Flipper Zero over USB serial; 67+ tools across BLE/WiFi/Sub-GHz/IR/NFC/RFID; staged Recon→Research→Enumerate→Exploit→Report with explicit approval gates on HIGH-risk actions |
| **qFlipper / Mobile apps** | Firmware updates, asset management |
| **FlipperZero-guide** (Nicholas-Arcari) | Technical playbook for cybersecurity/physical pentest/RF analysis/hardware RE |
| **JavaScript SDK** (Momentum) | On-device scripting for custom tests |

**Workflow mapping (whitehat):**
- **RF signal analysis** → flipper-rf-lab + external CC1101/SDR
- **NFC fuzzing/auditing** → native NFC app + Proxmark3 companion
- **Bluetooth protocol testing** → BLE apps + FlipperAgent ble scripts (Bleak)
- **Infrared assessment** → IR app + universal remotes
- **Wi-Fi** → Marauder on ESP32 module
- **Full-cycle automation** → FlipperAgent MCP server

Sources: pingequa.com firmware guide (2026-07-31); github.com/DarkFlippers/unleashed-firmware;
github.com/Next-Flip/Momentum-Firmware; github.com/RogueMaster/flipperzero-firmware-wPlugins;
github.com/tworjaga/flipper-rf-lab; github.com/jonastbrg/FlipperAgent; awesome-flipper.com.

---

## 4. OpenClaw Node as a Persistent Hardware Agent

### 4.1 The OpenClaw node protocol (established, ESP32-class)

**esp-openclaw-node** (github.com/openclaw/esp-openclaw-node; also the `espressif/esp-openclaw-node`
ESP-IDF component v1.0.0) defines the reference pattern:

- Runs an ESP32 application as an **OpenClaw Node over WebSocket** to an OpenClaw gateway.
- **Identity:** Ed25519 seed persisted in NVS; `device_id = hex(sha256(public_key))`.
- **Connect paths:** setup-code, shared-token, password, no-auth, saved-session (auto-reconnect after Wi-Fi/gateway interruptions).
- **Capabilities/commands:** node advertises `caps` and `commands` (e.g., `device`, `wifi`, `gpio` with `device.info`, `wifi.status`, `gpio.read/set`).
- **Invocation:** gateway sends `node.invoke.request`, node executes and replies `node.invoke.result`.
- **Gateway-side verification:** `openclaw nodes status --json`, `openclaw nodes invoke --node <id> --command device.info --json`.

### 4.2 Embedded OpenClaw implementations (the ecosystem)

| Project | Language | Hardware | Notes |
|---------|----------|----------|-------|
| **MimiClaw** | C (bare metal) | ESP32-S3 (PSRAM) | Full ReAct loop, Telegram, persistent memory (SOUL/USER/MEMORY.md) |
| **PycoClaw** | MicroPython | ESP32 (S3/RP2350) | Full agent parity, GPIO/CAN/I2C/LVGL, ScriptoHub skills |
| **ESPClaw** | C (ESP-IDF) | ESP32/CAM/S3 | Extensible IoT agent runtime, installable Lua apps |
| **ZClaw** | C | ESP32 | Ultra-compact base |
| **DuckyClaw** | C (TuyaOpen SDK) | Tuya/ESP32 | Enterprise IoT fusion |
| **RoClaw** | — | ESP32-S3 + CAM | Robotics dual-brain |

These run on **ESP32-class hardware** (Wi-Fi/2.4 GHz) — the exact class of chip the
Flipper Zero's expansion ecosystem uses (Wi-Fi Devboard = ESP32-S2).

### 4.3 Integrating OpenClaw with the Flipper Zero (three viable patterns)

The Flipper Zero itself is an **STM32WB55** (no Wi-Fi, no Linux, no Node.js). The
practical integration paths, ranked by maturity:

**Path A — Companion ESP32 OpenClaw node + Flipper over GPIO (RECOMMENDED, PROVEN components)**
1. Use the **official Wi-Fi Devboard (ESP32-S2)** or a multi-radio board (Feberis Pro,
   TwinWave, End Game) as the physical OpenClaw node platform.
2. Flash **esp-openclaw-node** (or MimiClaw/PycoClaw/ESPClaw) onto the ESP32; pair it
   to your OpenClaw gateway over Wi-Fi (WebSocket, Ed25519 identity, auto-reconnect).
3. Expose the Flipper Zero to the node over the **GPIO UART/SPI link** — the same bus
   Marauder uses — so the node can drive Flipper apps, or use the Flipper as a
   radio peripheral (Sub-GHz TX/RX, NFC, IR) behind the node.
4. Result: an **always-on hardware agent** whose radio resources (Sub-GHz, NFC, IR,
   125 kHz, BLE via the Flipper; Wi-Fi via the ESP32) are callable as node commands.

**Path B — Host/MCP agent controlling Flipper over USB (PROVEN today)**
- **FlipperAgent** already implements an MCP server + agent that drives a Flipper Zero
  over USB serial with 67+ tools and staged, approval-gated workflow. Run an OpenClaw
  node (or the FlipperAgent skills under OpenClaw) on the host that owns the USB link.
- Simplest first deployment; the "node" is a host service with the Flipper attached.

**Path C — Native STM32 OpenClaw node on the Flipper itself (EXPERIMENTAL)**
- Port an OpenClaw node client (Ed25519 + WebSocket/TLS) into the Flipper firmware
  (FURI app framework). The STM32WB55 lacks Wi-Fi; connectivity would need BLE to a
  bridge or an ESP32 modem. Feasible but requires custom firmware development;
  not currently published.

### 4.4 Required hardware modifications & configuration (Path A — detailed)

**Hardware:**
- Flipper Zero + official ESP32-S2 Wi-Fi Devboard (or multi-radio board with ESP32).
- MicroSD (≥8 GB) in Flipper; antenna for the bands you test.

**Firmware:**
- Flash **Momentum or Unleashed** on the Flipper (external-CC1101 + nRF24 + app support).
- Flash **esp-openclaw-node** firmware on the ESP32 devboard (build via `idf.py` for
  `esp32s2`; includes serial REPL for setup). If a multi-radio board (Feberis/TwinWave),
  keep its Marauder build or dual-boot with the OpenClaw node image.

**Configuration:**
1. ESP32 node: `wifi set <ssid> <passphrase>` → `gateway setup-code <setup-code>` →
   `gateway connect` (setup code from OpenClaw gateway). NVS persists identity +
   reconnect session.
2. Gateway host: `openclaw nodes status --json` → confirm `online`.
3. Register capabilities on the node:
   - `device` (info/status)
   - `radio.subghz` / `radio.nfc` / `radio.ir` / `radio.rfid` — wrap Flipper CLI/scripts
   - `wifi` (ESP32) — scan/status
   - `gpio` — direct pin control
4. Invoke: `openclaw nodes invoke --node <id> --command radio.subghz.tx --params '{"freq":433920000,"data":"..."}'`.

**Exposing the full radio stack:** Because the Flipper + ESP32 pair already exposes
Sub-GHz (native + external CC1101), NFC, 125 kHz, IR, iButton, BLE (Flipper) and
Wi-Fi (ESP32), a node wrapping these as commands makes **all radio resources**
available to authorized workflows through a single persistent agent.

### 4.5 Security & safety gates

- Follow FlipperAgent's risk model: LOW (auto), MEDIUM (log rationale), HIGH
  (explicit user approval), BLOCKED (never: /int/ writes, key/priv access).
- Scope enforcement: node commands should require an authorized-engagement flag;
  restrict TX frequencies/power to legal bands.
- Firmware hygiene: pin versions (cf. CVE-2026-30363, CVSS 8.4 stack overflow in a
  flipperzero-firmware commit); control payloads and physical access.

---

## 5. Recommendation Summary

| Goal | Recommended path |
|------|------------------|
| Full whitehat RF toolkit | Flipper Zero + external CC1101 (range) + nRF24 (2.4 GHz) + ESP32 Wi-Fi board (Marauder) + HackRF One (deep spectrum) |
| Best firmware | **Momentum** (polish + features) or **Unleashed** (stability baseline) |
| RF analysis | flipper-rf-lab + SDR |
| Autonomous authorized pentest | **FlipperAgent** (MCP, 67+ tools, staged approval) |
| **Persistent OpenClaw hardware agent** | **Path A:** ESP32 (Wi-Fi Devboard) running **esp-openclaw-node**, paired to OpenClaw gateway, driving the Flipper over GPIO; all radios exposed as node commands. **Path B** (FlipperAgent over USB) as the fast first step. |

The components for a fully integrated, well-outfitted whitehat testing rig — Flipper
Zero as radio front-end, ESP32-class OpenClaw node as always-on agent — all exist and
are proven individually; the integration is a configuration project, not a research gap.

---

## 6. Sources

- docs.flipper.net (tech specs, sub-GHz, GPIO, modules)
- TI CC1101 datasheet; ST ST25R3916
- flipper.wiki; jamisonderek/flipper-zero-tutorials
- Bastille Wireless Research — Flipper Zero (2026-05-26)
- PINGEQUA — firmware guide (2026-07-31), module catalog; Sapsan-sklep — pentest guide (2026-06-03); lab401.com; Tindie
- hackmag.com — "Expanding Flipper Zero" (2026-06-18)
- github.com/DarkFlippers/unleashed-firmware; Next-Flip/Momentum-Firmware; RogueMaster/flipperzero-firmware-wPlugins
- github.com/tworjaga/flipper-rf-lab; github.com/jonastbrg/FlipperAgent
- github.com/openclaw/esp-openclaw-node (+ ESP-IDF component); espclaw.dev; agent-wars.com (PycoClaw/MimiClaw); ebee.com (ESP32 OpenClaw projects)
- IEEE 3ICT 2024 — Flipper deauth detection via HackRF One
- SentineOne/Sapsan — CVE-2026-30363
