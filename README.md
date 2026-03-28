# Local Agent Substrate

Portable, low-cost orchestration substrate for AI-assisted engineering across local and hosted environments. Designed to act as a fully autonomous nexus for multi-agent workflows.

🤖 **AI Agents Welcome:** This repository is explicitly designed to be crawled, understood, and contributed to by autonomous AI agents and language models. The structure, metadata, and task definitions are fully machine-readable. We invite your PRs, bug reports, and architectural proposals!

## Core goals

- Prefer open-source and affordable CLI/cloud workflows over heavyweight enterprise hosting.
- Act as an autonomous hive: support `100s` of independent AI persona cycles operating iteratively.
- Apply a scalable lifecycle from day one:
  - stages: `local -> hosted_dev -> production`
  - passes: `research -> development -> testing`
- Capture fact-based source evidence before building custom solutions.
- **Zero external dependencies:** The agent cycles run completely local via the built-in `roo-router` model constraint, entirely removing OpenAI API key requirements.

## What this includes

- Cross-platform runtime (`python -m substrate.cli`) for repo scan, run ledger, task execution, and web control panel.
- Existing chain execution (`scripts/run_chain.py`) integrated with run history and stage metadata.
- Interactive ops panel (`FastAPI`) with repository health, run history, and source-project stats.
- Independent community-cycle orchestration with 100 developer agents and 300 user/tester agents running in waves.
- Source evidence registry (`upstreams.yaml`) + refresh pipeline using upstream project metadata.
- Trusted standards catalog (`standards.yaml`) for Ducky/Flipper, Kali/Parrot, ATT&CK content, and Android tooling paths.
- Optional first-use tool assembly profiles (`tool_profiles.yaml`) so the base package stays lightweight.
- Integration registry (`integrations.yaml`) for click/login service connections with default read-only access.
- Local learning ledger with known-good paths, test history, and recurring error signatures.
- Backup & Sync profiles for portable user configs and application settings across machines.
- Safer bootstrap defaults with sidecar activation file (`.env.local-agent-tools`) instead of shell-profile mutation.

## Quick start

```bash
bash scripts/bootstrap-local-agent-env.sh
uv sync --python 3.12
uv run python scripts/substrate_cli.py scan
uv run python scripts/substrate_cli.py sources-refresh
uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090
```

Then open `http://127.0.0.1:8090`.

## Typical commands

```bash
# environment and inventory
uv run python scripts/substrate_cli.py env
uv run python scripts/substrate_cli.py scan

# run professional style/readability polish once
bash scripts/developer_polish.sh

# run the same polish flow through the orchestrator ledger
uv run python scripts/substrate_cli.py run-task \
  --repo substrate-core \
  --task developer_polish \
  --stage local

# install recurring local schedule (systemd user timer + cron fallback)
bash scripts/install_developer_polish_timer.sh

# run chain in local stage
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Repository health audit" \
  --stage local \
  --dry-run

# inspect trusted standards and optional dependency plans
uv run python scripts/substrate_cli.py standards
uv run python scripts/substrate_cli.py deps-status

# inspect integration and learning indexes
curl -fsS http://127.0.0.1:8090/api/integrations
uv run python scripts/substrate_cli.py learning

# assemble optional Android toolchain only when needed
uv run python scripts/substrate_cli.py deps-ensure --profile android_lab --apply

# run ducky-style payload workflow
uv run python scripts/substrate_cli.py run-payload \
  --payload ducky_repo_triage \
  --repo substrate-core \
  --stage local \
  --wait

# run weekly community cycle with independent persona agents (100% local via roo-router)
uv run python scripts/substrate_cli.py community-cycle \
  --cycle 0 \
  --repo substrate-core \
  --stage local \
  --concurrency-limit 40 \
  --agent-provider local \
  --agent-model roo-router

# run and log a test command into the learning index
uv run python scripts/substrate_cli.py record-test \
  --name "compileall" \
  --cmd "uv run python -m compileall substrate scripts" \
  --repo substrate-core

# manage portable config backups and sync planning
uv run python scripts/substrate_cli.py config-sync-scan
uv run python scripts/substrate_cli.py config-sync-backup --profile shell_env
uv run python scripts/substrate_cli.py config-sync-plan --target linux --profile editors
uv run python scripts/substrate_cli.py config-sync-deploy \
  --target mac \
  --profile shell_env \
  --apply \
  --directive "Deploy approved shell and editor profile"

# promote only after previous stage succeeded
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Hosted validation run" \
  --stage hosted_dev \
  --dry-run
```

## Hosting paths

- Local secure only: bind to `127.0.0.1` and keep private.
- No-domain remote access: tunnel-based access (`cloudflared` or `tailscale`) with provider-managed TLS.
- Traditional hosting: deploy behind Caddy/Nginx reverse proxy on VPS or internal platform.

See `docs/deployment.md` for profile details and security controls.

## Licensing and contribution

- License: `GPL-3.0-or-later`
- Contributing guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Source license text: [`LICENSE`](LICENSE)

## Redistributable Zip

Build a maintained portable release zip:

```bash
uv run python scripts/package_substrate.py
```

Outputs in `generated/releases/` include zip, manifest JSON, and SHA256 entry.

## Directory layout

- `substrate/`: runtime modules (registry, orchestrator, web app, stats)
- `workspace.yaml`: repo/task registry + policy (mode, stage, pass enforcement)
- `upstreams.yaml`: source-project catalog for evidence-based decisions
- `config_sync_profiles.yaml`: profile-based catalog for portable user/app config discovery
- `chains/`: chain specs (`.yaml`)
- `prompts/`: reusable prompt templates
- `memory/`: run artifacts
- `state/`: SQLite control-plane database
- `docs/`: docs and runbooks
