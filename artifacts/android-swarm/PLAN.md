# Android Compute Swarm — Phase A Plan (Multi-Device Resource Sharing)

**Date:** 2026-08-07 · **Pass:** research → **Stage:** local · **Status:** PLANNING (requires simulation/emulation before implementation)

---

## 1. What the user asked

*A side-loadable APK that runs on **any current Android device (Android 16), no root, no developer mode** that makes the phone/tablet a **compute node** — exposing its **NPU, GPU, CPU, RAM, storage** to the substrate "resource swarm." The node should be as simple to install as possible. Model reference: OpenClaw's Android terminal agent, but simpler.*

---

## 2. Research summary

### 2.1 Sideloading on Android 16 (2026)

| Fact | Source |
|---|---|
| Per-app "Install unknown apps" (since Android 8) still the mechanism. Grant to file manager/browser, drop APK, confirm, then revoke the grant. | `MobilityArena` sideloading guide |
| Google's new **24-hour "advanced flow"** for apps from unverified developers takes effect Aug 2026: multi-step auth/restart/wait. | `Android Authority` |
| **Bypass:** ADB sideload has **no wait** at all (confirmed by `Mishaal Rahman`). Sideload Hub / anyapk model (local ADB via wireless debugging) also has no wait once paired. | `sam1am/anyapk` |
| **Best practice for this APK:** sign it with our own key + publish SHA-256 + use F-Droid or GitHub Releases. Play verification only affects Play-distributed APKs; direct sideload from our own site uses the normal flow, not the "unverified developer" flow. For a single org-distributed APK we are the "trusted source." | Research consensus |

**Implication:** a single sideloaded APK is the simplest install (one file, one system dialog). No need for companion helpers. If we ship the signer key alongside the repo, users can verify locally.

### 2.2 Compute access without root (Android 16)

| Resource | How to use it without root | Notes |
|---|---|---|
| **CPU + RAM** | Normal app threads + `WorkManager` / foreground service. Fully available. | Constraints: Doze/App Standby kill background work; OEM killers on MIUI/ColorOS/OnePlus/Huawei. Mitigations: foreground service + `WorkManager` 15-min safety net + per-OEM autostart deep-links; identical fixes documented by `Nataris` P2P swarm. |
| **Storage** | App-private storage is free; `SAF` for user-granted shared files. | No limitation. |
| **GPU (Vulkan compute)** | **Vulkan compute** via NDK, available since API 24; Android 16 requires Vulkan 1.4. Full control over shaders, fused attention kernels, etc. No root. | Android devs doc + `vulkan/compute` tutorial. Portable across Adreno/Mali; tune workgroup sizes per GPU. |
| **NPU** | **NNAPI** (deprecated in 15, still runs) *or* new **NPU Manager** (`com.android.npumanager`, Android 17+, AIDL HAL) for cooperative scheduling. Later: TFLite GPU delegate. | NNAPI is app-callable; vendor driver handles Hexagon dispatch. For Android 16, NNAPI path works; new manager is for Android 17 devices. |
| **TFLite + delegates** | `tflite-gpu` delegate covers most ops now. | Good fallback if Vulkan code path is not yet wired. |

**Key references**

- Vulkan compute on Android (NDK): <https://developer.android.com/guide/topics/renderscript/migrate/migrate-vulkan> + <https://docs.vulkan.org/tutorial/latest/Advanced_Vulkan_Compute/12_Mobile_and_Embedded_Compute/02_android_compute.html>
- Android NNAPI overview: <https://developer.android.com/ndk/guides/neuralnetworks> (NNAPI is deprecated in 15; NPU Manager is the successor)
- New NPU Manager for Android 17: <https://source.android.com/docs/core/perf/npu-manager> (`NpuManager.requestCanLoadModel` flow)
- Fused Vulkan attention (actual 2× speed on mobile): <https://mvpfactory.io/…/custom-vulkan-compute-kernels…>
- P2P phone swarm that already runs inference on Android without root: <https://dev.to/vishal_sharma_nataris/we-built-a-p2p-ai-inference-network…>

### 2.3 Existing swarm / compute-node patterns

