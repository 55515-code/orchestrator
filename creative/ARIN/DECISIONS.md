# ARIN — Decision Log

## 2026-08-09 — Package ingestion and substrate integration

- **Decision:** Accept `ARIN_Kilo_Autonomous_Novel_Package.zip` as a source
  package and integrate it as a new creative project under `creative/ARIN/`,
  governed by a new `creative-agent` role in the existing agent roster
  rather than a bespoke standalone script.
- **Rationale:** The package contains only Markdown/JSON/PNG (no executable
  code); its own manifest already declares
  `external_side_effect_policy: human_approval_required`, matching this
  substrate's Tier 2 human-approval model. Reusing the existing
  `agents.yaml` / `substrate/agents/` scheduling machinery avoids building a
  parallel automation path and keeps idempotency, learning records, and
  bounded validation consistent with every other agent.
- **Decision:** The scheduled cadence performs only bounded, reversible
  internal work (module scaffolding, canon/voice presence checks, quality
  gate self-checks, telemetry/cost-ledger snapshots). It does **not**
  auto-invoke a model to draft chapters, because that would spend API budget
  unattended without an explicit ceiling set by a human. Drafting is
  triggered on demand with `agent-run --role creative-agent --repo
  substrate-core --directive "<phase/chapter instruction>"`.
- **Decision:** Autonomy tier set to 1 (automatic only when validation is
  green), matching `update-agent`/`resource-generator`. Publishing, spending,
  and outbound promotion remain hard-coded Tier 2 checks inside
  `substrate/agents/creative.py`, independent of the tier declared in
  `agents.yaml`, so a misconfiguration of the YAML cannot silently unlock
  those actions.
