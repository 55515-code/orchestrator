# Tooling Rationale

This substrate uses established open-source tools to avoid custom infrastructure:

1. `uv` (Astral): fast Python/package/runtime management.
2. `mise` (jdx): version-managed multi-language toolchain (`node`, `pnpm`, `just`).
3. `direnv`: automatic per-directory environment activation.
4. `LangChain` + `LangGraph`: standardized prompt orchestration and chain execution.
5. `MkDocs Material`: local docs portal and runbook publishing.
6. `FastAPI` + `uvicorn`: lightweight ops API/panel runtime.
7. `SQLite`: portable local state backend with no managed service dependency.

Design principles:

- User-space installation by default (`~/.local/bin`) to avoid root coupling.
- Declarative configuration (`mise.toml`, chain YAML, prompt templates).
- Idempotent bootstrap script with repeatable outputs.
- Run artifacts persisted to `memory/runs/<timestamp>/`.
- Favor open-source and low-cost deploy patterns before enterprise-only services.
