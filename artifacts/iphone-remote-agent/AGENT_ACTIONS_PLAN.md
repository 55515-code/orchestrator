# iPhone Agent Actions — Phase A Plan

**Status:** Research → Planning (Phase A complete, awaiting simulation/emulation → gated execution)
**Date:** 2026-08-07
**Author:** Local Agent Substrate
**Scope:** Phone-initiated agent actions (terminal/desktop/file ops) on this CachyOS host
**Prerequisites:** Phase 1 complete — Tailscale mesh is up, Kilo remote is active on `100.117.132.49`

---

## 1. Objective

The user wants to **ask the agent from their iPhone to perform terminal or desktop actions** — not just chat with it. The agent must:

- Accept a request from the iPhone
- Decide what to do (the LLM reasoning part)
- Execute it on this local host (terminal commands, file ops, browser automation, etc.)
- Return a result to the iPhone
- Be repeatable and reliable

Examples the user wants to enable:
- "Run the security scan"
- "Rebuild and deploy the 1pointo site"
- "Compress these files"
- "Take a screenshot of the desktop"
- "Open this URL in Firefox"
- "Check disk usage"
- "Git pull the substrate repo"

---

## 2. Research Summary (trusted, verified methods)

Six candidate methods were surveyed. The constraints: *iPhone is the client, action runs on this host, must not weaken security, must be one PolicyKit-bounded root batch, must be always-on.*

| # | Method | Trust | Verdict |
|---|---|---|---|
| 1 | **Kilo iOS app + existing `kilo remote` agent** | First-party (kilo.ai) | **Already live (Phase 1).** This IS the primary path. The iOS app can chat with the agent, which can use tools (`bash`, `edit`, `read`) to perform any action. The model picker follows the local catalog. **No new install.** |
| 2 | **Apple Shortcuts + SSH-over-Tailscale → `kilo run` one-shot** | iOS native + First-party Tailscale SSH | **Chosen — voice/button-triggered one-shots.** iOS Shortcuts has a built-in `Run script over SSH` action. It can SSH into the Tailscale IP and invoke `kilo run "<prompt>"` (which uses the existing CLI to perform a one-shot agent task and exit). Siri/button triggers become real automation. |
| 3 | **Kilo ACP server + headless ACP client (`acpx`)** | First-party (`kilo acp`) + acpx.sh | **Chosen — scriptable / agent-orchestration path.** `kilo acp` runs a JSON-RPC-over-stdio Agent Client Protocol server (ACP v1 compliant). `acpx` is a headless ACP client that can drive sessions. Useful for: scheduled tasks, CI-like automation, webhooks. |
| 4 | **Apple Shortcuts + Tailscale Funnel → HTTPS → custom web action receiver** | iOS native + Tailscale | **Optional — only if Shortcuts SSH path proves limiting.** Funnel exposes an HTTPS endpoint at `cachyos-x8664.tail<hash>.ts.net` that proxies to a local action receiver. iOS Shortcuts `Get contents of URL` can hit it. More moving parts; defer. |
| 5 | **Tailscale SSH + tmux + manual agent session** | First-party | Useful for power users. The iPhone SSHes in via Tailscale, attaches to a long-running tmux session, and types into a `kilo` TUI. Already supported by Phase 1 setup. |
| 6 | **Port-forward 22 + external SSH** | Not chosen | Rejected — exposes host to internet. Tailscale SSH achieves the same without exposure. |

Sources verified (all 2026-current):

- `https://kilo.ai/docs/code-with-ai/platforms/cli` — `kilo acp` is first-class, takes `--cwd`, `--port`, `--hostname`, `--mdns`, `--cors`.
- `https://kilo.ai/docs/code-with-ai/platforms/cli-reference` — `kilo acp` options.
- `https://deepwiki.com/Kilo-Org/kilocode/13.3-acp-protocol` — Kilo's ACP implementation is full v1, used by Zed and acpx.
- `https://agentclientprotocol.com/protocol/v1/overview` — ACP is JSON-RPC 2.0 over stdio (or HTTP/WS for remote — work in progress).
- `https://acpx.sh/quickstart.html` — `acpx` is a headless ACP client with `acpx opencode exec`, `acpx opencode sessions new`, etc. Works with Kilo via the `opencode` adapter.
- `https://tailscale.com/docs/features/tailscale-funnel` — Funnel exposes ports 443/8443/10000 to the public internet via Tailscale relay, with auto TLS.
- `https://www.thoughtasylum.com/2026/05/27/triggering-macos-operations-remotely/` — Tailscale + Shortcuts + SSH pattern, well-established.
- `https://github.com/Kilo-Org/kilocode/issues/6766` — official confirmation: Kilo ACP works with `acpx opencode exec "..."`.

