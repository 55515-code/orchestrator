# iPhone Agent Actions — Phase C/D Validation Report

**Date:** 2026-08-07
**Phase:** Implementation → Validation (Phase 2 of the iPhone-Controllable Local Agent plan)

---

## Implementation complete

| # | Action | Result |
|---|---|---|
| 1 | Created `~/codespace/automation/actions.json` with 14 pre-defined actions | ✅ |
| 2 | Created `~/codespace/automation/run.sh` (resolves action → command + cwd, supports `%PROMPT%` substitution) | ✅ |
| 3 | Created `~/codespace/automation/ios-shortcuts-template.md` (Apple Shortcuts wiring) | ✅ |
| 4 | Created `~/.config/systemd/user/kilo-acp.service` (ACP server on 127.0.0.1:8765) | ✅ |
| 5 | Enabled + started `kilo-acp.service` (loopback only) | ✅ |
| 6 | Committed all 3 files to codespace repo (commit `ebde78c`) | ✅ |

---

## Live state (post-implementation)

```
~/codespace/automation/
├── actions.json          # 14 actions, JSON-valid
├── run.sh                # bash 3+, jq 1.8.2+ required
└── ios-shortcuts-template.md

~/.config/systemd/user/
├── kilo-remote.service   # from Phase 1 — Kilo chat agent (active)
└── kilo-acp.service      # NEW — Kilo ACP server, 127.0.0.1:8765 (active)
```

User systemd units: `kilo-remote.service` + `kilo-acp.service` both running.

---

## Functional verification

```
$ ~/codespace/automation/run.sh
Available actions (from /home/ahron/codespace/automation/actions.json):
  site_build — Build the 1pointo Astro site
  site_deploy_preview — Deploy site to Cloudflare Pages
  site_full — Build and deploy the 1pointo site
  substrate_status — List substrate workspace repos
  substrate_validate_content — Check content queue + validation
  disk_usage — Show disk usage of main mounts
  memory_check — Memory + top processes by memory
  tailscale_status — Show Tailscale peer status
  git_pull_all — Pull all workspace repos in ff-only mode
  git_status_all — Show dirty files across all workspace repos
  ollama_models — List available Ollama models
  kilo_status — Status of Kilo services
  agent_session — Run a one-shot Kilo agent task with the given prompt
  headscale_links — Show Tailscale self-node info + MagicDNS
```

`run.sh disk_usage` returned real `df -h` output.
`run.sh --which disk_usage` prints the resolved command.
`run.sh nosuchaction` exits 3 with the list of valid actions.

`systemctl --user status kilo-acp.service` shows `active (running)` with 102.9 MB RAM.

---

## What the iPhone can do right now (no further work)

1. **Kilo iOS app** — chat with the agent on the host, get tool-using answers (Phase 1)
2. **Termius / Blink / Prompt on iOS** — SSH to `100.117.132.49` (Tailscale IP) and:
   - `~/codespace/automation/run.sh disk_usage` — quick disk check
   - `~/codespace/automation/run.sh memory_check` — RAM + top processes
   - `~/codespace/automation/run.sh site_full` — build + deploy 1pointo.com
   - `kilo run "<prompt>"` — one-shot agent task
3. **Apple Shortcuts** — wire any of the above to a button or "Hey Siri" trigger (template in `ios-shortcuts-template.md`)
4. **`kilo acp` on 127.0.0.1:8765** — for future `acpx`/Zed integration (no iPhone client speaks ACP yet, but the server is up)

---

## Known issues / follow-ups

- **`kilo run` errors with "default agent substrate-maintainer not found"** — the kilo.jsonc default agent is set to a name that doesn't match an installed agent. Fix: `kilo config set default_agent general` (or another available agent — see `kilo agent list`). This affects `agent_session` actions. Other actions (disk, memory, etc.) are unaffected.
- **MagicDNS still broken** — `tailscale status` warns about systemd-resolved/NetworkManager conflict. Workaround: use the IP `100.117.132.49` directly in Termius/Shortcuts. This blocks Layer C (Tailscale Funnel) until resolved.
- **`acpx` not installed** — only needed for headless ACP orchestration. Not required for the iPhone use cases. Install later if/when scheduled-task automation is added.

---

## What's next: the webapp

The user has now requested the next phase: a **webapp interface** to control the system from iPhone, with:

1. **Non-AI-dependent UX** — direct buttons, status panels, no LLM in the loop for routine actions
2. **Kilo + automation access** — embedded chat for free-form requests
3. **Web command-line shell** — terminal in the browser

This is Phase 3. I'll start deep research, planning, validation, QA, then implementation.
