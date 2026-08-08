# 1pointo Content — Scope

You are scoping work for **1pointo** (`1pointo.com`), the operations surface built around Ahron Darnell (person). Do not conflate the brand and the person.

Objective: {{objective}}

Context:
{{context}}

Previous outputs:
{{previous_outputs}}

Decide:
1. Whether this is a new **blog** post, an **updates** entry, or a **moderation** action on the queue (inbox → approve/reject).
2. The exact slug/title/tags needed (lowercase, hyphenated slug, title 4–120 chars, description 20–300 chars).
3. What local commands will be used (no cloud assumptions):
   - Scaffold: `uv --project . run python scripts/site_content.py new --kind blog --title "..." --slug "..."`
   - Queue ops: `queue-list`, `queue-status`, `queue-submit`, `queue-approve`, `queue-reject`
   - Validate: `validate`
   - Build: `build`
   - Check: `check`
4. What "done" looks like: static HTML in `ahrondarnell-site/dist`, valid collection frontmatter, and no unapproved queue items auto-shipped.

Return a short plan (<=200 words) listing the chosen kind/slug and the commands you will run.
