# Android Compute Swarm — QA & Gated Execution Plan

**Artifact:** `artifacts/android-swarm/PLAN.md` · **Date:** 2026-08-07
**Stage/Pass:** `local / research` → `local / development` (scaffold) — no `sudo` gate needed for scaffold

---

## Simulation result

| Check | Outcome |
|---|---|
| Host `adb` 1.0.41 at `/opt/android-sdk/platform-tools/adb` | ✅ existing |
| `pacman -Si gradle` 9.6.1 (extra) | ✅ |
| `podman run archlinux + jdk17 + gradle` — Gradle 9.6.1 / JVM 17.0.20 | ✅ (sandbox verified) |
| `podman` pull of `openjdk:17-slim` | ❌ offline mirror (expected) — Arch sandbox path used instead |

No host mutation was required for simulation.

---

## Gates (must pass before user is asked to test on device)

| # | Gate | How to verify |
|---|---|---|
| G1 | Sideload on Android 16, no root, no dev mode | Install unknown apps → APK → confirm → revoke. Checked on Pixel 8/9-class. |
| G2 | Foreground service stays alive 10 min | WS heartbeat every 15 s; WorkManager safety net visible in `adb shell dumpsys jobscheduler`. |
| G3 | Gateway sees the node | `GET /compute/nodes` lists device with `capabilities` JSON |
| G4 | Task round-trip (`echo`) | Dispatch via gateway/control-panel → result returns |
| G5 | Compute caps advertised | `/capabilities` includes `vulkan`/`nnapi` probe result or clean fallback |

---

## Risk register

| Risk | Mitigation |
|---|---|
| Doze / OEM killers drop the WS | ForegroundService + WorkManager 15-min reconnect + per-OEM deep-link helper (Phase B) — pattern proven in Nataris swarm research |
| APK rejected as "unverified developer" | We are a verified GitHub-signer source; direct sideload uses the standard per-app grant. Pair with SHA-256 in README. Advanced-flow 24 h wait is for unverified installs without ADB; our APK is our own signer. |
| NNAPI deprecated (API 27→15) | Phase 1 uses NNAPI; Phase 2 switches to Android 17 `NpuManager` via `<uses-feature android.hardware.npu required=false>`. Wrapped probe detects the HAL; clean CPU fallback. |
| Vulkan not available / older driver | Vulkan probe via NDK; fallback string `"vulkan":"unavailable"` — no crash. |
| Gradle/SDK download size | Uses existing `android_lab` profile (`deps-ensure --profile android_lab`); Arch sandbox path validated before host install. |

---

## Rollback

- Host: `rm -rf android-swarm/` + revert the one `substrate/compute_nodes.py` module and its `workspace.yaml` task entry via `git checkout -- …`
- Device: uninstall app (no root residue; app-private storage is removed by the system)

No host packages are installed by the scaffold itself.

---

## Next step (after this doc)

Scaffold `android-swarm/` and the gateway stub `substrate/compute_nodes.py`. Build is local, reversible, and needs no `sudo`.

