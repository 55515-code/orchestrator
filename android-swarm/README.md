# Android Compute Swarm — sideloadable APK

**Package:** `com.substrate.nodemobile` · **App:** Substrate Node
**Min SDK 26** (Android 8.0), **target 36** (Android 16), no root, no dev mode.

## What it does

A single APK that makes the phone a compute node for the substrate swarm:

- Starts a **foreground service** (persistent notification, `dataSync` type).
- Announces **capabilities** (CPU cores, RAM, storage free, Vulkan/NPU probe, ABI, OS) on connect.
- Holds a **WebSocket** to the gateway (`wss://…/compute/nodes/ws`). Receives task JSON (`{"type":"task","id":"…","kind":"echo","payload":"hello"}`) and echoes the result. Real dispatch (Vulkan/NNAPI) will replace the echo.
- Survives reboot via `BOOT_COMPLETED` receiver (Phase B adds WorkManager safety net + per-OEM battery-exemption deep-links).

Simpler than OpenClaw Android: one APK directly, no Termux/bootstrap/Node.js layer.

## Sideload on Android 16

1. Download `app-release.apk` from **Releases** (or build below).
2. On the phone: **Settings → Apps → Special app access → Install unknown apps → Files → Allow** (grant to the app you download with, e.g. Files or Chrome).
3. Tap the APK → Install → confirm. Then **revoke the grant**.

> If your device enforces the Aug-2026 "advanced flow" for unverified apps, use `adb install app-release.apk` (no 24 h wait for ADB). All other users see the normal per-app grant.

## Build locally

```bash
# optional — install the profile's deps
uv run python scripts/substrate_cli.py deps-ensure --profile android_lab --apply

./gradlew :app:assembleRelease
# APK at android-swarm/app/build/outputs/apk/release/app-release.apk

# (optional) verify signature locally
apksigner verify --print-certs android-swarm/app/build/outputs/apk/release/app-release.apk
```

CI can produce a debug APK with `./gradlew :app:assembleDebug` (no signing).

## Gateway tie-in

- Host stub: `substrate/compute_nodes.py` (`ComputeNodeRegistry`).
- Real route + control-panel page will be added in the next pass and will reuse the existing `substrate/gateway` + Tailscale + orchestrator.

## Verifying

- On the phone: open **Substrate Node** → **Start node** → capabilities line shows cores/RAM/storage + `GPU`/`NPU` probe → notification persists.
- On the host: `python -c "from substrate.compute_nodes import REGISTRY; print(REGISTRY.list_nodes())"` after wiring the WS route.

## Security

- Runs in the app sandbox; no `MANAGE_EXTERNAL_STORAGE`.
- Declares `android.hardware.npu` as `required=false` (NpuManager guidance).
- Network is `INTERNET` only for the gateway WS. No exported components.

