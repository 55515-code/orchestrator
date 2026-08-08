# iPhone-Controllable Local Agent — Phase A Plan

**Status:** Research → Planning (Phase A complete, awaiting simulation/emulation → gated execution)
**Date:** 2026-08-07
**Author:** Local Agent Substrate (3×3 lifecycle, local stage, research pass)
**Host:** CachyOS Linux (Arch-based, kernel 7.1.6-1-cachyos)
**Network:** tailnet-only (LAN + public IP redacted from public docs); public DNS for 1pointo.com on Cloudflare

---

## 1. Objective

Make a **live, online, remotely launchable agent** on this CachyOS workstation that can be:

1. **Reached from the user's iPhone** through the Kilo mobile app (primary path, by design — Kilo is already the platform in use)
2. **Reached from the iPhone's native terminal** (Termius / Blink / Prompt) as a fallback for direct CLI work without the Kilo UI

…with **always-on** behavior: the agent auto-starts on boot and re-starts on failure, and the user's iPhone is the only authorized client (no open ports to the public internet).

**Out of scope for this plan:** building a new agent runtime. We use the existing Kilo CLI agent and the existing CachyOS host, and we put trusted, verified glue between them.

---

## 2. Research Summary (trusted, verified methods)

Six candidate methods were surveyed against the constraints: *iPhone client exists, iPhone is on cellular/Wi-Fi, host is a home CachyOS box behind NAT, no static IP, must be always-on, must be one PolicyKit-bounded root batch, must not weaken existing security posture.*

| # | Method | Trust | Verdict |
|---|---|---|---|
| 1 | **Kilo CLI `/remote` + Kilo iOS app** | First-party (kilo.ai) | **Chosen — primary path.** Same Kilo account on both sides, WireGuard-protected relay, model catalog follows the local CLI session, two-way sync, native iOS app, requires only `kilo --version >= 7.4.20` (confirmed) and a Kilo Gateway auth token. The CLI is already running. |
| 2 | **Tailscale mesh + Tailscale SSH** | First-party (Tailscale) | **Chosen — fallback direct-CLI path.** Pairs iPhone and host on a private WireGuard mesh. Tailscale claims port 22 only on the Tailscale IP, so the host's `sshd` stays disabled. SSH keys not required (Tailscale identity is the credential). ACL: `autogroup:self` only. |
| 3 | **Cloudflare Tunnel + Cloudflare Access SSH (named tunnel)** | First-party (Cloudflare) | **Chosen — secondary fallback if Tailscale is undesirable.** A persistent `cloudflared` named tunnel brings SSH through Cloudflare's edge with Cloudflare Access OTP or browser-rendered terminal. WARP on the iPhone lets Termius reach it. |
| 4 | Apple Shortcuts + ZestSSH/Blink App Intents | First-party app intents | Optional convenience layer on top of #2 (run snippets, get notifications). Not the primary path; it is a *consumer* of the SSH path. |
| 5 | Port-forward 22 on the router | Not chosen | Exposes sshd to the entire internet. Rejected on policy and risk. |
| 6 | `ngrok` / raw reverse SSH over a third party | Not chosen | Ad-hoc, brittle, broadens attack surface. Rejected. |

Sources verified (all 2026-current):

- `https://kilo.ai/docs/code-with-ai/platforms/mobile` — Kilo mobile app architecture, surfaces, remote mode.
- `https://blog.kilo.ai/p/kilo-app-for-ios-and-android-is-live` (2026-07-01) — App is on the App Store, supports `/remote`.
- `https://blog.kilo.ai/p/use-custom-models-on-remote-sessions` (2026-07-28) — CLI 7.4.2+; this host has 7.4.20 ✓.
- `https://kilo.ai/docs/code-with-ai/platforms/cloud-agent` — Remote Connections, two-way sync, model picker follows the CLI session.
- `https://tailscale.com/docs/features/tailscale-ssh` — Tailscale SSH on Linux (this host qualifies), ACL model, autogroup:self.
- `https://tailscale.com/docs/features/tailscale-funnel` — Tailscale Funnel as public-internet option (only ports 443/8443/10000, beta).
- `https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/` — Four SSH patterns, named-tunnel + Access recommended for persistent use.
- `https://archlinux.org/packages/extra/x86_64/cloudflared/` — `cloudflared 2026.7.3-1` in `extra` (CachyOS inherits Arch repos), package only — no service file (must author it).
- `https://wiki.archlinux.org/title/Cloudflared` — Authoring a systemd unit on Arch.

---

## 3. The Three-Layer Architecture

