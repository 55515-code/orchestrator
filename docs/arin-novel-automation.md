# ARIN novel automation — integration summary

## What was integrated

`ARIN_Kilo_Autonomous_Novel_Package.zip` (human-provided, from
`~/Downloads/`) was extracted in an isolated inspection directory outside
the workspace and reviewed before any integration. It contained only
Markdown, one JSON manifest, and one PNG poster — no executable code,
scripts, or archives-within-archives. Its own manifest declares:

```json
{
  "external_side_effect_policy": "human_approval_required",
  "autonomous_internal_work": true
}
```

That policy is exactly this substrate's existing Tier 0/1/2 autonomy model,
so the package was integrated as a new **role** in the existing agent
roster rather than a bespoke standalone automation path.

## What changed

| File | Change |
|---|---|
| `creative/ARIN/` | New project directory: canon, voice, planning, economy, critique (quality gates), contracts, and placeholder `memory/generation/publishing/promotion/telemetry/state` modules per `SUBSTRATE_EVOLUTION.md`. Original package preserved verbatim under `creative/ARIN/00_source_package/`. Poster preserved at `creative/ARIN/assets/ARIN_final_poster.png` with a SHA-256 provenance record. `PROJECT_STATE.md`, `DECISIONS.md`, `BACKLOG.md`, `CHANGELOG.md` created per the package's "first execution" checklist. |
| `substrate/agents/creative.py` | New `creative-agent` role handler. |
| `substrate/agents/core.py` | Registered `"creative-agent"` in `AGENT_ROLES` and the `run_agent` handler dispatch table. |
| `agents.yaml` | New roster entry `creative-arin` (role `creative-agent`, repo `substrate-core`, pass `development`, cadence `daily`, autonomy tier `1`). |

No changes were made to `workspace.yaml`, `standards.yaml`, `tool_profiles.yaml`, `integrations.yaml`, or `upstreams.yaml` — this integration did not require new tasks, standards, tools, integrations, or upstream sources.

## Schedule / trigger conditions

The agent runs through the existing scheduler, not a new cron job:

- **Automatic:** the `substrate-agent-timer` systemd user timer (5-minute
  poll, `agent-cycle` evaluates cadence) will pick up `creative-arin` and
  run it once per day, same as `update-agent`/`resource-generator`. No
  extra installation step is needed if the timer is already installed
  (`scripts/install_agent_timer.sh`); otherwise install it once.
- **Manual/on-demand:**
  ```bash
  uv run python scripts/substrate_cli.py agent-run --role creative-agent --repo substrate-core
  uv run python scripts/substrate_cli.py agent-run --role creative-agent --repo substrate-core --force
  uv run python scripts/substrate_cli.py agent-status
  ```

## What the scheduled run actually does (bounded, zero-cost)

Every automatic run (no `--directive`) only:

1. Verifies the `creative/ARIN/` module scaffold exists.
2. Verifies canon/voice/quality-gate/contract files are present.
3. Verifies `assets/ARIN_final_poster.png` still hashes to the recorded
   provenance value (`3d110c5a85ef6884e1438096e2c1a700c4691a27c077f80a2759fb5e1b10c28b`).
4. Runs a deterministic quality-gate self-check (no model call).
5. Snapshots telemetry/ledger state to `state/arin-production.json`.
6. Writes a dated rationale note to `.research/creative-arin/`.

It never invokes a paid model, never writes prose, and never touches
`publishing/`, `promotion/`, or the canonical poster.

## What requires a human directive (Tier 2, hard-coded)

`substrate/agents/creative.py` classifies any `--directive` text and
independently enforces Tier 2 for keywords indicating: publish, spend, pay,
advertise, outbound promotion, signing/contracts, payout/tax identity
setup, ownership/licensing changes, canon deletion, or credential exposure —
**regardless of `autonomy_tier` in `agents.yaml`**. These require an
explicit human-run CLI invocation with `--directive`; the unattended
`agent-cycle` path never supplies one, so Tier 2 actions cannot fire from
the timer.

Actual novel drafting (Phases A–F in
`creative/ARIN/planning/NOVEL_PRODUCTION_PLAN.md`) is intentionally **not**
wired into the automatic cadence, because unattended drafting would invoke
a paid model without a human-set cost ceiling. Start it deliberately:

```bash
uv run python scripts/substrate_cli.py agent-run --role creative-agent --repo substrate-core \
  --directive "phase-a: build world/character bible and chapter graph"
```

