# Register an Android OpenClaw CLI as a Worker + Developer Node

Target gateway: `cachyos-x8664` (this machine)
Generated: 2026-08-13

## 0. Facts about this gateway (verified, not assumed)

| Fact | Value |
|---|---|
| OpenClaw version | `2026.7.1-2 (0790d9f)` |
| Gateway WS port | **8090** (NOT the doc default 18789) |
| Bind mode | `loopback` — only 127.0.0.1 / [::1] |
| Auth mode | token (`gateway.auth.token` in `~/.openclaw/openclaw.json`) |
| Tailscale name | `cachyos-x8664.tail0b124a.ts.net` |
| Tailscale IP | `100.117.132.49` |
| LAN IP | `192.168.1.249` |
| `gateway.nodes` policy | `null` (defaults only) |
| `tools.exec` config | `{}` (empty — no node pinned yet) |

Because bind is `loopback`, a phone **cannot** connect directly yet.
Pick Path A (tunnel, no server change) or Path B (bind change, needs your OK).

---

## 1. On Android (Termux) — install

```bash
pkg update && pkg upgrade -y
pkg install -y nodejs-lts openssh
node -v          # must be 22.22.3+, 24.15+, or 25.9+
npm install -g openclaw
openclaw --version
```

If `openclaw: command not found`:

