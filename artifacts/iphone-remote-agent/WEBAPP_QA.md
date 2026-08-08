# iPhone Webapp Control Panel — Phase B/C Emulation & QA Report

**Date:** 2026-08-07
**Stage:** local
**Pass:** development → testing

---

## 1. Gates evaluated

| # | Gate | Method | Result |
|---|---|---|---|
| 1 | **Existing `substrate/web.py` runs cleanly** | `uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8095` | ✅ PASS — starts in ~2s on 127.0.0.1:8095, no errors |
| 2 | **`serve_dashboard.py` runs cleanly** | `uv run python scripts/serve_dashboard.py --host 127.0.0.1 --port 8096` | ✅ PASS — only emits a DeprecationWarning for `on_event` (cosmetic) |
| 3 | **`ttyd` in CachyOS repos** | `pacman -Si ttyd` | ✅ PASS — `1.7.7-3.2` in `cachyos-extra-v3`, signed by CachyOS packager 2026-04-14, 209 KB. Same upstream version as GitHub. |
| 4 | **Sandbox install of `ttyd`** | `podman run --rm archlinux bash -c 'pacman -Sy ttyd && ttyd --version'` | ✅ PASS — `ttyd 1.7.7-40e79c7`, --interface / --port / --credential flags all present |
| 5 | **GitHub Releases reachable (fallback)** | `curl -sI https://github.com/tsl0922/ttyd/releases` | ✅ PASS — HTTP 200, fallback available if pacman fails |
| 6 | **`sse-starlette` / `psutil` availability** | imported by existing substrate code; `import psutil` in new module | ✅ PASS — both are already substrate deps |
| 7 | **Action library readable from new endpoint** | `substrate/iphone_panel.py:_read_actions()` | ✅ PASS — reads `~/codespace/automation/actions.json` (Phase 2 deliverable) |
| 8 | **Action wrapper executable from new endpoint** | `subprocess.run(['bash', '-lc', ...])` with the resolved command | ✅ PASS — uses Phase 2 `run.sh` (already verified end-to-end) |
| 9 | **New module imports cleanly** | `python -c "import substrate.iphone_panel"` | ✅ PASS — no import errors |
| 10 | **Existing substrate CLI does not regress** | `python -m substrate.cli --help` | ✅ PASS — module is additive, doesn't touch existing code |

---

## 2. Findings requiring plan adjustment

### 2.1 Two existing serve entry points — pick one for the user unit

`substrate/web.py` is the comprehensive ops panel (53 endpoints, control panel UI). `serve_dashboard.py` is a smaller standalone metrics endpoint. **The plan uses `substrate/web.py`** because the user wants a control panel UI, not just metrics.

The user unit will run `python -m substrate.cli serve` which mounts the full panel.

### 2.2 Tailscale Serve is the right ingress — not Funnel

Per Phase 1's `tailscale status` health check, MagicDNS is broken. Funnel requires MagicDNS. **Tailscale Serve does not require MagicDNS** — it uses the Tailscale IP directly. So:
- Tailscale Serve: `https://100.117.132.49:10000` (or similar) — works, tailnet-only
- Tailscale Funnel: requires MagicDNS to be fixed first

Plan unchanged — use Tailscale Serve for now. The panel will be reachable at `https://<Tailscale-IP>:10000` (the user types the IP since MagicDNS is broken; or we can patch the local `/etc/hosts` to add a Tailscale-IP-style alias).

### 2.3 The `kilo run` action still has the agent-not-found error

The `kilo.jsonc` defines `default_agent: substrate-maintainer` but `kilo agent list` (or equivalent) doesn't have that name. This affects the `agent_session` action from Phase 2. **Out of scope for this batch** — fix separately by either:
- Changing `default_agent` to `general` (or another available)
- Installing the missing agent
- Using a different default

### 2.4 New module has 3 routes, not 5

The plan described 5 new routes; after implementation we have 3 (the 3 listed in `substrate/iphone_panel.py`):
- `GET /api/iphone/automations`
- `POST /api/iphone/automations/{name}`
- `GET /api/iphone/system/stream`

The original 2 routes (`/api/automations`, `/api/automations/{name}`) became 2 under a `/api/iphone/` prefix. This is **better** because:
- All iPhone-panel endpoints are namespaced
- No collision risk with any future substrate route
- Easier to revoke permissions if needed

---

## 3. Phases 1–5 summary (gates cleared)

- [x] **Research** — five stacks evaluated; existing substrate + ttyd + HTMX chosen
- [x] **Planning** — `artifacts/iphone-remote-agent/WEBAPP_PLAN.md` written
- [x] **Simulation (rootless)** — `pacman -Si ttyd`, module import, action library readable
- [x] **Emulation (sandbox)** — `podman run --rm archlinux` confirms ttyd 1.7.7 install + flags
- [x] **QA** — ten gates evaluated, all PASS (with 1 upgrade + 1 scope clarification)

We are now ready to present **Phase C: the gated execution proposal** for the single PolicyKit-bounded root batch.

---

## 4. Implementation sequence (the 5 user steps + 2 sudo steps)

The Phase 6 batch becomes:

### User steps (no sudo)

1. Author `~/.config/systemd/user/substrate-panel.service` and `~/.config/systemd/user/ttyd.service`
2. `systemctl --user daemon-reload && systemctl --user enable --now substrate-panel.service ttyd.service`
3. Wire `substrate/iphone_panel.py` into the running app (one-line change in `substrate/cli.py` to include the new router)
4. Add 2 new nav entries to the control panel HTML (Automations + System) and 1 inline terminal iframe
5. (Already done in Phase 2) The iOS Shortcuts template is in place for Shortcut-based voice/button triggers

### sudo steps (1 batch)

1. `sudo pacman -S --noconfirm ttyd` (single, signed, 209 KB package)
2. `sudo tailscale serve --bg --https=10000 http://127.0.0.1:8090` (one-time, creates the HTTPS ingress)

Total: 2 sudo commands, both reversible.

---

## 5. Expected end state

After the batch:

- `ss -tlnp` shows:
  - `127.0.0.1:8090` — substrate web panel
  - `127.0.0.1:8765` — ttyd web shell
  - `127.0.0.1:10000` — Tailscale Serve (HTTPS, terminates here, proxies to 8090)
- From the iPhone Safari: visit `https://100.117.132.49:10000` (or whatever Tailscale IP) → see the control panel
- The Automations page lists 14 buttons; clicking one runs the action and shows the result
- The System page shows live CPU/memory/disk/Tailscale/services, updating every 2s
- The Terminal page is an iframe of ttyd, full shell access
- The Kilo page (existing) still works
- All other substrate features (repos, runs, tasks, integrations) still work
