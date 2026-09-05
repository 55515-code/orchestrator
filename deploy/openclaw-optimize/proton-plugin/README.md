# OpenClaw `proton-bridge` extension plugin

A Control-UI-settings-backed extension plugin for **OpenClaw 2026.8.2** that manages the
custom **Proton Mail Bridge → OpenClaw hook** integration:

- declares a schema-driven config section (`plugins.entries.proton-bridge.config`) that the
  Control UI renders as editable fields (masked password/token),
- reconciles those settings into the mode-600 env file
  `/home/ahron/.config/substrate/proton-bridge-hook.env`
  (`PROTON_EMAIL`, `PROTON_BRIDGE_PW`, `PROTON_IMAP_HOST/PORT`, `PROTON_POLL_SECONDS`,
  `OPENCLAW_HOOK_URL`, `OPENCLAW_HOOK_TOKEN`),
- restarts the systemd user unit `proton-bridge-hook.service` after a change,
- adds `openclaw proton-bridge status|apply|clear` CLI commands and
  `protonBridge.status` / `protonBridge.apply` gateway RPC methods.

Nothing here modifies the live gateway yet. Install steps are at the bottom.

---

## 1. What is confirmed-supported in v2026.8.2 (verified against the installed tree)

Installed package: `/home/ahron/.npm-global/lib/node_modules/openclaw`
(`package.json` → `2026.8.2`; CLI reports `OpenClaw 2026.8.2 (0965053)`).

### 1.1 Extension plugins declare config schema via the manifest; the Control UI renders it

Built-in extensions ship an `openclaw.plugin.json` whose `configSchema` + `uiHints`
declare their settings, e.g.:

- `dist/extensions/logbook/openclaw.plugin.json` — `configSchema` with typed fields and
  `uiHints` (`label`, `help`, `placeholder`, `advanced`), rendered in Control UI.
- `dist/extensions/admin-http-rpc/openclaw.plugin.json` — `activation.onConfigPaths:
  ["plugins.entries.admin-http-rpc"]`; config is the entry under `plugins.entries.<id>`.
- `dist/extensions/active-memory/openclaw.plugin.json`, `dist/extensions/vault/...`,
  `dist/extensions/telegram/...` (channels use `channelConfigs.<channel>.schema`).

The config lives at `plugins.entries.<id>.config`
(`dist/types-D57XcDrj.d.ts`: `PluginEntryConfig`, lines ≈5633–5715). `api.pluginConfig`
is exactly that object (`docs/plugins/sdk-overview.md`, line ≈819). `uiHints` (including
`sensitive: true` for secrets) is a manifest field (`docs/plugins/manifest.md`, line ≈189
and the openrouter example at lines ≈117–133).

The Control UI's config editor is **schema-driven and includes plugin schemas**:

> "Schema and form rendering come from `config.schema` / `config.schema.lookup`,
> including … matched UI hints … plus plugin and channel schemas when available."
> — `docs/web/control-ui.md`, Settings → Config accordion.

and the generic config area covers every section without a curated page:

> "Advanced: every config section without a curated home, plus the raw JSON5 editor"
> — `docs/web/control-ui.md`, Settings → Config accordion.

So this plugin's fields are edited in the Control UI Settings config editor under
`plugins.entries.proton-bridge.config`; no custom front-end code is required.

### 1.2 Saving a `plugins.*` config change hot-reloads plugin runtimes (no gateway restart)

The gateway reload planner maps the `plugins` config prefix to a **hot** reload with the
`reload-plugins` action (`dist/config-reload-plan-D8kzIMTY.js`, `BASE_RELOAD_RULES`), and
hot plugin reload **replaces plugin runtimes/services** against the new config
(`dist/server-reload-handlers-Cjokxysa.js`, `plan.reloadPlugins` →
`params.reloadPlugins({ nextConfig, ... })` with service replacement). Therefore a Save on
the proton section re-runs this plugin's `register()`/service start with fresh settings —
which is where the plugin reconciles the env file and restarts the hook service.