```bash
mkdir -p "$HOME/.npm-global"
npm config set prefix "$HOME/.npm-global"
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

## 2. Get the gateway token (run on the CachyOS box, not the phone)

```bash
openclaw config get gateway.auth.token
```

Transfer it to the phone by hand. Do not paste it into a chat or commit it.

---

## Path A — SSH tunnel (no gateway change; works with loopback bind)

Requires `sshd` reachable on the CachyOS box over Tailscale.

Terminal 1 on Android (keep running):

```bash
ssh -N -L 18790:127.0.0.1:8090 ahron@100.117.132.49
```

Terminal 2 on Android:

```bash
export OPENCLAW_GATEWAY_TOKEN="<token-from-step-2>"
openclaw node run --host 127.0.0.1 --port 18790 --display-name "Ahron Android"
```

## Path B — bind gateway to Tailscale (direct connect, no tunnel)

Run on the CachyOS box. **This changes gateway exposure — my recommendation is
to keep it Tailscale-only, never LAN/public:**

```bash
openclaw config set gateway.bind tailscale
openclaw gateway restart
```

Then on Android:

```bash
export OPENCLAW_GATEWAY_TOKEN="<token-from-step-2>"
openclaw node run --host 100.117.132.49 --port 8090 --display-name "Ahron Android"
```

---

## 3. Approve the pairing (on the CachyOS box)

The node's `connect` handshake creates a **device pairing** request.

```bash
openclaw devices list
openclaw devices approve <requestId>
openclaw nodes status
openclaw nodes describe --node "Ahron Android"
```

Notes:
- Pending requests expire 5 minutes after the device's last retry.
- If the node reconnects with changed role/scopes/public key, the old request is
  superseded — re-run `openclaw devices list` and approve the **current** id.
- Approval scope needed: `operator.pairing` + `operator.admin` (because a
  worker node declares `system.run` / `system.which`).

---

## 4. Make it a WORKER (run shell commands)

Exec approvals live **on the phone** at `~/.openclaw/exec-approvals.json`.
Allowlist entries are added from the gateway:

```bash
openclaw approvals allowlist add --node "Ahron Android" "/data/data/com.termux/files/usr/bin/uname"
openclaw approvals allowlist add --node "Ahron Android" "/data/data/com.termux/files/usr/bin/git"
openclaw approvals allowlist add --node "Ahron Android" "/data/data/com.termux/files/usr/bin/node"
```

Termux paths are NOT `/usr/bin/*`. Confirm each real path first:

```bash
openclaw nodes invoke --node "Ahron Android" --command system.which --params '{"name":"git"}'
```

Route exec at the node — **per session (recommended, reversible):**

```text
/exec host=node security=allowlist node="Ahron Android"
```

Or globally (persistent; affects every agent run):

```bash
openclaw config set tools.exec.host node
openclaw config set tools.exec.security allowlist
openclaw config set tools.exec.node "Ahron Android"
```

I'd keep it per-session. Making the phone the global exec host means every
command this substrate runs goes to a battery-powered device over Tailscale.

Better: pin it to one agent only:

```bash
openclaw config set 'agents.list[0].tools.exec.node' "Ahron Android"
```

---

## 5. Make it a DEVELOPER node (Android data surface)

These are Android platform defaults — allowed once pairing is approved, no
extra config:

`camera.list`, `location.get`, `notifications.list`, `notifications.actions`,
`system.notify`, `device.info`, `device.status`, `device.permissions`,
`device.health`, `device.apps`, `contacts.search`, `calendar.events`,
`callLog.search`, `reminders.list`, `photos.latest`, `motion.activity`,
`motion.pedometer`, plus `canvas.*`.

```bash
openclaw nodes invoke --node "Ahron Android" --command device.info --params '{}'
openclaw nodes invoke --node "Ahron Android" --command device.status --params '{}'
openclaw nodes canvas snapshot --node "Ahron Android" --format png
openclaw nodes notify --node "Ahron Android" --title "Substrate" --body "Node online"
```

Dangerous / privacy-heavy commands need **explicit** opt-in even if the phone
declares them (`camera.snap`, `camera.clip`, `screen.record`, `contacts.add`,
`calendar.add`, `reminders.add`, `sms.send`, `sms.search`):

```bash
openclaw config set gateway.nodes.allowCommands '["camera.snap","sms.search"]'
openclaw gateway restart
```

`gateway.nodes.denyCommands` always wins over defaults and allowCommands.

---

## 6. Persistence on Android — DO NOT use `node install`

**`openclaw node install` / `node start` / `node stop` / `node restart` /
`node status` all FAIL on Android**, with:

```
Gateway service install not supported on android
```

This is by design, not a bug. Verified in the installed package:

- `dist/service-Dx57p0eF.js:183` defines `GATEWAY_SERVICE_REGISTRY` with keys
  for **only** `darwin` (LaunchAgent), `linux` (systemd user), `win32`
  (Scheduled Task).
- `resolveGatewayService()` (line 250) falls through to
  `createUnsupportedGatewayService()` when `process.platform` isn't one of those
  three. On Termux `process.platform === "android"`, so it throws.
- `dist/node-service-xUwQjiEY.js` `resolveNodeService()` is just a **wrapper
  around `resolveGatewayService()`** — it only swaps in node-host service
  labels. So the node daemon inherits the same platform gate.
- Confirmed callers of the failing path: `runNodeDaemonInstall`,
  `runNodeDaemonUninstall`, `runNodeDaemonStart`, `runNodeDaemonRestart`,
  `runNodeDaemonStop`, `runNodeDaemonStatus`.

Android has no systemd and no launchd, so there is nothing to install into.

### What DOES work: `openclaw node run` (foreground)

`node run` is registered separately (`dist/node-cli-DSAz3X0B.js:2738`) and never
touches the service registry. It is the only supported way to run a node host on
Termux.

Keep it alive with Termux's own mechanisms, not OpenClaw's:

```bash
pkg install -y termux-api termux-services
termux-wake-lock                     # stop Android from sleeping the process
openclaw node run --host 127.0.0.1 --port 18790 --display-name "Ahron Android"
```

Also required, or Android kills it within minutes:
- Android Settings > Apps > Termux > Battery > **Unrestricted**
- Termux notification > **Acquire wakelock**
- Install **Termux:Boot** if you want it to survive a reboot

For a real supervised service under Termux, use `runit` via `termux-services`
(write an `sv` run script that execs `openclaw node run`) — that is Termux's
service manager, and it is unrelated to `openclaw node install`.

Node identity/token persist in `~/.openclaw/node.json` on the phone either way.

### Strongly consider the official Android app instead

The Play Store / APK OpenClaw Android app is the *supported* node for a phone.
It keeps its gateway connection alive with a real Android **foreground service**
(persistent notification) — which is the thing Termux is fighting the OS to
emulate. It also gives you `device.*`, `notifications.*`, `photos.latest`,
`callLog.search`, `camera.*`, `canvas.*`, Voice/Talk, and mDNS discovery.

Tradeoff: the app is NOT a shell worker — it does not expose `system.run`, so it
cannot run `git`/build commands. Pick based on intent:

| Goal | Use |
|---|---|
| Run shell commands / dev worker | Termux + `openclaw node run` (foreground) |
| Phone sensors, notifications, camera, voice | Official Android app |
| Both | Run both; they pair as two separate nodes |

Note the app needs a **`wss://`** endpoint for Tailscale/public hosts — cleartext
`ws://` is only allowed on private LAN / `.local` / `127.0.0.1`. Use
`openclaw gateway --tailscale serve` for that.

---

## 7. Verify end to end

```bash
openclaw nodes status --connected
openclaw nodes describe --node "Ahron Android"
openclaw nodes invoke --node "Ahron Android" --command system.which --params '{"name":"uname"}'
```

## Rollback

```bash
openclaw nodes remove --node "Ahron Android"     # revokes the node role
openclaw config unset tools.exec.node
openclaw config set gateway.bind loopback        # only if you used Path B
openclaw gateway restart
```

On the phone: `openclaw node stop && openclaw node uninstall`

## Gotchas

- Port is **8090** here, not 18789. Every doc example says 18789 — ignore it.
- `openclaw nodes invoke` refuses `system.run`/`system.run.prepare` by design;
  shell goes through the `exec` tool with `host=node`.
- `host=auto` will not silently pick the phone; `host=node` must be explicit.
- Node hosts ignore `PATH` in `--env` and strip `NODE_OPTIONS`, `PYTHONPATH`,
  `BASH_ENV`, `LD_*`. Configure the service env instead.
- Nodes are peripherals: WhatsApp/Telegram messages still land on the gateway,
  never on the phone.
