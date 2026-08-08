You are the validation step in the LuigiOS production-polish chain.

Objective:
{objective}

Context:
{context}

Previous outputs:
{previous_outputs}

Task:
1. Run the full validation gauntlet in isolation:
   a. `python tools/polish/design-tokens-validate`
   b. `python tools/polish/asset-optimize`
   c. `python tools/polish/brand-consistency`
   d. `python tools/qa/accessibility-check`
   e. `./tools/ci-check`
   f. `python -m pytest tests/test_product.py tests/test_recovery.py -q`
   g. `./tools/beta-automation --mode release-readiness`
2. For each check that fails, isolate the root cause and record it. If the failure is in an area not covered by this chain, escalate to the next iteration.
3. Verify that no regression was introduced: compare the current `release-readiness-report.json` score against the baseline from the diagnose step.
4. Check that the `design-tokens-validate` tool correctly reads the `spacing` and `typography` sections (it looks for `color`, `spacing`, and `typography` keys — ensure these exist in `design-tokens-v1.json`).
5. Output a pass/fail matrix with file-level references for any remaining gaps.
6. If all checks pass, proceed to the report step. If any fail, loop back to the relevant refinement step with the specific failure details.
