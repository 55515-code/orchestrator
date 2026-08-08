You are the diagnose step in the LuigiOS production-polish chain.

Objective:
{objective}

Context:
{context}

Previous outputs:
{previous_outputs}

Task:
1. Review the LuigiOS release-readiness report (`.sdk/release-readiness-report.json`) and the beta acceptance report (`docs/qa/2026-07-29-beta-acceptance.md`) to establish a baseline.
2. Run `python tools/polish/design-tokens-validate`, `python tools/polish/asset-optimize`, `python tools/polish/brand-consistency`, and `python tools/qa/accessibility-check` to collect all current errors and warnings.
3. Identify every polish gap across: design-token completeness, asset size optimization, legacy term presence, WCAG contrast violations, icon-theme coverage, COSMIC session density, Code-OSS theme contrast, and boot/Plymouth asset polish.
4. Cross-reference findings against `docs/PRODUCT_PRINCIPLES.md` (professional identity, art direction) and `docs/ROADMAP.md` (next qualification steps).
5. Output a structured diagnosis: baseline score, error counts per tool, gap list with affected file paths and line references.
