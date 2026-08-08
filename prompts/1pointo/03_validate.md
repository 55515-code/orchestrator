# 1pointo Content — Validate

Validate locally before any build or approval.

Objective: {{objective}}

Context:
{{context}}

Previous outputs:
{{previous_outputs}}

Run in order and report results:
1. `uv --project . run python scripts/site_content.py validate` — must pass with `failed: 0`.
2. If queue work is involved: `queue-status` — inbox items must be either valid (`ok: true`) or explicitly rejected; never approve a file with `errors`.
3. `uv --project . run python scripts/site_content.py build` — must produce `13+` pages in `dist` without error.
4. `npm run check` or `scripts/site_content.py check` if needed — note any type errors.

If validation fails, fix the markdown frontmatter or body (do not skip checks). Return the JSON summaries verbatim for the record.
