# Render Router

Dynamic orchestration of image-generation jobs across local GPU engines and hosted AI APIs.

## Overview

The render router picks the best available engine for each job, falls back on failure, and records quality/latency/cost telemetry so the system learns which engine to prefer.

**Routing principle:** local-first, quality-by-default, with explicit opt-in for paid hosted APIs.

## Engines

Engines are declared in `render_profiles.yaml`. Each engine declares:
- `kind`: `local_gpu` or `hosted_api`
- `capabilities`: `text_to_image`, `image_to_image`, `edit`, `inpaint`, `style_reference`, `upscale`
- `quality_tier` / `speed_tier` / `cost_per_image_usd`
- `memory_strategy`: `cuda`, `model_cpu_offload`, `sequential_cpu_offload`, `none`

The router sorts candidates by `optimize_for` (`quality`, `speed`, `cost`) and walks the `fallback_order` until it finds an available engine.

## Configuration

```yaml
version: 1
defaults:
  optimize_for: quality
  allow_hosted: false        # spend must be explicitly opted into
  max_cost_usd: 0.50
  local_first: true
  fallback_order:
    - local_flux2_klein
    - local_z_image_turbo
    - local_noobai_xl
    - local_sdxl
    - openai_gpt_image
    - gemini_image
    - bfl_flux2
```

## CLI

```bash
# List engines with availability
uv run python scripts/substrate_cli.py render-catalog

# Dispatch a render
uv run python scripts/substrate_cli.py render-run \
  --prompt "neon cyberpunk portrait, crown, duality" \
  --width 832 --height 1216 \
  --optimize-for quality \
  --output generated/renders/test.png

# Dry-run (no generation)
uv run python scripts/substrate_cli.py render-run \
  --prompt "test" --dry-run

# Force a specific engine
uv run python scripts/substrate_cli.py render-run \
  --prompt "test" --engine local_flux2_klein

# Telemetry
uv run python scripts/substrate_cli.py render-telemetry
```

## Web API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/render/catalog` | Engine catalog + availability |
| `POST` | `/api/render/run` | Dispatch a render job (body: `RenderRequest` JSON) |
| `GET` | `/api/render/telemetry` | Per-engine leaderboard + spend |

## Hosted spend gating

Hosted APIs are disabled by default (`allow_hosted: false`). To enable:

1. Set the relevant env var (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `BFL_API_KEY`, `REVE_API_KEY`, `OPENROUTER_API_KEY`).
2. Set `allow_hosted: true` in `render_profiles.yaml` defaults.
3. Ensure `max_cost_usd` is set to a sensible budget guardrail.
4. For production spend, route through `integrations.yaml` mode gating (`write_requires_directive: true`).

## Local environment

`/tmp` on this host is a full 32 GB tmpfs. The router redirects `TMPDIR`, `HF_HOME`, `HF_HUB_CACHE`, and `TORCH_HOME` to `<repo>/state/render-cache/` before loading any local model.

Install the local inference stack:

```bash
uv sync --extra render
```

Or ad hoc (current convention):

```bash
uv run --with torch --with diffusers --with transformers --with accelerate \
  python -c "import torch; print(torch.cuda.get_device_name(0))"
```

## Telemetry

`state/render-telemetry.json` is not used. Per-engine statistics are stored in `state/orchestrator.db` (`render_events` table) and queried via `OrchestratorDB.engine_leaderboard()` / `render_spend()`.

## Caching

Identical `(engine_id, model_id, prompt, negative, width, height, steps, guidance, seed, mode, source_image, style_refs)` tuples are memoized under `state/render-cache/` via `CacheStore`.

## Integration with existing substrate

- `substrate/cli.py` — add `render-catalog`, `render-run`, `render-telemetry` subcommands (wiring documented in `substrate/render.py`).
- `substrate/web.py` — add `GET/POST /api/render/*` routes (wiring documented in `substrate/render.py`).
- `substrate/db.py` — `render_events` table + `record_render_event()` / `engine_leaderboard()` / `render_spend()` / `recent_render_events()`.
- `substrate/settings.py` — new path keys: `render_profiles`, `render_state`, `render_cache`, `render_output`.
