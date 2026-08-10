# ARIN — Backlog

## Now
- [ ] Human directive to begin Phase A (world bible, character bible,
      chronology, chapter graph) — run:
      `uv run python scripts/substrate_cli.py agent-run --role creative-agent --repo substrate-core --directive "phase-a: build world/character bible and chapter graph"`

## Next
- [ ] Phase B vertical slice (3 nonadjacent chapters) once Phase A artifacts
      exist and pass canon/voice self-review.
- [ ] Wire a real cost ceiling into `contracts/creative-generation-contract.md`
      before any Phase B/C generation run that uses a paid model provider.

## Later
- [ ] Phase C–F (full draft, structural/line revision, production build).
- [ ] Publishing/storefront staging (`publishing/`, `promotion/`) — remains
      Tier 2 for the actual publish/spend/send actions.

## Recurring (handled automatically by the `creative-arin` cadence)
- [ ] Module scaffolding presence check
- [ ] Canon/voice/quality-gate self-check against any drafted files
- [ ] Cost ledger and telemetry snapshot
- [ ] Stale/duplicate asset check
