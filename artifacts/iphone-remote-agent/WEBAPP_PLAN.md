# iPhone Webapp Control Panel — Phase A Plan

**Status:** Research → Planning (Phase A complete, awaiting simulation/emulation → gated execution)
**Date:** 2026-08-07
**Author:** Local Agent Substrate

---

## 1. Objective

The user wants a **webapp interface** accessible from their iPhone that:

1. Has a **non-AI-dependent UX** — direct buttons, status panels, dashboards. No LLM in the loop for routine actions.
2. **Integrates Kilo + automations** — chat-style and one-shot agent invocations.
3. **Includes a web command-line shell** — terminal in the browser.

The webapp must run on the CachyOS host, be reachable from the iPhone over Tailscale, and not weaken the host's security posture.

---

## 2. Research Summary (trusted, verified methods)

Five candidate stacks were surveyed against the constraints: *iPhone is the client, action runs on this host, must not weaken security, must be one PolicyKit-bounded root batch, must be always-on, must already have a foundation (Kilo + Tailscale + automation library from Phases 1 + 2).*

| # | Stack | Trust | Verdict |
|---|---|---|---|
| 1 | **Existing `substrate/web.py` control panel (FastAPI + Jinja2 + vanilla JS) + extension** | First-party in this repo | **Chosen — primary path.** Already built (1468 lines web.py, 3136 lines static, 3K-line HTML). Has command palette, dark theme, real-time updates, Repos/Runs/Tasks/Kilo pages. Tested: starts cleanly on `127.0.0.1:8090`. |
| 2 | **FastAPI + HTMX + SSE** | First-party (FastAPI, HTMX) | **Chosen — for live status panels and action buttons.** Modern pattern, server-rendered HTML fragments, EventSource for SSE, no client-side state. Per `oneuptime.com/blog/post/2026-01-25-build-realtime-dashboards-fastapi/view` and `medium.com/codex/building-real-time-dashboards-with-fastapi-and-htmx-01ea458673cb`. |
| 3 | **`ttyd` (C binary) + xterm.js** | First-party (tsl0922/ttyd, 11.7K stars, MIT) | **Chosen — for the web shell.** Single binary, real PTY, WebSocket, CJK + IME + ZMODEM + sixel. Per the comparison at `blit.sh/`, ttyd is the lightweight proven choice; blit.sh itself is overkill. |
| 4 | **`blit` (whole-machine browser workspace)** | First-party (Indent, MIT) | **Rejected** — too heavy (Wayland compositor, GUI streaming, agent API), single-binary installer via `curl | sh` is against the controlling policy (`prompts/iphone-bluetooth-transfer-integration.md` §2.4). |
| 5 | **`katulong` (WebAuthn-secured workspace)** | First-party (Dorky-Robot, Apache-2.0) | **Rejected** — interesting but new (2 stars, last commit May 2026), WebAuthn adds complexity we don't need (Tailscale identity already authenticates). |

**Bonus finding: the `substrate` repo already has `ttyd`-compatible shell run code** — `substrate/tooling.py:238` uses `subprocess.Popen(..., shell=True)` which can be wrapped in a PTY for the web shell.

**Sources verified (all 2026-current):**

- `https://fastapi.tiangolo.com/tutorial/server-sent-events/` — FastAPI has first-class SSE in 0.135.0
- `https://www.server-sent-events.com/backend-stream-generation-connection-management/python-fastapi-sse-implementation-guide/` — `sse-starlette` for ping + disconnect handling
- `https://github.com/tsl0922/ttyd?aid=recrNX4X7LREJmukJ` — `ttyd` v1.7.7, 11.7K stars, xterm.js, ZMODEM, sixel
- `https://tailscale.com/docs/reference/tailscale-cli/serve` — `tailscale serve` exposes local service to tailnet with auto-TLS via Tailscale identity headers (`Tailscale-User-Login`, etc.)
- `https://blit.sh/` — comparison table confirming ttyd is the lightweight choice; blit is overkill
- `https://github.com/Dorky-Robot/katulong` — WebAuthn-secured workspace, reviewed and rejected
- Internal substrate code: `substrate/web.py`, `substrate/dashboard/api.py`, `substrate/static/control-panel.{js,css}`, `substrate/templates/control-panel.html`

