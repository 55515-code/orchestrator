# Kilo Agent Instructions — Local Agent Substrate

## Project Overview

This is the **Local Agent Substrate** — a portable, low-cost orchestration substrate for AI-assisted engineering across local and hosted environments. It acts as a fully autonomous nexus for multi-agent workflows.

## How Kilo Should Interact With This Project

### Primary Interface

Use the substrate CLI via `uv run python -m substrate.cli` or `uv run python scripts/substrate_cli.py`. The CLI provides all operational commands.

### Key Commands

- `/scan` — Run a repository scan and health check
- `/serve` — Start the ops panel (FastAPI web UI) on 127.0.0.1:8090
- `/run-task` — Execute a named task from workspace.yaml
- `/community-cycle` — Run a community simulation cycle
- `/deps-ensure` — Install optional tool dependencies by profile
- `/learning` — View the execution learning index
- `/standards` — View the trusted standards catalog
- `/integrations` — View integration status
- `/tooling` — Check tooling availability and profiles
- `/research` — Refresh upstream research data
- `/payload` — Run a Ducky-style payload workflow
- `/chain` — Execute a chain of tasks
- `/record-test` — Record a test result in the learning index
- `/probe` — Generate a cross-platform system profile

### Workflow Enforcement

The substrate enforces a 3x3 lifecycle:
- **Stages**: `local` → `hosted_dev` → `production`
- **Passes**: `research` → `development` → `testing`

Always follow this order. Do not skip stages or passes.

### Policy Constraints

- `default_mode` is `mutate` but `require_source_facts_before_mutation` is `true` — always collect source evidence before making changes.
- RC1 OpenClaw assist is enabled only for `local` and `hosted_dev` stages and `research` pass only.
- Bounded validation is enabled with max 2 attempts and a 60-second deadline.
- Watchdog is enabled with max 1 respawn.

### Repository Configuration

The primary repository is `substrate-core` (the current workspace). Additional repositories are auto-discovered via git detection up to depth 2.

### Ignored Paths

The following paths are ignored by the substrate and should not be included in analysis:
- `.git`, `.venv`, `.direnv`, `node_modules`
- `aosp-eos-asteroids`, `work`, `tmp`, `downloads`, `tools`, `site`

### State and Memory

- SQLite database: `state/orchestrator.db`
- Learning index: `state/learning-index.json`
- Learning log: `memory/dev-history.jsonl`
- Config sync index: `state/config-sync-index.json`

### Key Configuration Files

| File | Purpose |
|------|---------|
| `workspace.yaml` | Repository/task registry and policy |
| `standards.yaml` | Trusted standards catalog (Ducky, Kali, ATT&CK, Android) |
| `tool_profiles.yaml` | Optional tool assembly profiles |
| `integrations.yaml` | External service integration registry |
| `upstreams.yaml` | Source-project catalog for evidence-based decisions |
| `config_sync_profiles.yaml` | Portable config backup/sync profiles |

### Safety Rules

- Never expose secrets or credentials in outputs.
- Never send repository contents to cloud AI tools without explicit approval.
- Always validate source facts before mutation.
- Prefer maintained open-source standards over custom solutions.
- Keep the base package lean; assemble optional tooling on first use.

### Development Flow

1. Make changes locally first.
2. Run `uv run python -m compileall substrate scripts` to verify syntax.
3. Run `uv run python scripts/substrate_cli.py scan` for health check.
4. Run `uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090` for the ops panel.
5. Update documentation when behavior changes.

### Testing

- `uv run --with pytest --with httpx pytest -q tests` for full test suite

### Packaging

- `uv run python scripts/package_substrate.py` builds a portable release zip in `generated/releases/`

### Sandboxed Execution Policy

All system-modifying commands MUST be validated in a sandbox first:

1. **Python/uv work**: Use `uv` managed environments (automatic isolation)
2. **System packages**: Test in `podman run --rm archlinux` first
3. **File restoration**: Review via `git show HEAD:<path>` before checkout
4. **Config changes**: Diff review before application
5. **Destructive operations**: Always require explicit user approval

**Promotion criteria**:
- Command succeeds in sandbox with expected output
- No unintended side effects observed
- Rollback plan documented

**Sandbox tools available**:
- `podman` — container isolation
- `systemd-nspawn` — lightweight container
- `bwrap` (bubblewrap) — sandboxing
- `unshare` — namespace isolation
- Python `venv` — virtual environment isolation

### Infrastructure Health Check

Run `bash scripts/health_check.sh` to validate substrate infrastructure integrity. This checks:
- Critical files exist (pyproject.toml, uv.lock, workspace.yaml, etc.)
- Critical directories exist (substrate/, scripts/, docs/, tests/, state/)
- Key scripts exist (substrate_cli.py, probe_system.py, etc.)
- Required tools are available (uv, python3, git)
- Python syntax is valid (compileall)
- Substrate scan succeeds

The CI pipeline runs this check automatically on every push/PR.

### Sandboxed Execution Policy

All system-modifying commands MUST be validated in a sandbox first:

1. **Python/uv work**: Use `uv` managed environments (automatic isolation)
2. **System packages**: Test in `podman run --rm archlinux` first
3. **File restoration**: Review via `git show HEAD:<path>` before checkout
4. **Config changes**: Diff review before application
5. **Destructive operations**: Always require explicit user approval

Promotion criteria:
- Command succeeds in sandbox with expected output
- No unintended side effects observed
- Rollback plan documented

### Infrastructure Health Check

Run `bash scripts/health_check.sh` to validate substrate infrastructure integrity. This checks:
- Critical files exist (pyproject.toml, uv.lock, workspace.yaml, etc.)
- Critical directories exist (substrate/, scripts/, docs/, tests/, state/)
- Key scripts are present
- Required tools are available (uv, python3, git)
- Python syntax is valid (compileall)
- Substrate scan succeeds

The CI pipeline automatically runs this check on every push/PR.