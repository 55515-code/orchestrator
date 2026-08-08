# Caching Workflow

The substrate includes a lightweight, dependency-free caching layer designed to
reduce redundant AI calls and repeated computation in local automation
workflows.  It is built on SQLite and the filesystem, so it works out of the
box without extra services or network dependencies.

## Design

- **Deterministic keys**: every cache entry is keyed by a SHA-256 digest of a
canonical JSON representation of `(kind, inputs)`.  The same objective,
context, provider, and model always produce the same key.
- **Summaries**: each entry stores a short extractive summary alongside the full
blob.  Summaries make cache status readable and enable lightweight trace
assembly without loading every result.
- **Subtask decomposition**: large objectives are split into smaller,
independently cacheable subtasks.  Future runs reuse subtasks that have not
changed and only invoke the AI for genuinely new work.
- **TTL and pruning**: entries can expire automatically and the cache can be
pruned by age or total size.

## Storage layout

Cache metadata lives in `state/cache/cache.db` and full values are stored as
pickle blobs under `state/cache/blobs/`.

## CLI usage

```bash
# Show cache statistics and recent entries
uv run python scripts/substrate_cli.py cache-status

# Filter by kind
uv run python scripts/substrate_cli.py cache-status --kind ai_call

# Clear entries
uv run python scripts/substrate_cli.py cache-clear --kind ai_call
uv run python scripts/substrate_cli.py cache-clear --tag openai --older-than-days 7

# Prune expired and old entries, optionally capping total size
uv run python scripts/substrate_cli.py cache-prune --max-age-days 30
uv run python scripts/substrate_cli.py cache-prune --max-age-days 7 --max-size-mb 512

# Run a chain without reading or writing the cache
uv run python scripts/substrate_cli.py run-chain \
  --repo substrate-core \
  --objective "Repository health audit" \
  --stage local \
  --no-cache
```

## Programmatic usage

```python
from substrate.cache_store import CacheStore
from substrate.task_cache import TaskCache

store = CacheStore("state/cache")
task_cache = TaskCache(store)

# Cache a single AI call
def runner(prompt: str) -> str:
    return call_llm(prompt)

result, meta = task_cache.cached_invoke(
    "openai", "gpt-4.1-mini", prompt, runner
)

# Decompose an objective and reuse cached subtasks
report = task_cache.run_cached_subtasks(
    objective="Audit repository health",
    context="substrate-core on feature branch",
    runner=runner,
    provider="openai",
    model="gpt-4.1-mini",
)

# Cache a high-level plan
plan = task_cache.cached_plan(
    objective="Plan migration to hosted_dev",
    context="Current local tests pass",
    planner=runner,
)
```

## Cache kinds

| Kind | Purpose |
|------|---------|
| `ai_call` | Raw provider invocation keyed by provider, model, prompt, and temperature. |
| `subtask` | Result of a decomposed subtask. |
| `plan` | High-level plan for an objective. |

## Best practices

- Keep prompts stable: whitespace or formatting changes produce different cache
  keys.
- Use `--no-cache` when reproducibility or fresh reasoning is required.
- Prune regularly in long-lived environments to control disk usage.
- Treat cached results as local acceleration, not as durable audit evidence;
  the orchestrator still records run events and artifacts separately.
