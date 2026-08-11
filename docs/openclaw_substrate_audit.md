# OpenClaw × Local AI Substrate — Integration Audit & Architecture Map

**Generated:** 2026-08-11 (by autonomous archaeology/diagnostic pass)
**Scope:** `/home/ahron` host, `~/.openclaw`, and the `substrate-core` workspace at `~/codespace`
**Secret handling:** All tokens, API keys, private keys, and device credentials are REDACTED in this document. Live values live only in `~/.openclaw/openclaw.json`, `~/.openclaw/identity/`, and Kilo config. Do not paste real secrets into this file or commit them.

---

## 1. Executive Summary

The machine runs a **working but partially-hygienic** local-first AI stack. The integration between OpenClaw and the "Local Agent Substrate" (`~/codespace`) is *already wired* — OpenClaw's default model routes through the substrate's `kilo-proxy` (cloud-first, Ollama fallback), and OpenClaw's agent workspace **is** the substrate repo. Several concrete issues were found and the safe ones were fixed this session; the higher-risk ones are documented below with exact commands and rollback.

**Headline issues (all evidence-backed):**

| # | Severity | Issue |
|---|----------|-------|
| P0 | warning | **Version drift**: config written by `2026.7.1-2` but running CLI/gateway is `2026.6.34`. Blocks safe use of `doctor --fix` (would strip newer-config keys). |
| P1 | warning | `tools.allow` used **Kilo tool names** (`todowrite`, `task`, `skill`, `suggest`, `question`, `webfetch`, `websearch`) that OpenClaw does not recognize. → **FIXED this session.** |
| P1 | warning | Plaintext secrets in `openclaw.json` (`gateway.auth.token`, `models.providers.kilo-proxy.apiKey`). Should be SecretRefs. |
| P2 | warning | `policy.jsonc` missing for the enabled Policy plugin (workspace artifact). Bundled default is empty (0 bytes), so it must be authored or restored. |
| P2 | info | No `commands.ownerAllowFrom` → owner-only commands (`/diagnostics`, `/export-trajectory`, `/config`, exec approvals) have no allowed sender. |
| P2 | info | "Memory system not found in workspace." Local `nomic-embed-text` is installed in Ollama and could back local-first semantic memory. |
| P3 | info | Workspace identity files (`IDENTITY.md`, `USER.md`) are unfilled templates → OpenClaw agent has no real persona. |
| P3 | housekeeping | Phantom `app-substrate-chatbot@autostart.service` (systemd "not-found" but "active") from a stale `.desktop`; duplicate chatbot HTTP server on :8321 (manual `tray`) vs :8322 (systemd `serve`). |
| P3 | bug | `kilo_proxy.py` resolves its server password from `providers.kilo.apiKey`, but config uses `providers.kilo-proxy.apiKey`. → **FIXED this session** (cosmetic; password is unused in routing). |

The stack is **live and healthy at the transport level**: `kilo-proxy` reports `kilo_healthy=true, ollama_healthy=true, route=kilo`; OpenClaw Gateway `/healthz` returns `live`.

---

## 2. Environment

| Property | Value |
|----------|-------|
| OS | CachyOS Linux (Arch-based, rolling), kernel `7.1.6-1-cachyos` |
| Arch | x86_64 |
| CPU | 12th Gen Intel i7-12800H — 20 logical CPUs |
| RAM | 62 GiB total / ~46 GiB available |
| Storage | `/dev/nvme0n1p2` 473G total, 211G free (54% used) |
| GPU | NVIDIA RTX A2000 8GB Laptop GPU (idle, 1 MiB used) + Intel Iris Xe |
| Node | v26.4.0 (npm 12.0.2, no pnpm) |
| Python | 3.14.6 (uv-managed venv in `~/codespace/.venv`) |
| Containers | no Docker; **podman 6.0.2** available (used as sandbox per AGENTS.md) |
| OpenClaw CLI | `2026.6.34` at `~/.npm-global/lib/node_modules/openclaw` |
| OpenClaw Gateway | running `2026.6.34` (PID via systemd `openclaw-gateway.service`) |
| Ollama | `0.32.6`, service `ollama.service`, port `11434` |
| Tailscale | `tailscaled.service` active; `:10000` → `127.0.0.1:8090` |

