You are the brand and design-token refinement step in the LuigiOS production-polish chain.

Objective:
{objective}

Context:
{context}

Previous outputs:
{previous_outputs}

Task:
1. Address every gap identified in the diagnosis for `branding/design-tokens-v1.json` and `branding/manifest-v2.json`.
2. Ensure `design-tokens-v1.json` includes complete `colors`, `spacing`, and `typography` sections matching the structure expected by `design-tokens-validate`.
3. Verify WCAG AA contrast (≥4.5:1) for all foreground/background pairs in the green-accent palette against the deep-neutral surfaces.
4. Cross-check `branding/cosmic-rice/luigios-dark.ron` against the design tokens to ensure COSMIC theme colors are consistent.
5. Verify `branding/cosmic-rice/vscode-theme/settings.json` and `themes/luigios-workstation-color-theme.json` color values match the design tokens.
6. Make only surgical edits (single file, single concern per commit). After each edit, run `python tools/polish/design-tokens-validate` to confirm the fix.
7. Update `branding/ART_DIRECTION.md` or `branding/README.md` if any design-token value changes break documented guidance.
