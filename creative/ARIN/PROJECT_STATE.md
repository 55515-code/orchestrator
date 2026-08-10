# ARIN — Project State

_Last updated by: integration (manual, 2026-08-09). Subsequent updates are
written automatically by the `creative-agent` role on each scheduled run._

## Package ingestion

- Source: `ARIN_Kilo_Autonomous_Novel_Package.zip` (human-provided, inspected
  in a sandboxed extraction directory before integration — no executable
  code was present, only Markdown, JSON, and one PNG asset).
- Entrypoint directive: `00_source_package/00_START_HERE/KILO_MASTER_DIRECTIVE.md`.
- Canon, voice rules, novel pipeline, economy/release rules, and quality
  gates copied into their respective module directories (see
  `SUBSTRATE_EVOLUTION.md` for the module map).
- Poster preserved as canonical reference: `assets/ARIN_final_poster.png`
  (hash recorded in `assets/PROVENANCE.md`).

## Phase status (`04_novel_pipeline` / `planning/NOVEL_PRODUCTION_PLAN.md`)

| Phase | Description | Status |
|---|---|---|
| A | World/character bible, chronology, chapter graph | not started |
| B | 3-chapter vertical slice | not started |
| C | Full draft (scene packets → chapters) | not started |
| D | Structural revision | not started |
| E | Line revision | not started |
| F | Production (EPUB/print-ready build) | not started |

## Autonomy posture

- `autonomous_internal_work: true` (per package manifest) — bounded,
  reversible internal work (indexing, QA, telemetry, cost modeling, draft
  promo assets) runs automatically on the `creative-arin` cadence.
- `external_side_effect_policy: human_approval_required` — no spending,
  contract acceptance, publishing, or outbound promotion happens without an
  explicit human directive passed via `--directive`. See
  `contracts/creative-generation-contract.md` for the enforced boundary.
- Actual prose generation (Phase A–F) is **not** yet wired into the
  scheduled cadence — see `../../docs/arin-novel-automation.md` for why and
  how to enable it deliberately.

## Resume instructions for another agent

1. Read this file, `BACKLOG.md`, `DECISIONS.md`, and `CHANGELOG.md`.
2. Read `canon/ARIN_CANON.md` and `voice/VOICE_STYLE_ENGINE.md` before
   writing any prose — they are immutable inputs.
3. Check `state/arin-production.json` for machine-readable phase/telemetry
   state before resuming work.
4. Do not modify `assets/ARIN_final_poster.png` or its provenance record
   without a recorded decision.