**Conclusion:** the **existing `kilo remote` setup (Phase 1) already covers the primary use case.** What we add is:

1. **`kilo acp` as a parallel headless server** for orchestration and SSH-driven one-shots
2. **A curated library of pre-defined prompts** ("snippets") that map common actions to concise invocations
3. **Apple Shortcuts setup** (user does this part) — iOS-side configuration; we provide the iOS Shortcuts template
4. **Tailscale Funnel** — optional, only if the iPhone needs to reach the host from outside Tailscale (cellular, no Tailscale app installed)

---

## 3. The Three-Layer Action Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ iPhone                                                        │
│                                                               │
│  Layer A       Kilo iOS app                                    │
│  (chat-driven) "fix the bug in substrate/tests"               │
│                → free-form LLM → tool calls → action          │
│                                                               │
│  Layer B       Apple Shortcuts                                 │
│  (button/Siri) "Hey Siri, run security scan"                  │
│                → SSH over Tailscale → kilo run "<prompt>"     │
│                                                               │
│  Layer C       Tailscale Funnel → HTTPS webhook               │
│  (external)    (anywhere, no Tailscale app needed)             │
│                → action-receiver on port 10000                 │
└──────────────┬──────────────────┬─────────────────┬───────────┘
               │                  │                 │
               ▼                  ▼                 ▼
┌──────────────────────────────────────────────────────────────┐
│ CachyOS host                                                   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  systemd user units (headless services)               │   │
│  │                                                       │   │
│  │  kilo-remote.service  →  `kilo remote` (chat)         │   │
│  │  kilo-acp.service     →  `kilo acp --hostname 127...` │   │
│  │  action-receiver.service →  FastAPI on 127.0.0.1:...  │   │
│  │                        (only reachable via Tailscale  │   │
│  │                         Funnel on port 10000)         │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  Tailscale mesh (Layer A & B use direct SSH on Tailscale IP)  │
│  Tailscale Funnel  (Layer C — public HTTPS)                   │
└──────────────────────────────────────────────────────────────┘
```

### Layer A — Chat-driven (already live, no change)

- iOS app → Kilo Gateway → local `kilo remote` session
- The agent reasons, picks tools (`bash`, `edit`, `read`), executes, returns results
- This is the **richest** path — the LLM can plan multi-step actions

### Layer B — Shortcut/voice-driven (NEW — needs iOS Shortcuts setup + `kilo acp` + one-shot `kilo run`)

- iOS Shortcut → "Run script over SSH" → `ssh ahron@100.117.132.49 'kilo run "fix the broken test in substrate"'`
- `kilo run` is a one-shot agent invocation: picks model, runs the prompt, returns the result, exits
- This is the **fastest** path for repeatable actions
- We ship a library of pre-defined "action" prompts the user can wire to Shortcuts

### Layer C — External HTTPS (OPTIONAL — only if A and B are insufficient)

- Tailscale Funnel exposes `cachyos-x8664.tail<hash>.ts.net:10000` to the public internet
- A small FastAPI/uvicorn action-receiver on `127.0.0.1:10000` accepts JSON `{action: "security_scan", params: {...}}`, looks up a registered handler, runs it, returns JSON result
- iOS Shortcuts can hit this via `Get contents of URL` with no SSH/Tailscale client
- **This is the only layer that needs `tailscale funnel`** which requires Tailscale to be the Funnel listener — meaning sshd-equivalent `systemd-resolved` MagicDNS to be working (currently broken per Phase 1 health check)

---

## 4. Package Selection (CachyOS / Arch)

| Component | Source | Trust | Verdict |
|---|---|---|---|
| `kilo acp` | Already installed (`kilo` 7.4.20) | First-party | Use existing install. Confirmed `kilo acp --help` works. |
| `acpx` | npm (`@openclaw/acpx` or `acpx`) | First-party (acpx.sh) | Optional install via `npm install -g acpx`. ~5 MB. Drives ACP servers from shell. **For Layer B orchestration.** |
| `tailscale funnel` | Already installed | First-party | Use existing tailscale 1.98.10. |
| Python web framework (Layer C) | `uv` (already in use) | First-party | `uv run --with fastapi uvicorn python -m receiver` for the action receiver. |
| `podman` (testing) | Already installed | First-party | Used in Phase 1, re-use for Phase 2 emulation. |

No new package installs at the OS level. `acpx` is an optional npm install.

---

## 5. Configuration Plan (exact files + diffs)

### 5.1 `~/.config/systemd/user/kilo-acp.service` (new, user unit)

```ini
[Unit]
Description=Kilo ACP headless server (for acpx/automation)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/home/ahron/.npm-global/lib/node_modules/@kilocode/cli/bin/kilo acp --port 8765 --hostname 127.0.0.1
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=default.target
```

**What this does:** `kilo acp` starts an ACP server on `127.0.0.1:8765` (loopback only — only reachable via Tailscale SSH or Funnel). Drives any ACP-compatible client (Zed, acpx, custom).

### 5.2 `~/codespace/automation/actions.json` (new, action library)

This is the curated library of pre-defined prompts that Shortcuts/scripts can invoke by name. Versioned in the codespace repo so it can be edited from any surface.

```json
{
  "actions": {
    "site_build": {
      "cwd": "/home/ahron/codespace/ahrondarnell-site",
      "command": "npm run build",
      "description": "Build the 1pointo Astro site"
    },
    "site_deploy_preview": {
      "cwd": "/home/ahron/codespace/ahrondarnell-site",
      "command": "npx wrangler pages deploy dist --project-name=ahrondarnell-site",
      "description": "Deploy site to Cloudflare Pages"
    },
    "substrate_status": {
      "cwd": "/home/ahron/codespace",
      "command": "uv run python -c 'from substrate.settings import load_workspace_config; from pathlib import Path; print(load_workspace_config(Path(\".\")).repositories.keys())'",
      "description": "List substrate workspace repos"
    },
    "security_scan": {
      "cwd": "/home/ahron/codespace",
      "command": "uv run python -m substrate.security_scan --quick",
      "description": "Quick security posture check"
    },
    "disk_usage": {
      "command": "df -h /home /var /tmp | head -10",
      "description": "Show disk usage of main mounts"
    },
    "memory_check": {
      "command": "free -h && ps aux --sort=-%mem | head -10",
      "description": "Show memory + top processes"
    },
    "git_pull_all": {
      "command": "for d in /home/ahron/codespace/*/; do (cd \"$d\" && git pull --ff-only 2>&1 | sed \"s|^|[$(basename $d)] |\"); done",
      "description": "Pull all workspace repos"
    },
    "agent_session": {
      "command": "kilo run \"%PROMPT%\"",
      "description": "Run a one-shot Kilo agent task with the given prompt"
    }
  }
}
```

**Usage from SSH/Shortcuts:**

```bash
# Read action library
ACTION=$(jq -r '.actions.site_build.command' ~/codespace/automation/actions.json)
# Run it
(cd /home/ahron/codespace/ahrondarnell-site && $ACTION)
```

Or, with the wrapper script `~/codespace/automation/run.sh` (to be created in 5.3), just:

```bash
~/codespace/automation/run.sh site_build
~/codespace/automation/run.sh site_deploy_preview
```

### 5.3 `~/codespace/automation/run.sh` (new, small wrapper)

```bash
#!/usr/bin/env bash
# Run a pre-defined action by name. See actions.json.
# Usage: run.sh <action_name> [extra args...]

