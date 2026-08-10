# Job contract — ARIN creative generation

Per `SUBSTRATE_EVOLUTION.md` § "Contract model". This is the machine- and
human-readable contract that any `creative-agent` run (scheduled or
on-demand) must satisfy.

- **objective:** advance the ARIN novel through the phases defined in
  `planning/NOVEL_PRODUCTION_PLAN.md`, and keep the reusable creative
  substrate (`memory/`, `canon/`, `voice/`, `planning/`, `generation/`,
  `critique/`, `assets/`, `publishing/`, `economy/`, `promotion/`,
  `telemetry/`, `state/`) healthy.
- **inputs / immutable canon:** `canon/ARIN_CANON.md`,
  `voice/VOICE_STYLE_ENGINE.md`, `assets/ARIN_final_poster.png` (+
  provenance). These are not to be rewritten by an automated run; only
  appended-to via a recorded decision.
- **allowed tools (scheduled/automatic run, tier 1):** filesystem read/write
  under `creative/ARIN/`, `state/`, `.research/creative-arin/`; no network
  calls; no paid model invocation unless a `--directive` explicitly requests
  drafting AND a cost ceiling below is set.
- **write boundaries:** `creative/ARIN/**` and
  `.research/creative-arin/**` only. Never `assets/ARIN_final_poster.png`.
- **budget ceiling (scheduled run):** $0.00 — bounded internal work only
  (no billed model calls). A human directive that requests drafting must
  state its own ceiling; the agent refuses to invoke a paid provider without
  one.
- **expected artifacts:** updated `PROJECT_STATE.md` phase table, a dated
  rationale note under `.research/creative-arin/`, an updated
  `state/arin-production.json` telemetry/ledger snapshot.
- **validators:** quality-gate self-check (`critique/QUALITY_GATES.md`
  "Autonomy" and "Production" sections — cost ceilings enforced, state
  resumable, no secrets, agent changes documented).
- **rollback/checkpoint:** every write is additive/idempotent per cadence
  window (see `state/agent-idempotency/`); nothing here deletes prior
  manuscript content.
- **human-approval gates (hard-coded in `substrate/agents/creative.py`,
  independent of `agents.yaml` tier):** spending, accepting platform terms,
  payout/tax identity setup, public publishing, outbound promotion/ads,
  ownership/licensing changes, deleting irreplaceable material, exposing
  credentials.
- **success metrics:** phase table advances only on validator pass; no
  validator failure is silently ignored; every run leaves a rationale note.