Each such run records the directive and validates the substrate; it does
not itself call a paid provider. Wiring `generation/` to a real model
adapter, with an enforced budget ceiling from
`creative/ARIN/contracts/creative-generation-contract.md`, is the next
engineering step before Phase A/B can actually produce prose.

## Validation performed

- `uv run python -m compileall substrate scripts` — clean.
- `uv run python scripts/substrate_cli.py scan` — clean, `substrate-core`
  repo detected as before.
- `uv run python scripts/substrate_cli.py agent-status` — `creative-arin`
  listed, `due_now: true`, correct cadence/tier.
- `uv run python scripts/substrate_cli.py agent-run --role creative-agent --repo substrate-core --force` —
  `status: success`, wrote the expected rationale note and state snapshot.
- Directive classification tested manually: a "publish…" directive was
  correctly tagged tier 2 (and would be blocked with no directive at all,
  since the unattended cadence never passes one); a "phase-a: draft…"
  directive was correctly tagged tier 1 and did not invoke generation.
- `uv run --with pytest --with httpx pytest -q tests` — 341 passed, 2
  skipped. The only failures are in two **pre-existing, unrelated** test
  files from other uncommitted workspace work that predates this package
  (`tests/test_change_snapshot.py`, `tests/test_approvals.py`); neither is
  touched by the creative integration and both fail identically in
  isolation.
- Test coverage for the creative agent lives in
  `tests/test_creative_agent.py` (11 tests: scheduled maintenance,
  directive classification/Tier gating, scaffold/hash/quality-gate
  self-checks, state resume) and is runnable via
  `uv run --with pytest pytest -q tests/test_creative_agent.py`.
- Runtime state (`state/arin-production.json` and
  `.research/creative-arin/`) is regenerated automatically on every run —
  maintenance runs write them deterministically, so a missing/corrupt
  state file self-heals on the next scheduled or forced run.

## Dependencies

None new. The role uses only the standard library (`hashlib`, `pathlib`,
`datetime`) plus the substrate's existing `_utils`/`core` helpers — no new
Python packages, no new external services, and no model/API key is
required for the scheduled maintenance path.

## Ongoing maintenance notes

- **Do not** hand-edit `assets/ARIN_final_poster.png` or its provenance
  hash in `creative/ARIN/assets/PROVENANCE.md` without recording a decision
  in `creative/ARIN/DECISIONS.md` — the daily run will flag a mismatch as
  `status: attention`.
- If `agent-status`/`agent-run` reports `status: attention`, check the
  latest note under `.research/creative-arin/` for the specific missing
  file, hash mismatch, or quality-gate finding before proceeding.
- When ready to start real drafting, decide the model/provider and a real
  per-run cost ceiling first, record it in
  `creative/ARIN/contracts/creative-generation-contract.md`, then implement
  the actual generation call in `creative/ARIN/generation/` — do not simply
  raise the agent's autonomy tier, since the Tier 2 gates for
  publish/spend/promote are hard-coded in `substrate/agents/creative.py`
  independent of `agents.yaml`.
- Stale agent branches/worktrees cleanup already run by `agent-cycle`
  applies here too; this role does not create git branches or worktrees
  itself, so there is nothing extra to prune.
- The original package is preserved unmodified under
  `creative/ARIN/00_source_package/` for reference/audit; treat it as
  read-only.
- **Persistence:** the creative package (`creative/ARIN/`, the
  `creative-agent` role, the `agents.yaml` entry, and this document) was
  staged but **not yet committed** to git during the initial integration.
  Commit it so the automation survives worktree resets; `git log --
  creative/` currently shows no history. (Audit note — 2026-08-09.)
- **Operational state:** `state/arin-production.json` and
  `.research/creative-arin/` are written on every run and self-heal if
  missing; they are ignored by git (root `.gitignore` patterns
  `state/` / `memory/` / `*.png`) — do not force-add them to the repo, as
  they are runtime state, not source.
- **Scheduled delivery:** the automation depends on the
  `substrate-agent-timer` systemd user timer being enabled (installed by
  `scripts/install_agent_timer.sh`). `systemctl --user status
  substrate-agent-timer.timer` must show `active (waiting)`. The
  `creative-arin` agent is evaluated by `agent-cycle` on the daily cadence
  exactly like every other roster agent.
