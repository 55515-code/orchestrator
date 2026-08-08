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

# Hugging Face Inference API (set HF_TOKEN)
uv run python scripts/run_chain.py --objective "Repository health audit" --provider huggingface --model meta-llama/Llama-3.1-8B-Instruct
```

The control-plane `run-chain` command caches AI calls by default.  To bypass the
local cache for a single run, add `--no-cache`:

```bash
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Repository health audit" \
  --stage local \
  --no-cache
```

Outputs are written to `memory/runs/<timestamp>/`.

## LuigiOS polish chain

A dedicated chain is available for iterating on the LuigiOS workstation polish:

```yaml
# chains/luigios-polish-chain.yaml
```

Pipeline steps:

1. `diagnose` — baseline scan against release-readiness, design tokens, assets, brand consistency, and accessibility
2. `prioritize` — rank gaps by impact and surface
3. `refine_brand` — fix design token, color, and WCAG contrast issues
4. `refine_desktop` — polish COSMIC session, panel, dock, and terminal configuration
5. `refine_assets` — optimize wallpapers, icons, and boot assets
6. `cleanup_legacy` — purge legacy terms from all tracked files
7. `validate` — run the full test suite and release-readiness scorecard
8. `report` — generate findings and update the learning index

Run the LuigiOS polish chain against the `luigios` repo:

```bash
uv run python scripts/substrate_cli.py run-chain \
  --repo luigios \
  --objective "Polish COSMIC session density and focus states" \
  --chain chains/luigios-polish-chain.yaml \
  --stage local \
  --provider local \
  --model roo-router
```

Tasks are also registered directly in `workspace.yaml` under the `luigios` repo.  Run
an individual task:

```bash
uv run python scripts/substrate_cli.py run-task \
  --repo luigios \
  --task luigios_automation \
  --stage local
```

Control-plane equivalent (stage-aware):

```bash
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Repository health audit" \
  --stage local \
  --dry-run
```
