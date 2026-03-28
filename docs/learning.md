# Learning Ledger

The substrate now keeps a local development memory so solved paths can be reused.

Storage:

- Log stream: `memory/dev-history.jsonl`
- Aggregated index: `state/learning-index.json`

What is captured:

- Successful commands/tests as known-good paths.
- Recurring error signatures with counts and last-seen timestamps.
- Change context snapshots (branch/dirty state/last commit) for repo-scoped runs.

## CLI

```bash
# inspect index
uv run python scripts/substrate_cli.py learning

# run and log a test command
uv run python scripts/substrate_cli.py record-test \
  --name "compileall" \
  --cmd "uv run python -m compileall substrate scripts" \
  --repo substrate-core

# attach a reusable fix note to an error signature
uv run python scripts/substrate_cli.py learning-resolve \
  --signature <signature> \
  --resolution "Use source-fact refresh before mutate mode"
```

## API

- `GET /api/learning`
- `POST /api/learning/resolve`

The dashboard surfaces both known-good paths and the error index for reuse during future runs.