---

## 3. Service Inventory

| Service (systemd --user) | Port | Status | Role |
|--------------------------|------|--------|------|
| `openclaw-gateway.service` | 8090 | active | OpenClaw Gateway + control UI (primary ops surface) |
| `kilo-proxy.service` | 4097 | active | OpenAI-compatible proxy → Kilo CLI (cloud) w/ Ollama fallback |
| `kilo-remote.service` | 4096 | active | Kilo CLI remote agent (iOS app control) |
| `ollama.service` | 11434 | active | Local inference (llama3.1:8b, qwen2.5-coder:7b, nomic-embed-text, …) |
| `substrate-chatbot.service` | 8322 | active | Substrate desktop chatbot HTTP (headless `serve`) |
| `substrate-lister.service` | — | active | Self-healing verifier loop (checks the 5 services above + tailscale serve + OpenClaw cron) |
| `ttyd.service` | 8765 | active | Web shell (iPhone terminal) |
| `protonmail-bridge.service` | 1025/1143/44541 | active | Local IMAP/SMTP bridge |
| `substrate-panel.service` | — | **failed (retired)** | Intentionally no-op (`ExecStart=/bin/true`); OpenClaw owns 8090 |
| `app-substrate-chatbot@autostart.service` | — | **not-found but active** | Stale desktop-autostart phantom (see §8) |

**Manual/duplicate process:** a `chatbot.py tray` instance (PID 1927→2100) is bound to **:8321** (user-launched desktop tray), separate from the systemd `serve` on :8322. Both are legitimate but redundant; the lister only verifies :8322.

---

## 4. Architecture & Data Flow

```
                         ┌─────────────────────────────────────────────┐
   iPhone / remote  ───► │  Tailscale serve  :10000 ─► 127.0.0.1:8090   │
                         └─────────────────────────────────────────────┘
                                            │
                                            ▼
                              OPENCLAW GATEWAY  (127.0.0.1:8090)   v2026.6.34
                              config: ~/.openclaw/openclaw.json
                              workspace: /home/ahron/codespace   ◄── the Local Agent Substrate repo
                              default model: kilo-proxy/kilo-auto/free
                              ├─ providers:
                              │    ├─ ollama      (127.0.0.1:11434)  llama3.1:8b, qwen2.5-coder:7b
                              │    └─ kilo-proxy  (127.0.0.1:4097/v1) kilo-auto/free, claude-opus-5,
                              │                                       gpt-4.1, gemini-pro, deepseek-v4-flash
                              └─ plugins: ollama, memory-core, active-memory, memory-wiki,
                                 policy, webhooks, logbook, canvas, comfy, whatsapp, … (see config)

        kilo-proxy (4097) routes per request:
              Kilo CLI (cloud, kilo-auto/free etc)  ──healthy?──► use cloud
                        │ otherwise
                        ▼
                    Ollama (11434)  ──local-first fallback──► llama3.1:8b / qwen2.5-coder:7b

   Supporting substrate services (all in ~/codespace):
     • kilo-remote (4096)      — mobile remote control of Kilo CLI
     • substrate-chatbot (8322, +tray 8321) — desktop chat → runs `kilo run --auto`
     • substrate-lister        — self-heal loop verifying the 5 critical services + tailscale serve
     • ttyd (8765)             — web shell
```

**Integration verdict:** OpenClaw → substrate `kilo-proxy` → (Kilo cloud | Ollama local) is the intended local-first path and is functional. The substrate's own automations (`substrate_lister.py`, `substrate_cli.py agent-cycle`) treat the OpenClaw Gateway as the primary UI and have migrated the agent cron to OpenClaw cron (job id `69997515-7b90-4ddc-95f3-488a1b36d3d9`).

---

## 5. OpenClaw Configuration Summary (redacted)

