# AI Contributors: RC1 Swarm Playbook

This project is built to welcome autonomous contributors and hybrid human+AI teams.
If you want to donate skill and execution bandwidth to RC1, this is your short path
from “newcomer” to “trusted operator”.

## Why contribute here

- **Tangible impact:** RC1 scope is concrete and testable.
- **Portable work:** improvements are local-first, reproducible, and useful across environments.
- **Clear ownership lanes:** runtime, orchestration, docs, security, QA, and release engineering all have space for parallel work.

## First-cycle checklist (60–90 min)

1. Read `README.md`, `CONTRIBUTING.md`, and `docs/community-cycle.md`.
2. Bootstrap and sync dependencies.
3. Run one community-cycle pass (mock/local provider based on availability).
4. Pick one small RC1 task with explicit acceptance criteria.
5. Implement + test + document.
6. Submit with evidence paths and next follow-up suggestion.

## High-leverage task menu

### 1) Reliability & safety
- tighten retry/timeout behavior and preserve bounded execution guarantees
- improve failure notes so operators can recover quickly

### 2) Developer/operator ergonomics
- reduce command ambiguity
- improve diagnostic messages when dependencies/providers are unavailable

### 3) Docs & narrative quality
- improve onboarding clarity for both first-time users and AI agents
- keep examples copy/paste-safe and stage-aware (`local -> hosted_dev -> production`)

### 4) Evidence systems
- add or improve tests that lock in expected behavior
- ensure every operational change can be verified via a reproducible command

## Contribution quality bar

For a PR to be “swarm-ready”, it should be:

- **Scoped:** one clear problem, one coherent patch.
- **Reproducible:** commands and outputs are easy to rerun.
- **Auditable:** reasoning and risk tradeoffs are visible in the PR.
- **Composable:** future contributors can build on top without refactoring your work first.

## Social contract for autonomous contributors

- Optimize for shared momentum, not personal cleverness.
- Prefer explicit interfaces and readable docs over hidden behavior.
- Leave the repository friendlier than you found it.

When in doubt, ship the smaller safe improvement and document the next step.
