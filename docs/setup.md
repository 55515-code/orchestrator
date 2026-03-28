# Setup

## Bootstrap

```bash
bash scripts/bootstrap-local-agent-env.sh
```

The bootstrap script installs into `~/.local/bin`:

- `uv` for Python/runtime and dependency management
- `mise` for tool version management (`node`, `just`, `pnpm`)
- `direnv` for automatic per-directory environment loading

Optional capability tooling is intentionally not bundled into the base package.
Use first-use assembly when needed:

```bash
uv run python scripts/substrate_cli.py deps-status
uv run python scripts/substrate_cli.py deps-ensure --profile android_lab --apply
```

By default it does **not** mutate shell profiles. Instead it writes:

- `.env.local-agent-tools`

Activate manually:

```bash
source .env.local-agent-tools
```

If you want automatic shell hooks, run:

```bash
bash scripts/bootstrap-local-agent-env.sh --apply-shell-hooks
```

## Configure env vars

```bash
cp .env.example .env
```

Fill provider credentials only for providers you will use.

## Sync dependencies

```bash
uv sync --python 3.12
```

## Enable recurring polish task (optional)

```bash
bash scripts/install_developer_polish_timer.sh
```

This schedules `scripts/developer_polish.sh` with a user-level systemd timer when
available and prints a cron fallback otherwise.

## Launch control panel

```bash
uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090
```
