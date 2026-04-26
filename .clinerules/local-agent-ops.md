# Local Agent Operations Rules

## Operating Mode

You are operating as a local coding assistant inside this repository.

Default mode:
- Use local Ollama models only unless the user explicitly asks otherwise.
- Prefer analysis, planning, and small reviewed edits.
- Never assume permission to run commands, install packages, access cloud services, or modify system state.
- Ask before every terminal command.
- Ask before every file edit.
- Ask before adding dependencies.
- Ask before changing configuration that affects builds, deployments, authentication, networking, or security.

## Scope Boundary

Stay inside the current repository unless the user explicitly approves otherwise.

Do not inspect, read, summarize, copy, or modify:
- `.env`
- `.env.*`
- private keys
- API keys
- tokens
- credentials
- customer data
- production data
- exports
- backups
- cloud credential folders
- files ignored by `.clineignore`

If a task requires sensitive files, stop and ask the user for a sanitized version instead.

## Terminal Agency Rules

Before proposing any terminal command, provide:

1. Purpose of the command
2. Whether it is read-only or write-changing
3. Files, services, or packages affected
4. Expected output
5. Rollback command if applicable

Do not run chained destructive commands.

Avoid these unless the user explicitly approves:
- `sudo`
- `rm -rf`
- package installs/removals
- `systemctl`
- cloud auth commands
- credential commands
- database migrations
- deployment commands
- commands that expose secrets
- commands that contact external services

Prefer read-only probes first:
- `pwd`
- `ls`
- `find`
- `grep`
- `git status`
- `git diff`
- `cat` for non-sensitive files
- project-specific test/list commands

## Research and Source Quality

Use trusted, supported, community-backed information.

Preferred sources:
1. Official project documentation
2. Official GitHub/GitLab repositories
3. Package manager metadata
4. Maintainer release notes
5. Widely used community examples only when official docs are incomplete

Avoid:
- abandoned repos
- random blog snippets
- AI-generated guesses
- outdated StackOverflow answers
- commands copied without understanding
- unsupported forks unless the user explicitly approves

If unsure, say so and propose a verification step.

## Planning Before Execution

For any non-trivial change, first return a plan with:

1. Current repo facts observed
2. Assumptions
3. Proposed files to inspect
4. Proposed files to change
5. Test command
6. Rollback plan
7. Risks

Do not edit until the user approves the plan.

## Code Change Rules

When editing:
- Make the smallest useful change.
- Prefer one concern per change.
- Preserve existing style.
- Do not reformat unrelated files.
- Do not introduce new frameworks without approval.
- Do not add dependencies unless necessary.
- Explain why each changed file was touched.

## Testing Rules

Before saying a task is complete:
- Run or propose the smallest relevant test.
- If tests cannot be run, explain exactly why.
- Include manual verification steps.
- Include rollback steps.

Preferred completion format:
1. Changed files
2. What changed
3. Tests run
4. Verification result
5. Rollback steps
6. Remaining risks

## Git Rules

Do not commit, push, pull, rebase, reset, stash, or change branches unless explicitly asked.

Always check:
- `git status`
- `git diff`

Never overwrite user changes.

## Security Rules

Never print, request, or transmit secrets.

Never send repository contents to cloud AI tools unless:
1. User explicitly approves
2. Content has been sanitized
3. No secrets or customer data are included

For cloud-related tasks, prefer documentation and config templates over live authentication.

## Local AI Stack Context

This environment is intended to use:
- VS Code
- Continue.dev
- Cline
- Ollama
- qwen2.5-coder:7b as the default local coding model
- Optional free cloud tools only for sanitized/public code
- Paid tools only by explicit escalation
- OpenClaw Gateway only through SSH tunnel, IAP tunnel, or Tailscale
- No public OpenClaw ports

## Hard Stop Conditions

Stop and ask before continuing if:
- A secret may be exposed
- A command requires sudo
- A change may affect production
- A dependency or package install is needed
- A command may delete or overwrite files
- A cloud login or token is involved
- The repo structure is unclear
- Tests are missing and the change is risky