---

## 3. Architecture — The Three-Layer Webapp

```
┌──────────────────────────────────────────────────────────────────────┐
│ iPhone Safari (or any browser)                                       │
│                                                                       │
│  Top-level UI — the Substrate Control Panel                          │
│    ├── Overview / Metrics / Repositories / Runs / Tasks               │
│    ├── Kilo Code page (chat, embedded)        [existing]             │
│    ├── NEW: Automations page (action buttons) [extends]               │
│    ├── NEW: System page (live status panels)  [extends]              │
│    └── NEW: Terminal page (web shell)         [adds]                  │
│                                                                       │
│  Non-AI UX:                                                          │
│    - All buttons hit /api/automations/{name} — no LLM in the loop     │
│    - Status panels use EventSource (SSE) for live updates            │
│    - Web shell uses ttyd over WebSocket                                │
│                                                                       │
│  AI UX:                                                              │
│    - Kilo chat panel uses existing endpoints (kilo remote)            │
│    - "Ask agent" button uses /api/automations/agent_session            │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
                       │  Tailscale mesh (HTTPS via tailscale serve)
                       │  Tailscale identity headers (auto-auth)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ CachyOS host                                                          │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Systemd user units (headless services)                        │  │
│  │                                                                │  │
│  │  kilo-remote.service    →  `kilo remote`   [Phase 1, active]  │  │
│  │  kilo-acp.service       →  `kilo acp`      [Phase 2, active]  │  │
│  │  substrate-panel.service →  `uvicorn substrate.web:app` NEW   │  │
│  │  ttyd.service           →  `ttyd bash`     NEW                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  `tailscale serve --https=10000 http://127.0.0.1:8090`                │
│    exposes the panel at                                               │
│    `https://cachyos-x8664.<tailnet>.ts.net:10000`                     │
│    with Tailscale identity headers (auto-auth).                       │
│                                                                       │
│  All services bind to 127.0.0.1 only.                                  │
│  Tailscale is the only ingress.                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Existing Control Panel (already built)

Pages found: `overview`, `metrics`, `repositories`, `runs`, `tasks`, `config`, `integrations`, `learning`, `kilo`, `whatsapp-setup`. Total 53 API endpoints. Already starts cleanly with `scripts/substrate_cli.py serve`.

### What's NEW in this phase

| Component | Type | Purpose |
|---|---|---|
| **Automations page** | NEW page | Direct buttons for each action in `~/codespace/automation/actions.json` — no LLM |
| **System page** | NEW page | Live SSE panels: CPU%, memory, disk, Tailscale status, Kilo services |
| **Web shell page** | NEW page | Embeds ttyd in an iframe or via a small FastAPI proxy to ttyd's WebSocket |
| **`/api/automations/{name}` endpoint** | NEW | `POST` runs `~/codespace/automation/run.sh <name>` and returns `{stdout, stderr, returncode}` as JSON |
| **`/api/system/stream` SSE endpoint** | NEW | Streams psutil metrics every 2s as server-rendered HTML fragments |
| **`substrate-panel.service`** | NEW user unit | Runs the existing `substrate/web.py` on `127.0.0.1:8090`, auto-restart |
| **`ttyd.service`** | NEW user unit | Runs `ttyd --port 8765 --interface 127.0.0.1 bash` |
| **Tailscale Serve config** | NEW | `tailscale serve --bg --https=10000 http://127.0.0.1:8090` exposes the panel |

---

## 4. Package Selection