| Pattern | Relevance |
|---|---|
| **Nataris** (P2P phone inference marketplace, 21 devices, WebSocket + WorkManager) | Best model for battery/OEM-killer mitigations (watchdogs, WorkManager safety net, deep-links). |
| **OpenClaw Android** (`Mohd-Mursaleen/openclaw-android` — native Termux, no proot; `AidanPark/openclaw-android` — glibc+Node, embedded APK with Linux bootstrap; `Friuns2/claw-code-android` — Claw Code Mobile with embedded bootstrap, 4-layer APK) | Termux models require an app store install (F-Droid/Play) + large bootstrap; simplest is single-APK with embedded bootstrap. |
| **Espresso3389/methings** (APK exposes every hardware capability as `127.0.0.1:33389` HTTP endpoints for the agent) | Best model for "expose NPU/GPU/CPU/storage/memory as HTTP endpoints." Self-contained APK, no root. |
| **0x01-a2a/mobile + TadB0x/pezhvakp2p** (`jniLibs` trick: native `lib*.so` packaged in APK installs to `nativeLibraryDir` with exec) | Model for bundling native binaries (llama.cpp, vllm halves) without root — they run from `nativeLibraryDir`. |

### 2.4 OpenClaw Android terminal agent vs. simplest APK

OpenClaw Android requires: `pacman`/`glibc-runner`/Node v22/Bun/python/make/cmake/clang on Termux *or* an embedded Linux bootstrap (hundreds of MB, 10–30 s boot). Fun, but the "Termux→OpenClaw" layer is exactly the complexity the user wants to **skip**.

The simpler sibling is:

> **A standalone APK (Kotlin + NDK) that is the node:**
> - Single file, Install unknown apps, done.
> - Foreground service keeps it alive; WebSocket/MQTT/WebRTC to the substrate gateway.
> - HTTP loopback device-API (like methings: `127.0.0.1:<port>` exposes camera, sensors, filesystem, shell).
> - Small native library(s) in `jniLibs` for Vulkan compute + NNAPI if we add model work.

This is strictly simpler for users (one APK, no bootstrap, ~2 s start). It reuses everything the repo already does on the gateway side (FastAPI gateway in `substrate/gateway`, Tailscale, orchestrator).

---

## 3. Constraints & non-goals

- **Runs on Android 16 (API 36), no root, no developer mode.** Test target: real device (Pixel 8/9 class, Adreno 7xx or Mali-G715).
- **Single APK, sideloadable**, reproducible build.
- **Will NOT** bundle a 4-GB model in the APK. Models are downloaded on demand (opt-in), like `megatron-lm` do on first task.
- **Beats of non-goal:** full productivity app, editor, browser stack — those belong in `methings` territory.

---

## 4. Proposed architecture

### 4.1 Android node (APK)

```
┌──────────────────────────────────────────────┐
│ Android app  com.substrate.nodemobile        │
│  Kotlin UI + ForegroundService               │
│  ├─ ControlPlane  — persistent WS to gateway │
│  │   ├─ heartbeat / capability announcement  │
│  │   ├─ task envelope (job JSON, code to run)│
│  │   └─ result / progress / telemetry back   │
│  ├─ DeviceAPI  (loopback HTTP like methings)│
│  │   GET /capabilities, POST /infer,         │
│  │   GET /sensors, GET /storage, /cpu        │
│  ├─ Compute                                │
│  │   ├─ Vulkan (GPU) — future custom kernels │
│  │   ├─ NNAPI → NPU (and later NpuManager)  │
│  │   └─ CPU fallback                        │
│  ├─ Battery/OEM guards                      │
│  │   ├─ ForegroundService + notification     │
│  │   ├─ WorkManager 15-min reconnect net    │
│  │   ├─ BootReceiver (RECEIVE_BOOT_COMPLETED)│
│  │   └─ Per-OEM whitelisting deep-links      │
│  └─ nativeLibs (jniLibs/arm64-v8a/)         │
│      └─ small JNI bridge for Vulkan/NNAPI   │
└──────────────────────────────────────────────┘
```

### 4.2 Host / gateway side

