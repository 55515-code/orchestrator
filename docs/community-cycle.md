# Community Cycle

The `community-cycle` command runs a full weekly open-source community cycle using
independent persona agents. Each actor is executed as an individual agent session
rather than a queue-only aggregate.

Population per cycle:

- 100 developer agents
- 300 user/tester agents

Each actor gets:

- unique `actor_id`
- persona profile
- independent prompt/input
- independent output artifact

Execution model:

- agents run in waves when `--concurrency-limit` is lower than 400
- cohort counts remain exact across the complete cycle
- full cycle artifacts are written to `memory/community-sim/<timestamp>-cycleNN-<id>/`

## Run Cycle 0

```bash
uv run python scripts/substrate_cli.py community-cycle \
  --cycle 0 \
  --repo substrate-core \
  --stage local \
  --concurrency-limit 40 \
  --agent-provider mock
```

Use a real provider/model when credentials/runtime are configured:

```bash
uv run python scripts/substrate_cli.py community-cycle \
  --cycle 0 \
  --repo substrate-core \
  --stage local \
  --concurrency-limit 20 \
  --agent-provider openai \
  --agent-model gpt-4.1-mini
```

## Generated Artifacts

Each cycle emits all required artifacts:

- mission and scope alignment report (`mission_scope_alignment.md`)
- prioritized backlog (`prioritized_backlog.json`)
- accepted/rejected RFC log (`accepted_rejected_rfc_log.json`)
- PR throughput and review latency (`pr_throughput_review_latency_report.json`)
- test matrix and failure taxonomy (`test_matrix_failure_taxonomy.json`)
- regression index and known-good updates (`regression_index_known_good_updates.json`)
- release readiness scorecard (`release_readiness_scorecard.json`)
- risk register (`risk_register.json`)
- community health report (`community_health_report.json`)
- cycle output report in required format (`cycle_report.md`)

Independent session records:

- full roster queues (`developers_queue.json`, `users_testers_queue.json`)
- wave plan (`wave_schedule.json`)
- per-actor session files (`actor_sessions/<actor_id>.json`)
- combined session stream (`actor_sessions.jsonl`)
