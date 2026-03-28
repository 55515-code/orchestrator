# Orchestrator

The substrate now includes a portable Python control plane under `substrate/`.

Primary entrypoint:

```bash
uv run python scripts/substrate_cli.py --help
```

## Key commands

```bash
# Scan repos and persist status
uv run python scripts/substrate_cli.py scan

# Refresh upstream source metadata (fact base)
uv run python scripts/substrate_cli.py sources-refresh

# Run chain
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Repository health audit" \
  --stage local \
  --dry-run

# Run developer polish workflow (lint/format/compile + voice marker scan)
uv run python scripts/substrate_cli.py run-task \
  --repo substrate-core \
  --task developer_polish \
  --stage local

# Install recurring local schedule (systemd user timer + cron fallback)
bash scripts/install_developer_polish_timer.sh

# Run control panel
uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090

# Trusted standards and optional tool profiles
uv run python scripts/substrate_cli.py standards
uv run python scripts/substrate_cli.py deps-status

# Integration state and learning index
curl -fsS http://127.0.0.1:8090/api/integrations
uv run python scripts/substrate_cli.py learning

# Assemble optional Android toolchain only when needed
uv run python scripts/substrate_cli.py deps-ensure --profile android_lab --apply

# Run a ducky-style payload workflow
uv run python scripts/substrate_cli.py run-payload \
  --payload ducky_repo_triage \
  --repo substrate-core \
  --stage local \
  --wait

# Run weekly community cycle with independent persona agents (100 + 300)
uv run python scripts/substrate_cli.py community-cycle \
  --cycle 0 \
  --repo substrate-core \
  --stage local \
  --concurrency-limit 40 \
  --agent-provider mock
```

The developer polish workflow writes logs to `memory/task-runs/` so it can be
reviewed in the same place as other local task logs.

## Safety defaults

- Default mode: `observe` (read-only orchestration).
- Mutation mode requires:
  - `--allow-mutations`
  - repo opt-in (`allow_mutations: true` in `workspace.yaml`)
  - fresh source evidence when policy requires it.
- Stage progression is enforced by default:
  - `local -> hosted_dev -> production`
  - can be bypassed only with explicit `--allow-stage-skip`.
