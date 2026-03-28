# Chains

Default chain config: `chains/local-agent-chain.yaml`

Pipeline steps:

1. `scope`
2. `research`
3. `execute`
4. `review`

Run a dry-run chain:

```bash
uv run python scripts/run_chain.py --objective "Repository health audit" --dry-run
```

Run with a real provider:

```bash
uv run python scripts/run_chain.py --objective "Repository health audit" --provider openai --model gpt-4.1-mini
```

Outputs are written to `memory/runs/<timestamp>/`.

Control-plane equivalent (stage-aware):

```bash
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Repository health audit" \
  --stage local \
  --dry-run
```
