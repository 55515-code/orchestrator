# Local Agent Substrate

This repository provides a local-first substrate for AI-agent automation with:

- User-space bootstrap of core tooling
- Prompt-chain orchestration with LangGraph
- Repeatable system probing and documentation
- Multi-repo control plane with run ledger + web ops panel
- Weekly community-cycle orchestration with independent persona agents
- Stage-aware lifecycle (`local -> hosted_dev -> production`)
- Source evidence refresh before mutation-mode automation

Use `bash scripts/bootstrap-local-agent-env.sh` to install dependencies, then `python scripts/probe_system.py docs/system-probe.md` to generate a host profile.

## Contributor Guides

- `docs/ai-contributors.md` — RC1 swarm playbook for AI contributors, hackers, and hybrid teams.
- `docs/community-cycle.md` — weekly cycle workflow and generated artifacts.
- `CONTRIBUTING.md` — project-wide contribution rules and preferred checks.