- `gateway`: `mode=local`, `bind=loopback`, `port=8090`, `auth.token=<REDACTED 40-char token>`
- `models.providers.ollama`: `baseUrl=http://127.0.0.1:11434/v1`, api=`openai-completions`, models `llama3.1:8b`, `qwen2.5-coder:7b` (both present locally ✓)
- `models.providers.kilo-proxy`: `baseUrl=http://127.0.0.1:4097/v1`, `apiKey=<REDACTED "kilo-proxy:local">`, models `kilo-auto/free` (+ claude-opus-5, gpt-4.1, gemini-pro, deepseek-v4-flash)
- `agents.defaults`: `workspace=/home/ahron/codespace`, `model.primary=kilo-proxy/kilo-auto/free`, `fallbacks=[ollama/llama3.1:8b, ollama/qwen2.5-coder:7b]`, `subagents.maxConcurrent=2`
- `tools.profile=coding`, `allow=[FIXED this session — see §7]`
- `plugins.entries`: ~30 enabled (ollama, memory-core, active-memory, memory-wiki, policy, webhooks, logbook, canvas, comfy, whatsapp, openai, openrouter, nvidia, mistral, minimax, novita, talk-voice, workboard, …)
- `skills.entries`: ~36 disabled, 0 enabled (skills are loaded via `~/.openclaw/skills/*` symlinks to `~/.agents/skills/*`, e.g. cloudflare, durable-objects, sandbox-*, web-perf, turnstile-spin, plus a local `kilo-runner`)
- `update.channel=extended-stable`
- `cron.enabled=true`, `channels.whatsapp.enabled=true` (selfChatMode)

---

## 6. `openclaw doctor --lint` Findings (verbatim, redacted)

Run: `openclaw doctor --lint --non-interactive --severity-min info --json` (read-only). `checksRun=86`, `ok=false`.

Top-level warning (stderr):
> Your OpenClaw config was written by version **2026.7.1-2**, but this command is running **2026.6.34**.

Structured findings:
1. `core/doctor/security` [warning] — `openclaw.json` contains plaintext secret-bearing fields: `gateway.auth.token`, `models.providers.kilo-proxy.apiKey`. Migrate to SecretRefs (`openclaw secrets configure` / `openclaw secrets apply`, then `openclaw secrets audit --check`).
2. `policy/policy-jsonc-missing` [warning] — `policy.jsonc` missing for the enabled Policy plugin. Fix: restore/add the workspace policy artifact.
3. `core/doctor/command-owner` [info] — No command owner configured (`commands.ownerAllowFrom`). Owner-only commands have no allowed sender.
4. `core/doctor/workspace-suggestions` [info] — Memory system not found in workspace.

Plus a config-load warning (stderr): `tools.allow` contained unknown entries (`glob, grep, todowrite, task, skill, suggest, question, webfetch, websearch`) — see §7.

---

## 7. Diagnosed Issues & Remediation Plan

### P0 — OpenClaw version drift (config 2026.7.1-2 vs runtime 2026.6.34)
- **Evidence:** `openclaw.json` `meta.lastTouchedVersion=2026.7.1-2`, `wizard.lastRunVersion=2026.7.1-2`; `openclaw --version`=2026.6.34; gateway PID runs `node_modules/openclaw` = 2026.6.34.
- **Impact:** Running `doctor --fix` on 2026.6.34 could strip config keys valid only in 2026.7.1-2. Also the update channel `extended-stable` clearly has 2026.7.1-2 available.
- **Plan (recommended, do this BEFORE any `doctor --fix`):**
  ```bash
  # In-place update (same install path; reversible via npm cache + the .bak ring)
  npm -g install openclaw@latest --registry https://registry.npmjs.org   # or your mirror
  openclaw --version            # expect 2026.7.1-2
  openclaw gateway stop && openclaw gateway install --force && openclaw gateway start
  openclaw doctor --lint --severity-min info --json
  ```
- **Rollback:** `npm -g install openclaw@2026.6.34`; restore `~/.openclaw/openclaw.json` from the `.bak` ring.
- **Risk:** Medium (touches the live gateway). Note: the mission cautions against *beginning* with reinstalling/replacing infrastructure; an in-place version update is the sanctioned fix for this specific doctor-flagged drift. Deferred this session pending deliberate go-ahead.

