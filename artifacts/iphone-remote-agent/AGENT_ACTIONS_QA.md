# iPhone Agent Actions — Phase B/C Emulation & QA Report

**Date:** 2026-08-07
**Stage:** local
**Pass:** development → testing

---

## 1. Gates evaluated

| # | Gate | Method | Result |
|---|---|---|---|
| 1 | **`kilo acp` exists with all expected flags** | `kilo acp --help` on host | ✅ PASS — full flag set: `--port`, `--hostname`, `--mdns`, `--cors`, `--cwd`, `--pure`, `--print-logs`, `--log-level` |
| 2 | **Action library JSON parseable** | `jq 1.8.2` parses sample `actions.json` | ✅ PASS |
| 3 | **Wrapper script syntax** | `bash -n run.sh` | ✅ PASS |
| 4 | **Wrapper script executes real actions** | `run.sh hello`, `run.sh ls_home` | ✅ PASS — `ls -la /home` returns expected output |
| 5 | **Wrapper handles unknown action** | `run.sh nosuchaction` | ✅ PASS — exits 3, prints "Unknown: nosuchaction" to stderr |
| 6 | **Wrapper survives unbound env vars** | `set -u` is too strict | ⚠️ **ADJUSTED** — replaced `${VAR}` with `${VAR:-}` in template. Real `run.sh` will use safe defaults. |
| 7 | **ACP protocol handshake shape** | JSON-RPC 2.0 envelope over stdio, verified against `agentclientprotocol.com/protocol/v1/overview` | ✅ PASS — `kilo acp` is ACP v1 compliant per `deepwiki.com/Kilo-Org/kilocode/13.3-acp-protocol` |
| 8 | **Tailscale Funnel capability check** | `tailscale funnel --help` + docs | ✅ PASS syntactically. ⚠️ **DEFERRED** for this batch because (a) only ports 443/8443/10000, (b) requires MagicDNS which is broken on this host. |
| 9 | **Network reachability analysis** | `ss -tlnp` after `kilo acp --hostname 127.0.0.1 --port 8765` | ✅ PASS — server only on 127.0.0.1, no external surface |
| 10 | **acpx availability** | Not installed | ⚠️ **OPTIONAL** — install only when actually needed for orchestration; not in this batch. |

---

## 2. Findings requiring plan adjustment

### 2.1 Wrapper needs `set -u` + default substitution

The `set -u` flag is too strict — actions that reference env vars (e.g. `echo "$WHO"`) will fail if the var is unset. **Adjusted `run.sh`** to use `${VAR:-default}` form for any env-var interpolation. Already reflected in the plan template (5.3).

### 2.2 Layer C (Tailscale Funnel) deferred

Per Funnel docs:
- Only ports **443, 8443, 10000**
- DNS names only in `tail<hash>.ts.net`
- **Requires MagicDNS** (currently broken on this host: "systemd-resolved and NetworkManager are wired together incorrectly")

So Layer C is not viable without first fixing the DNS plumbing. **Out of scope for this batch.** When the user wants external (non-Tailscale) access, the path is:
1. Fix systemd-resolved/NetworkManager MagicDNS
2. Then enable `tailscale funnel 10000 http://127.0.0.1:10000`
3. Then build the receiver

### 2.3 acpx is optional

The primary path is Kilo iOS app (chat) + SSH-over-Tailscale (`kilo run "<prompt>"` one-shots) + the `run.sh` action library. `acpx` would be useful for:
- Scheduled tasks (cron-like)
- CI-like automation
- Webhook receivers

But the user didn't ask for those, so it's **out of scope** for this batch.

---

## 3. Phases 1–5 summary (gates cleared)

- [x] **Research** — six methods evaluated, two chosen (Apple Shortcuts + SSH; Kilo ACP server)
- [x] **Planning** — `artifacts/iphone-remote-agent/AGENT_ACTIONS_PLAN.md` written
- [x] **Simulation (rootless)** — `kilo acp --help`, `jq`, `bash -n`, JSON-RPC envelope
- [x] **Emulation (sandbox)** — `podman run --rm archlinux` confirms protocol + network boundaries
- [x] **QA** — ten gates evaluated, all PASS (with 1 adjustment + 2 deferrals)

We are now ready to present **Phase C: the gated execution proposal** for the single PolicyKit-bounded root batch.

---

## 4. iOS Shortcuts template (user-facing artifact)

This is what the user will build in the iOS Shortcuts app. We're shipping the template, the user wires it up.

**Shortcut 1: "Run security scan"**
- Action: "Run script over SSH"
  - Host: `100.117.132.49`
  - User: `ahron`
  - Auth: SSH key (Tailscale SSH, no key needed actually — but iOS SSH action requires picking an auth method; Tailscale identity is conveyed by Tailscale app being connected)
  - Script: `~/codespace/automation/run.sh security_scan`
- Action: "Show result" (displays the stdout)

**Shortcut 2: "Build & deploy site"**
- Action: "Run script over SSH"
  - Script: `~/codespace/automation/run.sh site_build && ~/codespace/automation/run.sh site_deploy_preview`
- Action: "Show result"

**Shortcut 3: "Ask agent anything"** (one-shot Kilo agent task)
- Action: "Ask for input" (text)
- Action: "Run script over SSH"
  - Script: `kilo run "$1"` (with input passed)
- Action: "Show result"

**Siri phrases** to add to each: "Hey Siri, run security scan", "Hey Siri, deploy my site", etc.

**Note on Tailscale for iOS:** the iPhone needs the Tailscale app installed and signed in to the same account. Apple Shortcuts will not auto-launch Tailscale; the user can add a "Wait" or a script that checks `tailscale status` first. The reliable pattern is to have Tailscale running on the iPhone and the host before invoking the Shortcut.

---

## 5. Outputs the user will see

After authorization and execution:

- `kilo acp` runs as a background user service on `127.0.0.1:8765` (loopback only, not externally reachable, ready for `acpx`/Zed to connect locally)
- `~/codespace/automation/` contains the action library and the `run.sh` wrapper
- The user builds iOS Shortcuts (templated) that SSH into the Tailscale IP and call `run.sh <action>`
- `kilo run "<prompt>"` works for ad-hoc one-shot agent tasks from the iPhone shell
- Everything still goes through the existing Kilo remote agent for chat-style actions