| Component | Source | Trust | Verdict |
|---|---|---|---|
| `ttyd` | AUR or `pacman` (extra) | First-party (tsl0922, MIT, 11.7K stars) | Try `pacman -S ttyd` first. If not in CachyOS extra-v3, fall back to pre-built binary release. |
| `sse-starlette` | already a dep of substrate (via FastAPI) | First-party | No new install. |
| `psutil` | already a dep of substrate (per `substrate/dashboard/api.py` patterns) | First-party | No new install. |
| `substrate-panel.service` | user unit | internal | New file. |
| `ttyd.service` | user unit | internal | New file. |

**Investigation needed:** confirm `ttyd` is in CachyOS repos. If not, two options:
- (A) Build from source: `git clone https://github.com/tsl0922/ttyd && cd ttyd && mkdir build && cd build && cmake .. && make && sudo make install` (no AUR helper, no `curl | sh`).
- (B) Download signed release binary from GitHub Releases (signed by the maintainer, MIT) to `~/.local/bin/`.

Both are first-party sources.

---

## 5. Configuration Plan

### 5.1 `~/.config/systemd/user/substrate-panel.service` (new)

```ini
[Unit]
Description=Substrate Control Panel (webapp for iPhone)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ahron/codespace
ExecStart=/home/ahron/.local/bin/uv run --project /home/ahron/codespace python -m substrate.cli serve --host 127.0.0.1 --port 8090
Restart=on-failure
RestartSec=5
Environment=SUBSTRATE_PANEL_HOST=127.0.0.1
Environment=SUBSTRATE_PANEL_PORT=8090

[Install]
WantedBy=default.target
```

### 5.2 `~/.config/systemd/user/ttyd.service` (new)

```ini
[Unit]
Description=ttyd — web shell for the iPhone webapp
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ttyd --port 8765 --interface 127.0.0.1 --writable bash
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

### 5.3 New page additions to `substrate/templates/control-panel.html` (additive, 2 new pages)

- **Automations** page: list of buttons, each POSTs to `/api/automations/{name}`, displays result in a card
- **System** page: SSE-driven live panels for CPU, memory, disk, Tailscale, Kilo services

### 5.4 New endpoints in `substrate/web.py` (additive, 3 new routes)

- `POST /api/automations/{name}` — runs `~/codespace/automation/run.sh {name}` and returns JSON
- `GET /api/system/stream` — SSE endpoint streaming psutil metrics every 2s
- `GET /api/automations` — returns the list of available actions from `actions.json`

### 5.5 Tailscale Serve config (added via CLI, no file)

```
tailscale serve --bg --https=10000 http://127.0.0.1:8090
```

This makes the panel reachable at `https://cachyos-x8664.<tailnet>.ts.net:10000`. Tailscale identity headers are auto-injected, so the panel can use them for auth (we'll wire that in too).

### 5.6 (Optional) `kilo.jsonc` addition: add `kilo-web` to default services

Not strictly required — the Kilo page in the existing control panel already works.

---

## 6. Dependency & Closure Analysis

Resolved install set on CachyOS:

- `ttyd` (or downloaded binary) — ~2 MB compiled
- 2 new user units (no package)
- 2 new HTML pages (additive to existing template, ~200 lines)
- 3 new API routes (additive to existing `substrate/web.py`, ~150 lines)
- Tailscale Serve config (one CLI command, no file)
- (Optional) `psutil` — already a dep of substrate

This is a no-OS-package batch if `ttyd` is in CachyOS repos. If not, we need to install ttyd (sudo required, single batch).

---

## 7. Simulation Method (Phase B, rootless)

1. `pacman -Si ttyd` (print info only)
2. `podman run --rm archlinux bash -c 'pacman -Sy ttyd && ttyd --version'` (full install in container, confirm version)
3. `podman run --rm archlinux bash -c 'pacman -Sy nodejs npm && git clone https://github.com/tsl0922/ttyd && cd ttyd && cmake .. && make && ./build/ttyd --version'` (fallback: build from source in container)
4. **Boot the existing `substrate/web.py` in a container** with the new pages and endpoints stubbed in, verify it serves and the SSE endpoint streams.
5. **Test the action endpoint** with `curl -X POST http://127.0.0.1:8090/api/automations/disk_usage` and verify JSON shape.
6. **Test ttyd** with a mock client, confirm PTY streams back.