set -euo pipefail

NAME="${1:-}"
if [ -z "$NAME" ]; then
    echo "Usage: $0 <action_name>" >&2
    echo "Available actions:" >&2
    jq -r '.actions | to_entries[] | "  \(.key) — \(.value.description)"' "$(dirname "$0")/actions.json" >&2
    exit 2
fi

ACTION_FILE="$(dirname "$0")/actions.json"
CMD=$(jq -r --arg n "$NAME" '.actions[$n].command // empty' "$ACTION_FILE")
CWD=$(jq -r --arg n "$NAME" '.actions[$n].cwd // "."' "$ACTION_FILE")

if [ -z "$CMD" ]; then
    echo "Unknown action: $NAME" >&2
    exit 3
fi

# Optional: substitute $1..$N into %PROMPT% if the action uses it
if [[ "$CMD" == *"%PROMPT%"* ]]; then
    shift
    PROMPT="$*"
    CMD="${CMD//%PROMPT%/$PROMPT}"
fi

if [ -n "$CWD" ] && [ "$CWD" != "." ]; then
    cd "$CWD"
fi

echo "+ $CMD" >&2
eval "$CMD"
```

### 5.4 (Optional) `~/codespace/automation/receiver.py` (Layer C, Tailscale Funnel)

A small FastAPI app that exposes registered actions over HTTP. Only used if Layer C is needed. Will be developed only if/when authorized.

---

## 6. Dependency & Closure Analysis (rootless simulation)

Resolved install set:

- `acpx` (optional npm global) — ~5 MB, depends on Node ≥ 18 (already have Node via the `kilo` install).
- `kilo-acp.service` (user unit) — new systemd user unit, no package changes.
- `actions.json` + `run.sh` — new files in `~/codespace/automation/`, tracked in git.
- `receiver.py` (Layer C only) — new Python file, deps via `uv` (fastapi, uvicorn).

No OS-level package installs. No AUR. No `curl | bash`. All first-party.

---

## 7. Simulation Method (Phase B, rootless)

1. `jq` already on host; verify it parses the new `actions.json` without error.
2. `bash -n run.sh` to syntax-check the wrapper.
3. `podman run --rm archlinux` — install `kilo`-equivalent + `jq` + verify the wrapper logic.
4. `kilo acp --help` on the host — confirm the binary actually starts an ACP server (we won't keep it running; just `--help`).
5. `acpx --help` (after `npm install -g acpx` is done in the host's user namespace) — confirm the binary is callable.
6. (Optional) `tailscale funnel --help` — confirm CLI shape matches Funnel v1.52+ syntax.

All Python analysis tooling under `uv` per substrate conventions.

---

## 8. Research Sources (verified upstream, no third-party blogs relied on for trust)

- `kilo.ai/docs/code-with-ai/platforms/cli` — Kilo CLI command reference (2026)
- `kilo.ai/docs/code-with-ai/platforms/cli-reference` — `kilo acp` flags
- `deepwiki.com/Kilo-Org/kilocode/13.3-acp-protocol` — Kilo ACP implementation details
- `agentclientprotocol.com/protocol/v1/overview` — ACP v1 spec (JSON-RPC 2.0)
- `acpx.sh/quickstart.html` + `acpx.sh/prompting.html` — `acpx` headless ACP client
- `github.com/Kilo-Org/kilocode/issues/6766` — official confirmation: Kilo works with `acpx opencode exec`
- `tailscale.com/docs/features/tailscale-funnel` + `tailscale.com/docs/reference/tailscale-cli/funnel` — Tailscale Funnel CLI
- `thoughtasylum.com/2026/05/27/triggering-macos-operations-remotely/` — Tailscale + Shortcuts + SSH pattern

---

## 9. Verification & Rollback

**Success criteria (post-implementation, observable from the iPhone):**

- [ ] From the iPhone, opening the Kilo iOS app, the host's session appears under **CLI** surface. Sending a message that requires a tool call (e.g., "what's the disk usage?") produces a real result.
- [ ] From the iPhone, in Termius/Blink, SSH to `100.117.132.49` (or MagicDNS name if resolved) and run `~/codespace/automation/run.sh disk_usage` — it returns `df -h` output.
- [ ] From the iPhone, in Termius, `kilo run "tell me the current weather in Buffalo"` — returns a real answer.
- [ ] Optional: iOS Shortcut "Run security scan" → ssh into Tailscale IP → runs `~/codespace/automation/run.sh security_scan` → returns the JSON result via Shortcuts' "Show result" action.
- [ ] `ss -tlnp | grep -E '8765|10000'` shows the ACP server (8765) and (if Layer C is enabled) action-receiver (10000) bound to `127.0.0.1` ONLY.
- [ ] No new external ports. Funnel only adds an outbound connection to the Tailscale relay.

**Rollback (in order, all rootless except Tailscale state):**

1. `systemctl --user disable --now kilo-acp.service && rm ~/.config/systemd/user/kilo-acp.service && systemctl --user daemon-reload`
2. `rm -rf ~/codespace/automation/`
3. (If Layer C enabled) `tailscale funnel --https=10000 off && systemctl --user disable --now action-receiver.service`
4. (If `acpx` installed) `npm uninstall -g acpx`
5. (Phase 1 rollback still applies for Tailscale) — see `PLAN.md` §9

After rollback: iPhone cannot trigger any new actions. Chat via Kilo iOS app still works (Phase 1 untouched).

---

## 10. Lifecycle Alignment (3×3)

- **Stage:** `local` (this entire plan; the host is the host)
- **Pass:** `research` (this document) → `development` (sandbox emulation in Phase B) → `testing` (live, authorized host validation after the single PolicyKit gate)

---

## 11. What is explicitly OUT of scope for this single batch

- **Tailscale Funnel** (Layer C) — only if A and B prove insufficient in validation. The systemd-resolved/MagicDNS issue from Phase 1 would also need to be fixed first.
- **A custom iOS Shortcuts setup** — that's the user's action; we provide the iOS Shortcuts template.
- **A new auth layer** — Tailscale identity (Phase 1) is the credential; no API keys.
- **Replacing `kilo run` with a custom executor** — the existing CLI is sufficient and well-tested.
