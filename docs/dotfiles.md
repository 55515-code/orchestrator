# Backup & Sync

The control panel can manage local dotfiles and common application configs as an indexed, portable config set rather than a pile of ad-hoc shell edits.

Profile definitions live in `config_sync_profiles.yaml` and can be extended without changing backend code.

## Workflow

1. Scan the current user environment and discover dotfiles plus app config locations.
2. Back up selected files into the workspace before making changes.
3. Organize and convert configs for the target environment.
4. Plan deployment first, then apply only when an explicit write directive is provided.

## Storage

- Index: `state/config-sync-index.json`
- Backups: `memory/config-sync/backups/<timestamp>/...`

The index tracks source paths, checksums, backup timestamps, deployment metadata, and profile labels so the known-good state can be reused instead of rediscovered.

## CLI

```bash
# discover and index local config sources
uv run python scripts/substrate_cli.py config-sync-scan

# create a workspace backup snapshot
uv run python scripts/substrate_cli.py config-sync-backup --profile shell_env

# preview a deployment to another environment
uv run python scripts/substrate_cli.py config-sync-plan --target linux --profile editors

# apply a deployment only with an explicit directive
uv run python scripts/substrate_cli.py config-sync-deploy \
  --target mac \
  --profile shell_env \
  --apply \
  --directive "Deploy approved shell and editor profile"
```

## Safety Model

- Default behavior is `read` and `plan` only.
- Writes to external environments require an explicit directive.
- Keep backups before conversion or deployment.
- Prefer a plan review on a local machine before pushing configs to another OS or host.
- Use the legacy `dotfiles-*` aliases only for compatibility with older automation.

## Recommended Order

Use the panel in this order:

1. Scan
2. Backup
3. Plan
4. Apply

This keeps the workflow reversible and preserves the local baseline.