---

## 8. Risk Register (per step)

| Step | Impact | Severity | Mitigation |
|---|---|---|---|
| 1 (ttyd install) | 2 MB binary, depends on glibc, openssl. No conflicts. | **Low** | `pacman -Rns ttyd` reverts. |
| 2 (user units) | 2 services start, ~30 MB RAM combined. | **Low** | `systemctl --user disable --now` reverts. |
| 3 (HTML pages) | 2 new pages added. Existing 10 unchanged. | **Low** | `git checkout -- substrate/templates/control-panel.html` reverts. |
| 4 (API routes) | 3 new routes. Existing 53 unchanged. | **Low** | `git checkout -- substrate/web.py` reverts. |
| 5 (Tailscale Serve) | Adds HTTPS listener on Tailscale IP :10000, proxying to 127.0.0.1:8090. **Public key is your Tailscale identity** — no new auth needed. | **Low** | `tailscale serve --https=10000 off` reverts. |
| 6 (test) | Run actions from a non-LLM endpoint to confirm no surprise. | **Low** | No new state. |

---

## 9. Verification & Rollback

**Success criteria (post-implementation, observable from the iPhone):**

- [ ] From the iPhone Safari, `https://cachyos-x8664.<tailnet>.ts.net:10000` shows the control panel.
- [ ] The control panel shows "Logged in as: ahron" in the top-right (Tailscale identity header).
- [ ] Navigate to **Automations** → see ~14 buttons (site_build, disk_usage, etc.) → click `disk_usage` → see `df -h` output in a card, no LLM involved.
- [ ] Navigate to **System** → see live CPU%/memory/disk panels updating every 2s.
- [ ] Navigate to **Terminal** → see a working shell (ttyd in iframe) — type `ls -la` → see output.
- [ ] Navigate to **Kilo Code** → chat with the agent (existing flow from Phase 1).
- [ ] `ss -tlnp` shows the panel and ttyd only on 127.0.0.1.
- [ ] `tailscale serve status` shows the :10000 mapping.

**Rollback (in order, all rootless except `pacman -Rns`):**

```bash
# 1. tear down Tailscale Serve
tailscale serve --https=10000 off

# 2. stop the new user services
systemctl --user disable --now substrate-panel.service ttyd.service
rm ~/.config/systemd/user/substrate-panel.service ~/.config/systemd/user/ttyd.service
systemctl --user daemon-reload

# 3. revert the substrate changes
cd ~/codespace && git checkout -- substrate/web.py substrate/templates/control-panel.html substrate/static/

# 4. (if ttyd was installed) uninstall
sudo pacman -Rns ttyd
```

After rollback: no webapp reachable; Phase 1 (Kilo remote) and Phase 2 (action library) still work via SSH-over-Tailscale.

---

## 10. Lifecycle Alignment (3×3)

- **Stage:** `local` (this entire plan; the host is the host)
- **Pass:** `research` (this document) → `development` (sandbox emulation in Phase B) → `testing` (live, authorized host validation after the single PolicyKit gate)

---

## 11. What is explicitly OUT of scope for this single batch

- **Tailscale Funnel** (public internet access) — only the user's Tailscale identity reaches the panel; the rest of the internet doesn't. Public exposure would require Funnel + an additional auth layer, deferred.
- **Replacing ttyd with a custom web shell** — ttyd is the right tool, no need to reinvent.
- **Migrating the existing control panel to HTMX** — it's already a working app. We add to it, not replace it.
- **A new mobile-native app** — Safari works fine for the iPhone.
- **A new auth layer** — Tailscale identity is the credential. (If we ever expose publicly, we'll add auth then.)
- **Migrating to a different substrate repo path** — everything is at `~/codespace` and stays there.