### 1.3 Plugin code runs on the gateway host and may run shell tools

Bundled plugins already do this: `dist/extensions/logbook/index.js` uses `node:fs`
`readFileSync`, `dist/extensions/crabbox/index.js` and `dist/extensions/cua-computer/index.js`
use `node:child_process` `spawn`/`spawnSync` (including `systemctl`-style host tooling).
Installed plugins run under the gateway's runtime with the gateway's user identity and
have the same host-side Node access (`docs/plugins/building-plugins.md`; the SDK import
convention is `import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry"`).

### 1.4 Plugins can add root CLI commands and gateway RPC methods

- `api.registerCli(...)` + manifest `cliCommands` / `commandAliases` /
  `activation.onCommands`: see `dist/extensions/vault/openclaw.plugin.json` +
  `dist/extensions/vault/index.js` (registers `openclaw vault ...`).
- `api.registerGatewayMethod(name, handler, { scope })`: see
  `dist/extensions/logbook/index.js` (`logbook.status`, etc.).
- `api.registerService(...)`: background service started with the plugin runtime
  (`dist/plugin-entry-B3VkmenH.d.ts`, `OpenClawPluginService`), the reconcile hook point.

### 1.5 Admin HTTP RPC cannot run arbitrary commands

`docs/plugins/admin-http-rpc.md` (lines ≈168–185) and the source allowlist
(`dist/extensions/admin-http-rpc/index.js`, `ADMIN_HTTP_RPC_ALLOWED_METHODS`) include
`config.get`, `config.schema`, `config.schema.lookup`, `config.set`, `config.patch`,
`config.apply` — **no method that executes a custom command/tool or writes the env file /
restarts a service**. Its config writes are for `openclaw.json` only. So it is a
convenient read/write path for the config section, not a replacement for this plugin's
reconcile step.

---

## 2. What is NOT supported in v2026.8.2

### 2.1 `gateway.controlUi.experimental.customPlugins` does not exist

`grep -r "customPlugins"` across the whole installed package returns **zero matches**.
`GatewayControlUiConfig` (`dist/types-D57XcDrj.d.ts`, lines ≈4139–4185) has no
`experimental`/`customPlugins` key. There is therefore no "frontend control-ui plugin"
load path to write against.

### 2.2 External plugins get read-only sandboxed tabs, not native settings tabs with POST

Plugin Control-UI **tabs** are real: `api.session.controls.registerControlUiDescriptor({
surface: "tab", ... })` (`docs/plugins/sdk-overview.md`, lines ≈456–506;
`dist/plugin-entry-B3VkmenH.d.ts`, `PluginControlUiDescriptor`). But for an **installed**
(external) plugin the Control UI mounts the descriptor `path` (a plugin HTTP route) in a
sandboxed frame, and the gateway grant to that frame is **GET/HEAD only with
`operator.read`**:

> "The frame grant accepts only `GET` and `HEAD` and always carries `operator.read` …
> Mutations remain on explicit Gateway-authenticated parent or bearer surfaces."
> — `docs/plugins/sdk-overview.md`

(Also `dist/github-user-identity-Dm3dZZld.js`, `listControlUiPluginTabAuthGrants`.)
Only bundled plugins can claim a native route (`placement: "route:<pluginId>"`) or ship a
first-class view (the Control UI build embeds only bundled views such as
`logbook-view-*.js`). So a "custom Proton Mail settings **tab** with a Save button that
POSTs to the backend" is **not cleanly supported for an installed plugin** in 2026.8.2.

A `surface: "settings"` descriptor exists in the type union
(`PluginControlUiDescriptor.surface`) but its rendering for external plugins is not
documented in `docs/plugins/sdk-overview.md` and is not verified to mount for installed
plugins, so this design does not depend on it.