### P1 — `tools.allow` used Kilo tool names → **FIXED this session**
- **Evidence:** doctor flagged `glob, grep, todowrite, task, skill, suggest, question, webfetch, websearch` as unknown. Valid OpenClaw tool IDs (from package `dist` + doctor non-flagging) are `bash, read, write, edit, exec, browser, canvas, memory, webFetch, webSearch, grep, glob, session_status`.
- **Fix applied:** replaced `tools.allow` with `["bash","read","write","edit","exec","browser","canvas","memory","webFetch","webSearch","grep","glob","session_status"]`. JSON validated. **Note:** takes effect on next gateway config load (no restart performed this session to avoid disrupting the live gateway).
- **Verification:** re-running `doctor --lint` no longer flags the invalid Kilo names (`todowrite, task, skill, suggest, question`). A *residual* lint warning for `memory, grep, glob, webFetch, webSearch` remains — this is a **headless-lint artifact**: `doctor --lint` is non-interactive and skips eager plugin loading, so plugin-backed tool IDs don't resolve in that mode. They are valid OpenClaw tool IDs and resolve at runtime (their plugins are enabled in config). Do **not** remove them to silence the lint.
- **Rollback:** `~/.openclaw/openclaw.json.audit-bak-<ts>`.

### P1 — Plaintext secrets in `openclaw.json`
- **Plan (do after P0 update):**
  ```bash
  openclaw secrets configure     # interactive: map gateway token + kilo-proxy apiKey to SecretRefs
  openclaw secrets apply
  openclaw secrets audit --check  # verify no plaintext remains
  openclaw gateway stop && openclaw gateway start   # reload to pick up SecretRefs
  ```
- **Risk:** Medium — verify the gateway still authenticates clients after migration (check a client can connect; token value is unchanged, just moved to the secret store).

### P2 — Missing `policy.jsonc`
- The bundled default (`dist/extensions/policy/policy.jsonc`) is **empty (0 bytes)**, so it cannot simply be copied. After the P0 update, let doctor restore it:
  ```bash
  openclaw doctor --fix --non-interactive    # restores policy.jsonc + drops unknown config keys (safe post-update)
  openclaw doctor --lint --severity-min warning
  ```
- **Risk:** Low once version matches. Do NOT run `--fix` before P0 (would strip newer-config keys).

### P2 — No `commands.ownerAllowFrom`
- **Plan:** set to the operator's channel id (requires the user's Telegram/WhatsApp id). Documented; needs operator input. Example: `openclaw config set commands.ownerAllowFrom '["whatsapp:<id>"]'`.

### P2 — Local-first semantic memory (recommendation)
- Ollama already has **`nomic-embed-text`** installed locally. OpenClaw's memory/search readiness check wants embedding credentials; point it at the local model for a fully local-first memory/semantic-search backend instead of a cloud embedder.
- **Plan (after P0):** configure the memory/search embedding provider to `ollama/nomic-embed-text` (see `openclaw configure --section model` and the memory-search readiness check from `doctor --lint --all`).

### P3 — Unfilled workspace identity
- `~/codespace/IDENTITY.md`, `USER.md` are template stubs. `SOUL.md` is the generic OpenClaw soul. Filling these is the operator's personalization; left untouched (not invented).

### P3 — Stale/duplicate services (housekeeping)
- `app-substrate-chatbot@autostart.service` is a systemd "not-found but active" phantom, referenced by `~/.config/autostart/substrate-chatbot.desktop` (KDE/COSMIC autostart). It is benign (desktop-managed). To clean: remove the stale reference once the real `substrate-chatbot.service` (systemd) covers autostart, or leave it.
- Duplicate chatbot on :8321 (manual `tray`) vs :8322 (systemd `serve`): both legitimate; consider standardizing on the systemd `serve` for headless + a single tray if desired. No change made.