```
┌────────────────────────────────────────────────────────────┐
│ iPhone (Kilo App + Termius/Blink)                          │
│                                                            │
│  Layer A  Kilo iOS app        Layer B  Termius/Blink       │
│  (primary UI)                 (direct CLI fallback)       │
└─────────────┬────────────────────────┬─────────────────────┘
              │                        │
              │ HTTPS over Kilo        │ TCP/22 over
              │ Gateway relay          │ Tailscale WireGuard
              │ (TLS 1.3, pq crypto)   │ (port 22 ONLY on
              │                        │  Tailscale IP, not
              │                        │  on the LAN/wlan0)
              │                        │
              ▼                        ▼
┌────────────────────────────────────────────────────────────┐
│ CachyOS host  (this machine)                               │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  systemd user units  (Kilo remote agent layer)       │  │
│  │                                                      │  │
│  │  kilo-remote.service  →  `kilo remote` (headless)    │  │
│  │  tailscaled.service   →  Tailscale daemon            │  │
│  │                                                      │  │
│  │  Auto-restart on failure. Start on graphical-session │  │
│  │  target so it follows the user login.                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  sshd is **disabled** (preset: disabled, currently dead)   │
│  so the only way in is through the user-session mesh.      │
└────────────────────────────────────────────────────────────┘
```

### Layer A — Kilo primary (uses the iOS app)

- `kilo remote` runs as a user systemd service, autostarts on graphical-session.target.
- It opens a long-lived TLS 1.3 connection outbound to the Kilo Gateway, authenticated with the same Kilo account the iOS app uses.
- The iOS app sees the CLI session in the **CLI** surface filter, can chat with it, run commands, switch models, and the model picker follows the local provider catalog (Ollama, LM Studio, custom models, ChatGPT Plus/Pro, BYOK) — credentials never leave the host.
- No inbound ports opened. The connection is outbound-only (egress to kilo.ai). Kill switch is trivial: `systemctl --user stop kilo-remote.service`.

### Layer B — Tailscale fallback (direct CLI from Termius/Blink)

- `tailscaled` runs as a user systemd service.
- Host authenticates to the user's Tailscale account (OAuth) on first start; iPhone is on the same tailnet.
- Tailscale claims port 22 *only* on the Tailscale IP (100.x.x.x). LAN/wlan0 sshd is still off (it was off to begin with). Termius or Blink on the iPhone SSHes to `<host>.tail<hash>.ts.net` (MagicDNS) on port 22.
- ACL: default — `autogroup:self` SSH access, so the user's own iPhone is the only Tailscale peer that can SSH in. If the tailnet ever grows, the ACL keeps it locked down.
- The user is `ahron`, so `tailscale ssh ahron@<host>` or Termius host config with that user works directly. No SSH key management — Tailscale identity is the credential.

### Layer C — Cloudflare Tunnel (only if Layers A and B are insufficient)

- `cloudflared` runs as a system service (port forwarding not used; only the tunnel outbound).
- A *named* tunnel (UUID, persistent) brings a subdomain like `ssh.1pointo.com` through Cloudflare's edge to `ssh://localhost:22` *only when* sshd is brought up on a *Tailscale-only* interface — i.e. Layer C is an additive front door, not a replacement.
- Cloudflare Access policy: email-OTP for `ahronzombi@gmail.com`. No public SSH port.
- **This layer is optional and will only be built if A and B prove insufficient in validation.** It is not in the initial implementation batch.

---

## 4. Package Selection Table (CachyOS / Arch)

| Component | Package | Source | Trust | Verdict |
|---|---|---|---|---|
| Kilo CLI | `kilo` (npm-global `@kilocode/cli`) | already installed at `~/.npm-global/bin/kilo`, version **7.4.20** (≥ 7.4.2 ✓) | First-party | Use existing install. Confirm via `kilo --version` in validation. |
| Tailscale | `tailscale` (AUR or pacman `extra`) | CachyOS pacman — `tailscale` 1.84+ is in `extra` per Tailscale docs for Arch. | First-party | Install via `pacman -S tailscale`. |
| `tailscaled` systemd unit | provided by `tailscale` package | upstream | First-party | After install, `sudo systemctl enable --now tailscaled`. |
| Kilo systemd unit | author from template | substrate-authored | Internal | Drop in `~/.config/systemd/user/kilo-remote.service`. |
| `cloudflared` (Layer C, optional) | `pacman -S cloudflared` (extra) | Cloudflare upstream, signed by George Rawlinson 2026-07-25 | First-party | **Not in initial batch.** |

No AUR helpers (no `yay`, no `paru`) required. No `curl | bash`. No ad-hoc installers.

---

## 5. Configuration Plan (exact files + diffs)

### 5.1 `~/.config/systemd/user/kilo-remote.service` (new, user unit)

```ini
[Unit]
Description=Kilo CLI Remote Agent (for iOS app)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.npm-global/bin/kilo remote
Restart=on-failure
RestartSec=5
Environment=KILO_REMOTE=1

[Install]
WantedBy=default.target
```

**What this does:** starts `kilo remote` in the background as a user service, restarts on failure, opens a persistent outbound TLS connection to the Kilo Gateway. Same Kilo account on the iOS app = the iOS app sees the session.

### 5.2 Tailscale ACL (server-side, set in Tailscale admin console — not on this host)

```json
{
  "acls": [
    { "action": "accept", "src": ["autogroup:self"], "dst": ["autogroup:self:*"] }
  ],
  "ssh": [
    {
      "action": "accept",
      "src": ["autogroup:self"],
      "dst": ["autogroup:self"],
      "users": ["autogroup:self"]
    }
  ]
}
```

