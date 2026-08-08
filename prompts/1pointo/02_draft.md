# 1pointo Content — Draft

Draft or stage the content described in the objective. Use local file writes only.

Objective: {{objective}}

Plan from previous step:
{{previous_outputs}}

Rules:
- `1pointo` is the site/system brand; `Ahron Darnell` is the author/person. Use `BRAND` for site name in templates and `SITE`/`PERSON` for author identity — do not rename the domain or person to each other.
- For new posts: run `scripts/site_content.py new --kind <blog|updates> --title "..." --slug "..." --tags "..."` then edit the created markdown file to replace placeholder body with real content.
- For community submissions: use `queue-submit --source <path>` to land it in `ahrondarnell-site/.content-queue/inbox/` — never write directly to `src/content/`.
- Keep frontmatter valid: `title`, `description`, `pubDate` (YYYY-MM-DD), `author: "Ahron Darnell"`, `tags` (blog), `draft` (blog, default false for publish).
- Write answer-shaped, plain-English content (40–60 word BLUF opening) with short sections a crawler can extract.

Output the file path(s) you created or staged and the first 40 words of body.
