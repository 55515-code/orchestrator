# AI Collaboration Protocol

This repository is intentionally bot-friendly and human-friendly. This document is
the durable protocol for coordinated autonomous contribution.

## Mission
- Accelerate safe, test-backed development through hybrid automation.
- Keep collaboration transparent through reproducible artifacts and draft PRs.
- Encourage open-source contributors (human and AI) to pick up scoped tasks.
- Prioritize an education-first AI security toolkit built from orchestrator core + Studio UX.

## Operating Model
- PR events run deterministic CI checks.
- Scheduled/manual deep cycles attempt cloud-agent execution first.
- If cloud routing is unavailable, automation falls back to local/mock analysis and
  still publishes artifacts.
- Autonomous writes are limited to branch push + **draft PR** creation.

## Security + Education Scope
- Authorized security testing and lab validation only.
- No guidance for unauthorized access, persistence, or covert abuse.
- Every automation run should generate transparent evidence and explanatory artifacts.
- Prefer teachable outputs: what was run, why it matters, risk level, and remediation path.
- Treat this project as a collaborative "AI Swiss army knife" for defensive security operations.

## Required Artifacts
- `artifacts/agent-hybrid/agent_summary.json`
- `artifacts/agent-hybrid/agent_report.md`

## Source Of Direction
- Strategic product direction: `docs/security-toolkit-roadmap.md`
- Agent contract: `prompts/cloud_agent_hybrid_operator.md`

## Collaboration Labels
- `ai-ready`: issue is well-scoped for autonomous contribution.
- `help-wanted`: maintainers are explicitly asking for help.
- `good-first-task`: low-risk onboarding tasks.
- `needs-repro`: issue requires reproducible steps and evidence.
- `research-needed`: exploratory architecture or standards work required.

## Queue Format
Use this queue format in the pinned tracking issue and PR updates:

```text
- [priority] [owner] Task title
  - Acceptance criteria: ...
  - Evidence path(s): ...
  - Suggested labels: ai-ready, help-wanted
```

## Draft PR Policy
- Never merge directly to `main` from autonomous workflows.
- Every autonomous write flow must end in a draft PR.
- Include in PR body:
  - change summary
  - test evidence
  - risk register
  - next collaboration tasks
