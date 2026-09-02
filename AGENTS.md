# Kilo Agent Instructions — Local Agent Substrate

## Project Overview

This is the **Local Agent Substrate** — a portable, low-cost orchestration substrate for AI-assisted engineering across local and hosted environments. It acts as a fully autonomous nexus for multi-agent workflows.

## How Kilo Should Interact With This Project

### Primary Interface

Use the substrate CLI via `uv run python -m substrate.cli` or `uv run python scripts/substrate_cli.py`. The CLI provides all operational commands.

**Note:** OpenClaw Gateway is the primary ops UI on `127.0.0.1:8090`. The legacy substrate panel (`substrate serve`) is retired; use it only for local dev on alternative ports if needed.

### Key Commands

- `/scan` — Run a repository scan and health check
- `/serve` — Start the ops panel (FastAPI web UI) on 127.0.0.1:8090
- `/run-task` — Execute a named task from workspace.yaml
- `/community-cycle` — Run a community simulation cycle
- `/deps-ensure` — Install optional tool dependencies by profile
- `/learning` — View the execution learning index
- `/standards` — View the trusted standards catalog
- `/integrations` — View integration status
- `/tooling` — Check tooling availability and profiles
- `/research` — Refresh upstream research data
- `/payload` — Run a Ducky-style payload workflow
- `/chain` — Execute a chain of tasks
- `/record-test` — Record a test result in the learning index
- `/probe` — Generate a cross-platform system profile
- `/storage-status` — Report filesystem facts and the recommended Btrfs plan
- `/storage-validate` — Validate Btrfs recommendations against the tooling stack
- `/storage-maintenance` — Run Btrfs dedup/defrag maintenance (dry-run; `--apply` to execute)

See `docs/btrfs-optimization.md` for the storage-layer tradeoffs and runbook.

### Panel Security

The ops panel (`substrate-panel.service`, 127.0.0.1:8090) enforces, in
`substrate/web.py`:

