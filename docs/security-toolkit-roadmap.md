# Security Toolkit Roadmap

This roadmap defines the intended direction for future development:
an AI-heavy, transparent, education-first security operations toolkit that uses the
orchestrator core and Scheduler Studio UX as the primary delivery surface.

## Product Vision
- Build a "Swiss army knife" for authorized security testing and defensive validation.
- Keep all workflows clear, reproducible, and community-shareable.
- Use AI to accelerate analysis and explanations, not to obscure action.

## Guardrails
- Authorized environments and legal scopes only.
- No stealth, persistence, or unauthorized targeting workflows.
- Every run must produce explainable outputs and evidence paths.
- Keep draft-PR-only automation for autonomous write flows.

## Core Development Themes
1. Core reliability for security jobs
- Harden scheduled and ad-hoc job execution.
- Improve stage-policy enforcement and checkpoint lineage.
- Standardize run artifact schema for security evidence.

2. UX for operator clarity and learning
- Job templates for common defensive workflows.
- Guided setup with safety checks and scope confirmation.
- Rich run views: findings, confidence, risks, and remediation suggestions.

3. Tooling integrations (defensive/open-source first)
- Add plugin-style adapters for maintained security tooling.
- Keep integration provenance, versions, and expected output contracts explicit.
- Normalize results so AI and humans can compare signals across tools.

4. AI collaboration and transparency
- Auto-generate educational reports from run artifacts.
- Maintain public collaboration queues with owners and acceptance criteria.
- Encourage external bots/humans through clear labels and issue templates.

## Backlog Seeds
- Template library: network validation, web surface checks, wireless lab checks.
- Result model: severity + confidence + reproducibility score.
- UX workflow: "Plan -> Validate Scope -> Run -> Explain -> Share."
- Artifact pack: machine JSON + human Markdown + replay command bundle.
- Community docs: contribution playbooks for security-focused squads.