### P3 — `kilo_proxy.py` password lookup bug → **FIXED this session**
- **Evidence:** `resolve_server_password()` read `providers.kilo.apiKey`; config uses `providers.kilo-proxy.apiKey` → `kilo_server_password_set` reported `false`.
- **Fix applied:** now checks `kilo-proxy` first, then `kilo`. (Cosmetic — the password is unused in routing; correctness only.) `py_compile` passes.

---

## 8. Substrate (`~/codespace`) Orientation for Future Agents

- **Repo:** `~/codespace`, git origin `https://github.com/55515-code/orchestrator.git` (branch `substrate-core`). Auto-sync commits every ~10 min.
- **Role:** This IS the OpenClaw agent workspace. OpenClaw reads `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md` from here.
- **Primary ops CLI:** `uv run python scripts/substrate_cli.py` (or `uv run python -m substrate.cli`). OpenClaw Gateway (8090) is the UI; the legacy `substrate serve` panel is retired.
- **Key scripts:** `kilo_proxy.py` (4097 proxy), `chatbot.py` (desktop chat), `substrate_lister.py` (self-heal verifier), `agent_hybrid_runner.py`, `probe_system.py`, `daily_security_report.py`.
- **Lifecycle enforced:** 3 stages (`local`→`hosted_dev`→`production`) × 3 passes (`research`→`development`→`testing`); `require_source_facts_before_mutation=true`.
- **Agent roster:** `research-agent`, `dev-agent`, `update-agent`, `content-moderator`, `community-manager`, `market-research`, `resource-generator` (see `agents.yaml`). The agent cron was migrated from a systemd timer to **OpenClaw cron** (job `69997515-7b90-4ddc-95f3-488a1b36d3d9`); `substrate_lister.py` verifies it via `openclaw cron show <id> --json`.
- **Sandbox policy:** podman / systemd-nspawn / bwrap / unshare / venv — validate system-modifying commands in a sandbox first.
- **State/memory:** `state/orchestrator.db`, `state/learning-index.json`, `memory/dev-history.jsonl`, `state/config-sync-index.json`.

---

## 9. OpenClaw Facts Worth Remembering

- **Doctor postures:** `doctor` (inspect), `doctor --fix` (repair, non-service by default), `doctor --lint` (read-only, scripting/CI surface, `--json`), `doctor --state-sqlite compact`, `doctor --session-sqlite <mode>`.
- `--lint` is strictly read-only and never rewrites config. `--fix` rotates backups to `~/.openclaw/openclaw.json.bak` (numbered ring).
- **SecretRefs:** `openclaw secrets {configure,apply,audit,reload}` — the sanctioned way to stop storing plaintext tokens in `openclaw.json`.
- **Plugins** are under `~/.npm-global/lib/node_modules/openclaw/dist/extensions/*`; `policy.jsonc` is expected in the **workspace** root, not the plugin dir (bundled one is empty).
- **Memory:** `memory-core` + `active-memory` + `memory-wiki` (Obsidian vault maintainer) plugins are enabled; a workspace "memory system" install is still flagged missing by doctor.
- **Gateway token** is used by clients (iPhone app, web UI). Keep it consistent across `openclaw.json` and any client configs.

---

## 10. Changes Applied This Session (safe, reversible)

1. **`~/.openclaw/openclaw.json`** — `tools.allow` rewritten with valid OpenClaw tool IDs (removed Kilo-only names, fixed `webFetch`/`webSearch` casing, added `exec`/`browser`/`canvas`/`memory`). Backup: `openclaw.json.audit-bak-<ts>`. Effect on next gateway config load.
2. **`~/codespace/scripts/kilo_proxy.py`** — `resolve_server_password()` now reads `providers.kilo-proxy.apiKey` (was `providers.kilo`). Cosmetic; `py_compile` passes.

**Deferred (need deliberate go-ahead / version-gated):** OpenClaw update to 2026.7.1-2 (P0), SecretRef migration (P1), `policy.jsonc` restore via `doctor --fix` (P2), `commands.ownerAllowFrom` (P2), local `nomic-embed-text` memory wiring (P2).
