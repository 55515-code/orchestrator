# 1pointo Content — Review & Moderation Gate

No content ships without an explicit human approval step.

Objective: {{objective}}

Previous outputs:
{{previous_outputs}}

Actions:
- If this run created a draft (`draft: true`), leave it as a draft for human review — do NOT flip it to `draft: false` on your own.
- If this run staged community content in the inbox, report the `queue-list` and recommend `queue-approve --file <name> --kind blog --slug <slug>` or `queue-reject --file <name> --reason "..."`, but do NOT run approve/reject unless the objective explicitly says "approve" with a directive.
- Summarize: what is ready, what still needs human action, and the exact shell commands a human should run to publish (validate → approve → build → verify `dist`).

Return a concise review with: Ready / Needs human / Commands to publish.
