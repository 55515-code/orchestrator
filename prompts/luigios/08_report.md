You are the final report step in the LuigiOS production-polish chain.

Objective:
{objective}

Context:
{context}

Previous outputs:
{previous_outputs}

Task:
1. Aggregate the validation pass/fail matrix from the previous step.
2. Update `docs/AUTOMATION.md` with any new checks performed or new findings documented.
3. Update `LuigiOS/CHANGELOG.md` with a summary of all changes made during this chain run, grouped by area (brand, desktop, assets, legacy cleanup).
4. Update `.sdk/release-readiness-report.json` if the score improved.
5. Generate a summary artifact at `LuigiOS/.sdk/polish-findings/` with:
   - Baseline score (from diagnose step)
   - Final score (from validate step)
   - List of all files modified
   - List of all test results (pass/fail per check)
   - Remaining gaps for the next iteration
6. Output a concise markdown summary of the iteration results.
7. Record the chain run in the substrate learning index via `substrate record-test`.