### 2.3 Summary

| Mechanism | v2026.8.2 status |
| --- | --- |
| `gateway.controlUi.experimental.customPlugins` | **absent** (0 matches in package) |
| Manifest `configSchema` + `uiHints` rendered by Control UI config editor | **supported** |
| Hot plugin runtime reload on `plugins.*` config save | **supported** |
| Plugin CLI commands (`api.registerCli`) | **supported** |
| Plugin gateway RPC methods + services | **supported** |
| Plugin writes env file / runs `systemctl --user` | **supported** (host process) |
| Installed-plugin Control-UI tab with mutation POST | **not cleanly supported** (GET/HEAD grant) |
| `admin-http-rpc` running arbitrary commands | **not supported** (config methods only) |

---

## 3. Design

The chosen route is therefore **backend extension plugin + manifest config schema**:

```
Control UI Settings (schema form, plugins.entries.proton-bridge.config)
        │  Save → config.patch/apply
        ▼
Gateway config reload planner: plugins.* → hot "reload-plugins"
        ▼
Plugin runtime/service replaced with new api.pluginConfig
        ▼
registerService.start(): reconcile()
   • read existing env file (preserve unrelated lines)
   • serialize managed keys (atomic write, mode 600)
   • if changed → systemctl --user restart proton-bridge-hook.service
```

Plus operator-visible fallbacks:

- `openclaw proton-bridge status|apply|clear` CLI (no UI needed),
- `protonBridge.status` / `protonBridge.apply` gateway RPC methods,
- explicit re-reconcile on every plugin activation, so a plain gateway restart also
  converges the env file.

Secrets stay masked in the UI via `uiHints.sensitive`; they are stored in `openclaw.json`
(already mode-restricted like the other gateway credentials) and written to the mode-600
env file. Clearing a field in the UI to an empty value removes the matching env key
(empty fields are treated as "unset"); absent fields are left untouched so the hook falls
back to its script defaults / secret-tool keyring.

### Files

| File | Purpose |
| --- | --- |
| `openclaw.plugin.json` | Manifest: plugin id `proton-bridge`, activation (`onConfigPaths` + `onCommands`), `cliCommands`, `configSchema`, `uiHints`. |
| `index.js` | Runtime: config parsing, env serialization (atomic, mode 600), `systemctl --user` (sets `XDG_RUNTIME_DIR`), reconcile service, gateway methods, CLI commands. |
| `package.json` | External-plugin package metadata + `openclaw.extensions` entry. |

### Behavior notes

- `systemctl --user` needs the user bus: the plugin exports `XDG_RUNTIME_DIR=/run/user/<uid>`
  for the child when it is unset (verified working on this host; without it the gateway
  service environment cannot reach the user bus).
- The env file is only rewritten when content actually changes; the service is restarted
  only when the file changed.
- Unknown lines in the env file (comments, unrelated keys) are preserved verbatim.
- The reconcile step is idempotent and failure-safe: write/restart errors are logged as
  warnings and reported by the CLI / RPC; they never crash the gateway.

---

## 4. Install & enable (do not run until you are ready)

Requires the gateway to restart after the plugin is first installed.