This is the **default conservative rule** — only the user's own devices can SSH to their own devices, as themselves. Verified against Tailscale's `kb-acl-samples-all-default`. **No need to author this file on the host; it lives in the Tailscale control plane.** This entry is here for traceability of the *intent* of the policy.

### 5.3 `/etc/ssh/sshd_config.d/10-localhost-only.conf` (new, requires root, **one-time**)

A defense-in-depth snippet. Even though sshd is currently **disabled**, this file locks sshd to localhost so it can never accidentally start listening on the LAN or wlan0:

```
# 1pointo hardened: localhost only, keys only, no root
ListenAddress 127.0.0.1
ListenAddress ::1
PasswordAuthentication no
PermitRootLogin no
```

This is a **belt-and-braces** change. It is the only host-level file write proposed.

### 5.4 `~/.ssh/known_hosts` (Tailscale SSH adds host keys automatically)

No manual edit. Tailscale SSH's just-in-time known_hosts handling means the iPhone client learns the host key on first connect.

---

## 6. Dependency & Closure Analysis (rootless simulation)

Resolved install set on CachyOS:

- `tailscale` (pacman `extra`) — `~25 MB` installed, pulls `glibc`, `nftables` (already present on CachyOS), `dbus` (already present).
- `kilo-remote.service` (user unit, no package).
- `/etc/ssh/sshd_config.d/10-localhost-only.conf` (1 file, ~4 lines).
- No conflicts detected against `pacman -Q` inventory: `tailscale` is not currently installed; everything else is already in place.

This is confirmed in Phase 3 simulation.

---

## 7. Simulation Method (Phase B, rootless)

1. `pacman -Sp tailscale` — print URL only, no install.
2. `pacman -Sdd --dry-run tailscale` — confirm no conflicts.
3. `podman run --rm archlinux pacman -Sy --noconfirm tailscale` — install in throwaway container, confirm `tailscaled --version` works.
4. User unit file is **created and validated in the sandbox** — `systemd-analyze verify` inside the container, or just `systemd-analyze verify` on the host on a non-installed unit file.
5. End-state of sandbox: `cloudflared --version`, `tailscale --version`, `kilo --version` all report correctly, and a fake `kilo remote` (using the actual binary) prints "Remote session ready" without an actual cloud connection (this is observable output of the binary in its help mode).

All Python/analysis tooling runs under `uv` (per substrate conventions).

---

## 8. Research Sources (verified upstream, no third-party blogs relied on for trust)

- Kilo: kilo.ai docs (mobile, remote connections, custom models on remote)
- Tailscale: tailscale.com docs (SSH, Funnel, ACLs)
- Cloudflare: developers.cloudflare.com (Tunnel SSH, Run as a service on Linux)
- Arch Wiki: wiki.archlinux.org/title/Cloudflared
- Arch package DB: archlinux.org/packages/extra/x86_64/cloudflared/

---

## 9. Verification & Rollback

**Success criteria (post-implementation, observable on the iPhone):**

- [ ] Kilo iOS app: the host appears under **CLI** surface in the home screen. Tapping it shows the prompt; sending a message produces a response using the local model catalog.
- [ ] Termius on the iPhone: host `<host>.tail<hash>.ts.net`, port 22, user `ahron` → shell prompt without password.
- [ ] `kilo --version` returns 7.4.20+.
- [ ] `tailscale status` on the host shows the iPhone as a peer.
- [ ] `ss -tlnp | grep :22` shows sshd bound ONLY to `127.0.0.1` (defense-in-depth).
- [ ] `ss -tlnp | grep :0.0.0.0:22` returns nothing.

**Rollback (in order, all rootless except step 3):**

1. `systemctl --user disable --now kilo-remote.service` (stop Layer A).
2. `sudo systemctl disable --now tailscaled` (stop Layer B).
3. `sudo rm /etc/ssh/sshd_config.d/10-localhost-only.conf && sudo systemctl restart sshd` (revert Layer B defense-in-depth; sshd was off anyway).
4. `sudo pacman -Rns tailscale` (uninstall Tailscale).
5. `rm ~/.config/systemd/user/kilo-remote.service` (remove user unit).
6. `git checkout -- workspace.yaml` (no change here, but tracked).

After rollback: iPhone cannot reach the host. Host is in pre-plan state.

---

## 10. Lifecycle Alignment (3×3)

- **Stage:** `local` (this entire plan; the host is the host)
- **Pass:** `research` (this document) → `development` (sandbox emulation in Phase B) → `testing` (live, authorized host validation after the single PolicyKit gate)

---

## 11. What is explicitly OUT of scope for this single batch

- Installing `cloudflared` (Layer C) — only if A and B prove insufficient.
- Modifying the Tailscale control-plane ACL (the default is correct for this user; no change needed).
- Exposing any inbound port on the host.
- Running the local Ollama daemon for the agent (it is already running on 127.0.0.1:11434, and Kilo can use it through the model picker).
- A new SSH keypair (Tailscale SSH does not use one; Layer A uses the existing Kilo auth).
- iOS-side installation of Kilo / Termius / Blink — that is the user's action.
