# Autonomous Creative Substrate Evolution

ARIN must improve the system that creates it.

## Preserve existing discipline
Use staged promotion:
model/tier selection → runtime compatibility → isolated boundary → ingest/quarantine → benchmark/security regression → review mode → limited writes/tools → canary → promotion.

Keep secrets isolated. Never print credentials into logs, prompts, manuscripts, commits, or artifacts.

## Build reusable modules when absent
- `memory/`: compact project-state summaries + retrieval index
- `canon/`: entities, dates, relationships, rules, unresolved questions
- `voice/`: style exemplars, forbidden habits, evaluators
- `planning/`: scene/chapter dependency graph
- `generation/`: model-agnostic generation adapters
- `critique/`: continuity, voice, pacing, repetition, factual plausibility
- `assets/`: canonical visual/media registry with hashes/provenance
- `publishing/`: EPUB/PDF/source build scripts and metadata
- `economy/`: cost ledger, pricing scenarios, revenue model
- `promotion/`: derivative asset queue and experiment specs
- `contracts/`: machine-readable job contracts for agents/tools
- `telemetry/`: token/runtime/cost/error/quality metrics
- `state/`: resumable checkpoints

## Contract model
Every autonomous job should declare:
- objective
- inputs and immutable canon
- allowed tools
- write boundaries
- budget ceiling
- expected artifacts
- validators
- rollback/checkpoint
- human-approval gates
- success metrics

Prefer deterministic transforms and cached intermediate artifacts where possible. Expensive generation should be invoked only when retrieval, reuse, or procedural transformation cannot meet quality.

## Background behavior
When idle or waiting on a human gate, agents may perform only bounded internal work:
- index/retrieve project knowledge
- run QA
- deduplicate assets
- improve documentation
- benchmark prompts/models
- prepare release candidates
- calculate cost/revenue scenarios
- generate *draft* promotional assets
They must not publish, spend, message audiences, or enter contracts autonomously.