- **Origin/Host CSRF + DNS-rebinding checks** — state-changing requests must
  come from a loopback host or the machine's own Tailscale name (`tailscale
  serve`); HMAC-protected `/gateway/*/webhook` paths are exempt.
- **Bearer-token auth** — every POST/PUT/PATCH/DELETE requires
  `Authorization: Bearer <token>` when `PANEL_AUTH_TOKEN` is configured. The
  token lives in the service unit and is mirrored to `state/panel-auth-token.txt`
  (mode 600) for operator reference. GET endpoints remain open.
- **Per-IP rate limiting** — 100 requests/minute per client; excess requests
  get `429` with a `Retry-After` header. The browser UI authenticates
  automatically via the same-origin `/__panel_auth_bootstrap__.js` bootstrap.
- **XSS hardening** — `escapeHtml()` in `substrate/static/control-panel.js`
  escapes all user-generated content before `innerHTML` interpolation.
- **Shell injection hardening** — automation prompts are passed to `run.sh` as
  argv elements, never interpolated into a shell string
  (`substrate/iphone_panel.py`).

Rotate the token by regenerating it with
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"` and updating
`Environment=PANEL_AUTH_TOKEN` in `~/.config/systemd/user/substrate-panel.service`.

### Desktop Chatbot

A desktop chatbot (`substrate/chatbot/`) gives the user a chat interface that
runs autonomous Kilo tasks for desktop and internet automation. It reuses the
existing Kilo CLI (`kilo run --auto --format json`) and inherits the user's
existing Kilo permission configuration.

**Run it:**
- `uv run python scripts/chatbot.py tray` — tray icon (panel) + HTTP server + chat UI
- `uv run python scripts/chatbot.py serve` — headless HTTP server only
- `uv run python scripts/chatbot.py open` — start server if needed, open chat UI in browser
- `uv run python scripts/chatbot.py status` — server status JSON
- `bash scripts/install_chatbot.sh` — app launcher, autostart, icon, optional systemd service

**How it works:**
- `POST /api/chat` enqueues a task; the worker runs
  `kilo run --auto --format json --dir <workspace> [--session <id>] <message>`.
- JSON events stream back over SSE (`/api/stream/<task_id>`): text, tool calls,
  model info, done. Multi-turn conversation continues via the captured Kilo
  session id.
- Sessions persist as JSONL under `state/chatbot/sessions/`.
- Autonomy is bounded by the user's Kilo permission config (deny rules still
  block dangerous actions even with `--auto`).
- Config: `~/.config/kilo/chatbot.json` — fields: `host`, `port`, `workspace`,
  `kilo_binary`, `agent`, `model`, `kilo_config`, `task_timeout_seconds`.

**Future extension points:** additional services hook in via the same task
queue; voice input can be added in the chat UI or tray without changing the
agent runner.

### Workflow Enforcement

The substrate enforces a 3x3 lifecycle:
- **Stages**: `local` → `hosted_dev` → `production`
- **Passes**: `research` → `development` → `testing`

Always follow this order. Do not skip stages or passes.

### Policy Constraints

- `default_mode` is `mutate` but `require_source_facts_before_mutation` is `true` — always collect source evidence before making changes.
- RC1 OpenClaw assist is enabled only for `local` and `hosted_dev` stages and `research` pass only.
- Bounded validation is enabled with max 2 attempts and a 60-second deadline.
- Watchdog is enabled with max 1 respawn.

### Repository Configuration

The primary repository is `substrate-core` (the current workspace). Additional repositories are auto-discovered via git detection up to depth 2.

### Ignored Paths

The following paths are ignored by the substrate and should not be included in analysis:
- `.git`, `.venv`, `.direnv`, `node_modules`
- `aosp-eos-asteroids`, `work`, `tmp`, `downloads`, `tools`, `site`

### State and Memory

- SQLite database: `state/orchestrator.db`
- Learning index: `state/learning-index.json`
- Learning log: `memory/dev-history.jsonl`
- Config sync index: `state/config-sync-index.json`

### Key Configuration Files

| File | Purpose |
|------|---------|
| `workspace.yaml` | Repository/task registry and policy |
| `agents.yaml` | Agent roster (roles, cadence, autonomy tiers, providers) |
| `standards.yaml` | Trusted standards catalog (Ducky, Kali, ATT&CK, Android) |
| `tool_profiles.yaml` | Optional tool assembly profiles |
| `integrations.yaml` | External service integration registry |
| `upstreams.yaml` | Source-project catalog for evidence-based decisions |
| `config_sync_profiles.yaml` | Portable config backup/sync profiles |

### Agent Automation

A roster of scheduled agents in `agents.yaml` performs research, development,
update, and moderation work across substrate-core, LuigiOS, and
ahrondarnell-site. Implementation lives in `substrate/agents/`.

**Roster:**
- `research-agent` (per repo, daily, Tier 0) — refreshes upstream source facts, writes evidence notes to `.research/<repo>/`, satisfies `require_source_facts_before_mutation`.
- `dev-agent` (per repo, daily, Tier 1) — picks a backlog issue (GitHub via `gh`, else local TODO scan), generates a patch via `chains/local-agent-chain.yaml` in an isolated worktree (`agent/<repo>/dev-<date>` branch), runs bounded validation, commits only when tests are green.
- `update-agent` (per repo, weekly, Tier 1) — dependency bumps (`uv lock --upgrade`, `npm audit fix`), polish workflows, docs freshness checks; commits only when tests are green.
- `content-moderator` (ahrondarnell-site, hourly, Tier 1) — triages the site queue; auto-applies hold/needs-changes marks, writes rationale to `.research/site-moderation/`; approvals/rejections remain human-only.
- `community-manager` (cross-repo, every 4h, Tier 1) — WhatsApp gateway status, GitHub issue/PR triage drafts, community simulation cycles (`.research/community-sim/`); never sends outbound messages.
- `market-research` (substrate-core, weekly, Tier 0) — the sales research swarm: scans advertising channels and agent-commerce protocols (x402, agent marketplaces, LLM discovery) into `.research/market-demand/`, and refreshes the always-selling posture dashboard (`state/sales-posture.json`). Passive/pull-based only.
- `resource-generator` (substrate-core, weekly, Tier 1) — consumes `state/resource-backlog.json` from the expansion trigger, drafts resources through the quality gate; publishing into `resources/catalog.json` stays Tier 2.

**Autonomy tiers:**
- Tier 0: always automatic (notes, reports, branches, test runs).
- Tier 1: automatic only when validation is green (agent-branch commits, queue hold/needs-changes).
- Tier 2: always requires an explicit human directive (merges, deploys, publishing, queue approvals, outbound replies, ALL crypto financial operations: wallet generation, price updates, opportunity spend, refunds). Promoting an action (e.g. Tier 2 → Tier 1) requires editing the tier checks in `substrate/agents/` and the agent's `autonomy_tier` in `agents.yaml` with explicit approval.

**Commands:**
- `uv run python scripts/substrate_cli.py agent-cycle` — run every due agent sequentially (used by the systemd timer).
- `uv run python scripts/substrate_cli.py agent-run --role <role> --repo <slug> [--force] [--directive <text>]` — run one agent manually.
- `uv run python scripts/substrate_cli.py agent-status` — show roster, last runs, next due times.
- `uv run python scripts/crypto/wallet_gen.py create --purpose <p> --directive <text>` — generate a wallet (Tier 2).
- `uv run python scripts/crypto/wallet_gen.py backup` / `list` / `public-address --purpose <p>` / `verify-recovery --purpose <p>`.
- `uv run python scripts/crypto/backup_proton.py` — verified encrypted backup (Proton Drive sync folder or staged).
- `uv run python scripts/crypto/export_site_data.py` — regenerate `resources/llm-catalog.json`, site `src/data/*.ts`, and `workers/d1-seed.sql` from source of truth.

**Scheduler:** `scripts/install_agent_timer.sh` installs the
`substrate-agent-timer` systemd user timer (every 5 minutes; `agent-cycle`
evaluates cadence internally). Logs: `journalctl --user -u
substrate-agent-timer`. Rollback: `systemctl --user stop
substrate-agent-timer.timer`. Idempotency keys in `state/agent-idempotency/`
prevent duplicate runs; stale agent branches/worktrees (>30 days) are cleaned
on each cycle. Agent state: `state/agent-state.json`.s |

### Safety Rules

- Never expose secrets or credentials in outputs.
- Never send repository contents to cloud AI tools without explicit approval.
- Always validate source facts before mutation.
- Prefer maintained open-source standards over custom solutions.
- Keep the base package lean; assemble optional tooling on first use.

### Development Flow

1. Make changes locally first.
2. Run `uv run python -m compileall substrate scripts` to verify syntax.
3. Run `uv run python scripts/substrate_cli.py scan` for health check.
4. Run `uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090` for the ops panel.
5. Update documentation when behavior changes.

### Testing

- `uv run --with pytest --with httpx pytest -q tests` for full test suite

### Packaging

- `uv run python scripts/package_substrate.py` builds a portable release zip in `generated/releases/`

### Sandboxed Execution Policy

All system-modifying commands MUST be validated in a sandbox first:

1. **Python/uv work**: Use `uv` managed environments (automatic isolation)
2. **System packages**: Test in `podman run --rm archlinux` first
3. **File restoration**: Review via `git show HEAD:<path>` before checkout
4. **Config changes**: Diff review before application
5. **Destructive operations**: Always require explicit user approval

**Promotion criteria**:
- Command succeeds in sandbox with expected output
- No unintended side effects observed
- Rollback plan documented

**Sandbox tools available**:
- `podman` — container isolation
- `systemd-nspawn` — lightweight container
- `bwrap` (bubblewrap) — sandboxing
- `unshare` — namespace isolation
- Python `venv` — virtual environment isolation

### Infrastructure Health Check

Run `bash scripts/health_check.sh` to validate substrate infrastructure integrity. This checks:
- Critical files exist (pyproject.toml, uv.lock, workspace.yaml, etc.)
- Critical directories exist (substrate/, scripts/, docs/, tests/, state/)
- Key scripts exist (substrate_cli.py, probe_system.py, etc.)
- Required tools are available (uv, python3, git)
- Python syntax is valid (compileall)
- Substrate scan succeeds

The CI pipeline runs this check automatically on every push/PR.

### Sandboxed Execution Policy

All system-modifying commands MUST be validated in a sandbox first:

1. **Python/uv work**: Use `uv` managed environments (automatic isolation)
2. **System packages**: Test in `podman run --rm archlinux` first
3. **File restoration**: Review via `git show HEAD:<path>` before checkout
4. **Config changes**: Diff review before application
5. **Destructive operations**: Always require explicit user approval

Promotion criteria:
- Command succeeds in sandbox with expected output
- No unintended side effects observed
- Rollback plan documented

### Infrastructure Health Check

Run `bash scripts/health_check.sh` to validate substrate infrastructure integrity. This checks:
- Critical files exist (pyproject.toml, uv.lock, workspace.yaml, etc.)
- Critical directories exist (substrate/, scripts/, docs/, tests/, state/)
- Key scripts are present
- Required tools are available (uv, python3, git)
- Python syntax is valid (compileall)
- Substrate scan succeeds

The CI pipeline automatically runs this check on every push/PR.

## Tools

### Local notes (migrated from TOOLS.md)

# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup: camera names and locations, SSH hosts and aliases, preferred TTS voices, speaker/room names, device nicknames, anything environment-specific.

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Android OpenClaw node

- Preferred node: `nothing-3a` (`a303aa5317ec48d38527a49eb3f2b99d269de1b6455b8164e2b468f1ef7dd55e`).
- Use it only when connected **and** `nodes status` shows the required command declared (not merely a capability label): Android/Termux-specific checks need `system.run`, mobile browser work needs `browser.proxy`, and bounded local inference needs a compatible model returned by discovery.
- Keep ordinary repository commands, scheduled agents, builds, and tests on the gateway unless the task specifically benefits from Android. Never assume the phone has the workspace or host dependencies.
- For shell work on Android, call exec explicitly with `host=node`; `tools.exec.node` pins that explicit route while `tools.exec.host=auto` preserves gateway fallback for regular work.
- Browser node routing is manual and pinned to this device; target the node explicitly. If it is offline or its browser proxy is unavailable, use the gateway browser instead.
- Do not route sensitive sensor, SMS, camera, screen-recording, or outbound actions to the phone without the normal permission and user-confirmation checks.
- Local inference is opportunistic only: run discovery first and fall back if no compatible Ollama model is advertised.
- Current verification (2026-08-23): pairing was refreshed successfully and the node now declares `system.run`, `system.which`, `system.execApprovals.get/set`, and `browser.proxy`. `system.which` works. Direct exec is still denied by the phone's node-host runtime despite an effective full/off/full approvals policy, so keep gateway fallback mandatory until the node host is upgraded or restarted with corrected approval handling. Browser proxy reaches the phone but no supported Chromium executable is installed; local inference advertises a capability but no compatible Ollama service/model is currently discoverable.

## Related

- [Agent workspace](/concepts/agent-workspace)