```bash
OC=/home/ahron/.npm-global/bin/openclaw

cd /home/ahron/codespace/deploy/openclaw-optimize

# 1) install from this local directory (linked dev source; copies nothing)
$OC plugins install --link ./proton-plugin --accept-capabilities --force

# 2) add "proton-bridge" to plugins.allow (the live config uses an explicit allowlist)
#    edit /home/ahron/.openclaw/openclaw.json, or:
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path.home() / ".openclaw" / "openclaw.json"
cfg = json.loads(p.read_text())
allow = cfg.setdefault("plugins", {}).setdefault("allow", [])
if "proton-bridge" not in allow:
    allow.append("proton-bridge")
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    print("added proton-bridge to plugins.allow")
EOF

# 3) enable (writes plugins.entries.proton-bridge.enabled = true)
$OC plugins enable proton-bridge --accept-capabilities

# 4) configure the fields (examples; the Control UI Settings form can do this too)
$OC config set plugins.entries.proton-bridge.config.email 'you@protonmail.com'
$OC config set plugins.entries.proton-bridge.config.bridgePassword 'replace-me'
$OC config set plugins.entries.proton-bridge.config.imapHost '127.0.0.1'
$OC config set plugins.entries.proton-bridge.config.imapPort 1143 --strict-json
$OC config set plugins.entries.proton-bridge.config.pollSeconds 30 --strict-json
$OC config set plugins.entries.proton-bridge.config.hookUrl 'http://127.0.0.1:8090/hooks/proton'
$OC config set plugins.entries.proton-bridge.config.hookToken 'replace-me'

# 5) restart the gateway so the plugin registry picks up the new plugin
systemctl --user restart openclaw-gateway
#   or: $OC gateway restart

# 6) verify
$OC plugins list | grep proton
$OC plugins inspect proton-bridge --runtime --json
$OC proton-bridge status
$OC proton-bridge apply
systemctl --user status proton-bridge-hook
```

From then on:

- Edit the section **Settings → Config → … → Advanced** (the schema form for
  `plugins.entries.proton-bridge.config`) and Save/Apply. Because the change is under the
  `plugins` config prefix, the gateway hot-reloads the plugin runtime and the reconcile
  step writes the env file and restarts `proton-bridge-hook.service` — no gateway restart
  required for subsequent edits.
- Or run `openclaw proton-bridge apply` after editing.
- `openclaw proton-bridge clear --dry-run` shows what removing all managed env keys would do.

### Rollback

```bash
$OC plugins disable proton-bridge
systemctl --user restart openclaw-gateway
# optionally: $OC plugins uninstall proton-bridge
```

---

## 5. Key verification citations

- Package + version: `/home/ahron/.npm-global/lib/node_modules/openclaw/package.json`; CLI `openclaw --version`.
- `customPlugins` absent: recursive grep over the installed package → 0 matches; `GatewayControlUiConfig` in `dist/types-D57XcDrj.d.ts` (≈lines 4139–4185).
- Manifest config schema + uiHints: `dist/extensions/logbook/openclaw.plugin.json`, `docs/plugins/manifest.md` (≈lines 117–133, 189).
- `api.pluginConfig` = `plugins.entries.<id>.config`: `docs/plugins/sdk-overview.md` (≈line 819); `dist/types-D57XcDrj.d.ts` `PluginEntryConfig` (≈lines 5633–5715).
- Control UI config editor is schema-driven incl. plugin schemas: `docs/web/control-ui.md` (Settings → Config accordion).
- Hot `plugins.*` reload: `dist/config-reload-plan-D8kzIMTY.js` (`BASE_RELOAD_RULES`); plugin runtime replacement in `dist/server-reload-handlers-Cjokxysa.js` (≈lines 894–978).
- Admin HTTP RPC allowlist: `docs/plugins/admin-http-rpc.md` (≈lines 168–185); `dist/extensions/admin-http-rpc/index.js`.
- Plugin tabs / sandboxed-frame grant: `docs/plugins/sdk-overview.md` (≈lines 456–506); `dist/github-user-identity-Dm3dZZld.js`; `dist/plugin-entry-B3VkmenH.d.ts` (`PluginControlUiDescriptor`).
- Plugin CLI registration precedent: `dist/extensions/vault/openclaw.plugin.json`, `dist/extensions/vault/index.js`.
- Plugin host-process filesystem/child-process precedent: `dist/extensions/logbook/index.js`, `dist/extensions/crabbox/index.js`.
- Plugin install CLI: `docs/plugins/manage-plugins.md` (`openclaw plugins install --link <path>`, `--accept-capabilities`, `--force`).
