# Promotion + Deployment Runbook (People + Bots)

## Current status snapshot (as of 2026-04-10 UTC)

- Latest autonomous run: `20260410-054706-cycle03-d82bb3fa`.
- Stage executed: `local`.
- Population completed: 400 independent sessions (100 developer personas + 300 user/tester personas).
- Release readiness: **35.7%** (`passed=1`, `partial=3`, `failed=3`).
- Biggest blockers: backup/sync regression, integration boundary clarity, review SLA backlog, flaky-test policy.

Source artifacts:

- `memory/community-sim/20260410-054706-cycle03-d82bb3fa/cycle_report.md`
- `README_STATUS.md`
- `docs/community_status.html`

---

## Promotion strategy

### 1) Promotion to people (maintainers and contributors)

Use a staged communication cadence after each cycle:

1. **Core maintainers (same day):**
   - Share top 3 risks and explicit owners from the cycle report.
   - Require owner acknowledgement for each critical/high issue.
2. **Module owners (within 24h):**
   - Convert risk items into issue tickets with acceptance criteria.
   - Attach proof commands and artifact paths for reproducibility.
3. **Contributors/community (within 48h):**
   - Publish a concise status update from `README_STATUS.md`.
   - Tag "good first issue" and "help wanted" tasks from non-critical backlog.

### 2) Promotion to bots (autonomous agents)

Use the orchestrator's wave model to parallelize with controls:

1. Run cycle in `local` first.
2. Assign bots by squad ownership from risk register.
3. Require each bot PR to include:
   - risk/issue ID addressed,
   - reproducible validation command,
   - artifact path(s),
   - next-step handoff.
4. Promote to `hosted_dev` only when `local:testing=pass` and critical risk count is zero.

---

## Tactical plan for the next 7 days

1. **Fix backup/sync normalization regression** (critical).
2. **Publish supported/unsupported integrations matrix** (high).
3. **Implement deterministic flaky-test retry policy** (high).
4. **Clear review backlog for security-sensitive PRs** (high).
5. **Patch onboarding recovery docs** (medium).

Success gates:

- No critical issues open.
- Flaky tests `<=2` for 3 consecutive runs.
- Hosted-dev test pass before any production promotion.

---

## Deployment strategy

### Phase A: Local validation

```bash
uv run python scripts/substrate_cli.py scan
uv run python scripts/substrate_cli.py community-cycle --cycle 4 --repo substrate-core --stage local --concurrency-limit 40 --agent-provider mock
```

### Phase B: Hosted dev promotion (dry run first)

```bash
uv run python scripts/substrate_cli.py run-chain --repo substrate-core --objective "Hosted validation run" --stage hosted_dev --dry-run
```

### Phase C: Controlled production promotion

Promote only when Phase B has clean evidence:

- release readiness score >= 90%,
- no critical/high unresolved security or reliability blockers,
- deterministic CI pass window achieved.

Operational profiles:

- local-only serve: `uv run python scripts/substrate_cli.py serve --host 127.0.0.1 --port 8090`
- containerized: `bash scripts/run_local_container.sh up`

---

## Operator checklist

- [ ] Run cycle and regenerate status pages.
- [ ] Publish people-facing summary and owner actions.
- [ ] Dispatch bot work packets by squad.
- [ ] Validate stage gates (`local` -> `hosted_dev` -> `production`).
- [ ] Record evidence paths in PRs and status docs.
