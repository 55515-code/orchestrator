# Optimization Cycle — 2026-08-08

Evidence-based optimization pass over the Local Agent Substrate stack. This cycle
reviewed existing research outputs, measured current performance, selected the
highest-impact opportunities, and implemented them with pre-defined success metrics.

## 1. Evidence Review

### Measured metrics (pre-optimization)

| Metric | Value | Source |
|--------|-------|--------|
| Test suite | 311 passed, 2 skipped | `pytest -q tests/` × 3 runs, zero flakiness |
| Lint errors | 38 (30 E402, 6 F841, 2 E741) | `ruff check substrate scripts` |
| Agent success rate | 13/13 agents green on last run | `state/agent-state.json` |
| Update-agent validation | 1 intermittent failure (`pytest: unrecognized arguments: - -`) preceded by `VIRTUAL_ENV` mismatch warning | `.research/substrate-core/2026-08-08-update-failure.md` |
| Build-cache files tracked in git | 3 `.wrangler/cache/*.json` + 1 `control_panel.db` | `git ls-files` |
| Agent worktree disk usage | 688M across 5 worktrees | `du -sh state/agent-worktrees` |
| Auto-sync commits / 24h | 21 (carrying substantive agent work — `state/`, `memory/`, `.research/` already gitignored) | `git log` |

### Simulated evidence (treated with caution)

The community-simulation release scorecard reports 35.7% readiness with claims like
"78 flaky tests". Direct measurement (3 consecutive full-suite runs) shows **zero**
flakiness, contradicting the simulated claim. Simulated evidence is retained as a
directional signal only; this cycle optimizes from measured data.

## 2. Selected Optimizations

Selected on impact × evidence-quality × feasibility:

### OPT-1 — Eliminate lint debt (stability/hygiene)

- **Evidence**: 38 ruff errors, including dead assignments and ambiguous names.
- **Plan**: Fix 2 E741 (rename `l` → `listener`/`entry` in `daily_security_report.py`),
  remove 6 F841 dead assignments (verified each variable unused in scope and each
  right-hand side side-effect-free before removal), reorder `web.py` imports to fix 19
  E402 (moved `logger` and `contextlib` import to their canonical positions), and add
  `[tool.ruff.lint.per-file-ignores]` for the 11 scripts whose `sys.path` bootstrap
  legitimately precedes imports.
- **Success metric**: 0 ruff errors; test suite unchanged at 311 passed.
- **Risk mitigation**: Every F841 removal verified by scope analysis first; full test
  suite run after each batch; `web.py` import verified via `import substrate.web`.
- **Cost**: Low (no behavior change intended). **Feasibility**: High.

### OPT-2 — Stop tracking build caches (friction reduction)

- **Evidence**: `workers/*/.wrangler/cache/*.json` and `deploy-system/control_panel.db`
  committed into history; machine-specific caches pollute diffs and auto-sync commits.
- **Plan**: `git rm --cached` the 4 files; add `.wrangler/` and `node_modules/` to
  `.gitignore` (`*.db` already present).
- **Success metric**: `git ls-files | grep -E '\.wrangler|control_panel'` → empty;
  `git check-ignore` confirms both paths ignored.
- **Risk mitigation**: `--cached` keeps files on disk; wrangler regenerates its cache.
- **Cost**: Trivial. **Feasibility**: High.

### OPT-3 — Harden bounded validation against env leakage (reliability)

- **Evidence**: Update-agent failure `pytest: unrecognized arguments: - -` immediately
  preceded by `warning: VIRTUAL_ENV ... does not match the project environment path`
  — the agent inherits the parent `VIRTUAL_ENV` when validating inside a worktree that
  has its own `.venv`.
- **Plan**: In `substrate/agents/core.py::run_command_bounded`, when no explicit `env`
  is supplied, inherit `os.environ` minus `VIRTUAL_ENV` so `uv` resolves the worktree's
  own environment cleanly. Also attach `command` and `workdir` to failure results so any
  future recurrence is diagnosable from the run ledger alone.
- **Success metric**: Bounded child processes observe no `VIRTUAL_ENV`; next
  update-agent cycle validates green with zero VIRTUAL_ENV warnings.
- **Risk mitigation**: `uv run` manages its own environment, so stripping `VIRTUAL_ENV`
  only removes the mismatch; verified via a live probe asserting the child environment
  is clean. Explicit `env=` callers are unaffected.
- **Cost**: Low. **Feasibility**: High (verified live).

### OPT-4 — Worktree disk visibility (operational calm)

- **Evidence**: 688M in `state/agent-worktrees` with no visibility in health checks.
- **Plan**: `scripts/health_check.sh` now reports worktree count + size and warns above
  1GB, making growth observable before it becomes a problem. (Worktrees from in-flight
  agent runs are intentionally retained; stale >30-day cleanup already runs per cycle.)
- **Success metric**: Health check surfaces usage; warning triggers only above 1GB.
- **Risk mitigation**: Read-only check; no deletion behavior added.
- **Cost**: Trivial. **Feasibility**: High.

## 3. Implementation Results

| Metric | Before | After | Target | Status |
|--------|--------|-------|--------|--------|
| Ruff errors | 38 | **0** | 0 | ✅ |
| Test suite | 311 passed, 2 skipped | **311 passed, 2 skipped** | no regression | ✅ |
| Tracked build-cache files | 4 | **0** | 0 | ✅ |
| VIRTUAL_ENV visible to bounded child | yes | **no** (probe-verified) | no | ✅ |
| Worktree disk visibility in health check | none | **reported + 1GB warning** | present | ✅ |
| `health_check.sh` | pass | **pass** | pass | ✅ |

Files changed: `substrate/web.py`, `substrate/cli.py`, `substrate/render.py`,
`substrate/agents/core.py`, `scripts/daily_security_report.py`,
`scripts/remaster_pipeline.py`, `scripts/health_check.sh`, `pyproject.toml`,
`.gitignore`, plus untracked cache/db files.

## 4. Post-Implementation Monitoring

1. **Lint regression guard**: `uv run --with ruff ruff check substrate scripts`
   — expected `All checks passed!`. Baseline recorded in the learning index as
   `optimization-cycle-2026-08-08-post-lint`.
2. **Update-agent stability**: watch `state/agent-state.json` → `update-substrate`
   over the next daily cycles; success metric is continued `validation_not_green: 0`
   and no `VIRTUAL_ENV` warnings in `.research/substrate-core/` reports. Any new
   failure now includes the exact `command` + `workdir` in the run record.
3. **Disk hygiene**: `bash scripts/health_check.sh` — the new Agent Worktree Disk
   Usage section warns above 1GB; track weekly.
4. **Commit hygiene**: confirm future auto-sync commits no longer contain
   `.wrangler/cache` entries (`git log -p -- workers | grep -c wrangler` → 0).
5. **Suite stability**: keep the 3-run flakiness probe as the standard when the
   community sim claims test instability — measured data overrides simulated claims.
