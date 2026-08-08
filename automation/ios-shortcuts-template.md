# iOS Shortcuts — 1pointo Remote Control

This is a template for Apple Shortcuts on your iPhone. Each shortcut SSHes into your CachyOS host over Tailscale and runs a pre-defined action.

## Prerequisites

1. **Tailscale on iPhone** — install from the App Store, sign in with the same Tailscale account as your CachyOS host.
2. **Keep Tailscale connected** — the iPhone Tailscale app must be running (it runs in the background, but check if Shortcuts are failing).
3. **Host IP** — your CachyOS Tailscale IP is `100.117.132.49` (run `tailscale status` on the host to confirm).
4. **SSH auth** — Tailscale SSH uses Tailscale identity, not a key. The iOS "Run script over SSH" action requires picking an auth method:
   - **Tailscale SSH option:** the Shortcut connects via Tailscale mesh, no password/key needed once the iPhone Tailscale app is connected to the same account.
   - **Practical alternative:** set a long-lived SSH key on the host (`~/.ssh/authorized_keys`) and pick the key in the Shortcut.

## How to create a Shortcut

In the iOS Shortcuts app: `+` → search for "Run script over SSH" → set Host / User / Auth → paste the script below → name it → optionally add to Home Screen or assign to Siri.

---

## Shortcut: "Run security scan"

```
~/codespace/automation/run.sh security_scan
```

Or, since security_scan is not yet in the library:

```
~/codespace/automation/run.sh disk_usage
~/codespace/automation/run.sh memory_check
~/codespace/automation/run.sh tailscale_status
```

Display the result with a "Show result" action after the SSH action.

## Shortcut: "Build & deploy site"

```
~/codespace/automation/run.sh site_full
```

## Shortcut: "Pull all repos"

```
~/codespace/automation/run.sh git_pull_all
```

## Shortcut: "Ask agent" (free-form)

This takes user input and runs a one-shot Kilo agent task.

1. Add an **"Ask for input"** action — Type: Text, Prompt: "What should the agent do?"
2. Add a **"Run script over SSH"** action:
   - Script: `kilo run "$1"` (the iOS action passes input as `$1`)
3. Add a **"Show result"** action.

When you invoke "Hey Siri, ask agent", Siri asks you what to do, then the Shortcut sends the prompt to the local Kilo agent on your CachyOS host.

## Shortcut: "List available actions"

```
~/codespace/automation/run.sh
```

(no arguments — the wrapper lists all actions when called with no args)

---

## Siri phrases

- "Hey Siri, run security scan" → runs the security scan
- "Hey Siri, deploy my site" → builds + deploys 1pointo.com
- "Hey Siri, pull my repos" → git pull on all codespace repos
- "Hey Siri, ask agent" → free-form agent prompt

---

## Adding a new action

1. SSH into the host: `ssh ahron@100.117.132.49`
2. Edit `~/codespace/automation/actions.json` and add a new key
3. Add a new iOS Shortcut pointing at the new action
4. Commit the updated `actions.json`: `cd ~/codespace && git add automation/ && git commit -m "feat: add <name> action"`

---

## Troubleshooting

- **"Connection refused"** — Tailscale on the iPhone is disconnected. Open the Tailscale app and confirm the host shows as a peer.
- **"Permission denied"** — Tailscale SSH ACL may be blocking. On the host, run `tailscale status` and confirm the iPhone is listed.
- **"Unknown action"** — the action library on the host has been updated; re-run `~/codespace/automation/run.sh` (no args) to see the current list.
- **"default agent substrate-maintainer not found"** — the `agent_session` action requires a configured default agent. On the host, set a real default: `kilo config set default_agent general` (or your preferred agent). See `kilo config --help`.