- New substrate gateway route: `/compute/nodes` (registry) + `/compute/dispatch` (push a task to a node) + `/compute/capabilities` (inventory). Substrate side is pure Python — shown in `substrate/dashboard` + `substrate/gateway` patterns.
- Substrate orchestrator (`substrate/orchestrator.py`) treats phone nodes as a **capability-tagged executor pool** — dispatch with `capability IN {cpu,gpu,npu,storage}`.

### 4.3 Messaging & networking

- **Phase 1 transport:** persistent WebSocket to gateway (Tailscale or public host port). Simple, debuggable.
- **Phase 2 transport:** WebRTC data-channel / EtdmNet-style P2P mesh if we scale past a few nodes. Defer — one WS is enough to prove the loop.

### 4.4 Compute dispatch policy

- Gateway keeps a node registry (heartbeat + RAM/CPU/GPU/NPU caps).
- Task declares desired capabilities and a deadline.
- Scheduler picks the cheapest matching node (least-busy / most-ram / pinned-OS).

### 4.5 Security

- Token-based node enrollment (Tailscale identity when possible; otherwise generated node token in `SharedPreferences`).
- Capabilities are reported by the node; gateway validates by running a tiny probe (allocates 1 buffer on the claimed accelerator).
- App declares `android.hardware.npu` `required=false` (new NPU Manager guidance).

---

## 5. What we will build (Phase B/C — after simulation)

### 5.1 Android project (`android-swarm/`)

```
android-swarm/
  app/
    src/main/{AndroidManifest.xml, java/com/substrate/nodemobile/{…}}
    src/main/jniLibs/arm64-v8a/           ← native libs (built via NDK)
    cpp/  (small JNI bridge + Vulkan probe)
    build.gradle.kts
  build.gradle.kts
  settings.gradle.kts
  gradle.properties
  README.md                               ← sideload steps + verify SHA
```

Build with `gradle assembleRelease` → APK at `android-swarm/app/build/outputs/apk/release/app-release.apk`.

### 5.2 Gateway extension (under `substrate/`)

- One new module: `substrate/compute_nodes.py` (registry, lifecycle, metrics).
- Exposed via `substrate/dashboard` + `substrate/gateway` routes + a small panel page in `substrate/static/control-panel.*`.

### 5.3 Substrate integration

- `workspace.yaml` task `android_compute_node_sim` (mock node in Python, tests without a phone).
- `tool_profiles.yaml` entries for Android SDK/Gradle already exist — extend with `ndk_version`/`vulkan`.

---

## 6. Why not reinvent the wheel

We are **not** building a separate Termux bootstrap, a productivity app, or a new P2P protocol. We are using:

- the substrate's existing gateway + orchestrator,
- Tailscale identity (already on this host),
- standard Android APIs (Vulkan, NNAPI/NpuManager, foreground service, WorkManager),
- a normal sideloaded APK (one file, one grant).

All compute is exposed as the existing `/compute/*` HTTP + WS surface so existing chains/tasks can dispatch to the phone without new SDK code.

---

## 7. Success criteria (Phase 2 = after simulation, Phase 3 = after build)

- **Sideload on Android 16, no root, no dev mode.** Install→grant→confirm→revoke grant. Verified on a Pixel device.
- **Node heartbeat reachable from gateway.** `GET /compute/nodes` lists the phone.
- **Task round-trip.** Dispatch `{"kind":"echo","payload":"hello"}` → phone executes loopback handler → result returns and is visible in `control-panel`.
- **Compute proven.** The node exposes `{"gpu":"vulkan","npu":"nnapi","cpu":"ok","ram":N}` and a dispatched Vulkan probe succeeds (or falls back cleanly).
- **OEM guard exercise.** On a Xiaomi/ColorOS test device, foreground service survives 10 minutes without the WS dropping.

---

## 8. Gated work (what still needs approval before root/sudo)

Nothing needs root on the Android device. On the host, next steps are: install Android SDK/NDK + Gradle (via `scripts/substrate_cli.py deps-ensure --profile android_lab --apply`), run `gradle assembleRelease` in sandbox (`podman`+`openjdk` image), then install APK on the phone. No host root beyond normal package installs.

---

*Next steps:* validate SDK/NDK/Gradle toolchain in a `podman run --rm` sandbox (per `AGENTS.md` "System packages → podman"), then scaffold the `android-swarm/` project and gateway extension.
