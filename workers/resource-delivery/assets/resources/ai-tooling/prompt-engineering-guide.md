# Prompt Engineering Guide for Compliance & Security Automation

**Version:** 1.0 · **Category:** AI Tooling · **Audience:** Teams automating compliance/security documentation

Practical prompt patterns for generating reliable, audit-friendly compliance
and security documents. Focuses on structure, grounding, and validation rather
than cleverness.

## 1. Core Principles

1. **Ground before generating.** Provide source facts (standards excerpts,
   current configs, prior audit findings) in the prompt. Ungrounded models
   hallucinate control names and regulatory citations.
2. **Separate facts from instructions.** Use clearly delimited sections so the
   model can distinguish provided evidence from the task.
3. **Require structure.** Ask for checklists, tables, and named sections.
   Structured output is easier to validate and reuse.
4. **Constrain scope.** State explicitly what NOT to do (no invented citations,
   no assumptions about unverified systems).
5. **Validate the output.** Every generated document passes a quality gate
   before a human or agent publishes it.

## 2. The R-T-S-C Pattern

A reliable prompt has four parts:

- **Role** — who the model should act as ("You are a SOC 2 implementation
  consultant...")
- **Task** — the specific deliverable ("...produce a readiness checklist...")
- **Source** — the grounding facts ("...based on the control list below...")
- **Constraints** — format and limits ("...as a Markdown checklist with
  phases; do not invent controls not in the source list")

## 3. Template: Compliance Checklist

```
Role: You are a <framework> implementation consultant for a small business.
Task: Produce a readiness checklist for <deliverable>.
Source facts:
<source>
{{ paste current controls, prior findings, system inventory }}
</source>
Constraints:
- Output Markdown with ## phase headings and - [ ] checklist items.
- Cite only controls present in the source facts.
- Add a "Common Failure Points" section.
- Do not invent regulatory citations.
```

## 4. Template: Security Policy

```
Role: You are a security policy writer for a <size> organization.
Task: Draft a <policy name> policy.
Source facts:
<source>
{{ tech stack, team size, regulatory drivers }}
</source>
Constraints:
- Sections: Purpose, Scope, Roles, Requirements, Enforcement, Review.
- Keep language testable (each requirement verifiable).
- Mark addressable/optional decisions explicitly.
```

## 5. Template: Risk Register Row Generation

```
Role: You are a risk analyst.
Task: Convert the following observations into risk register rows.
Source facts:
<source>
{{ raw observations }}
</source>
Constraints:
- Columns: Threat | Likelihood (1-5) | Impact (1-5) | Mitigation | Owner.
- Do not exceed the facts given; flag gaps as "NEEDS VERIFICATION".
```

## 6. Quality Gate Checklist (run before publishing)

- [ ] Every claim traces to provided source facts or is flagged
- [ ] No invented citations, statute numbers, or control IDs
- [ ] Output matches the requested structure (sections, tables, checklists)
- [ ] No banned/spam terms (guaranteed returns, free money, act now)
- [ ] Length and depth appropriate to the deliverable
- [ ] A human (Tier 2) approves before publication

## 7. Common Mistakes

1. **No grounding** → hallucinated controls. Always include source facts.
2. **Overly open tasks** → generic filler. Narrow the deliverable.
3. **Skipping validation** → publishing errors. Enforce the quality gate.
4. **Treating output as legal advice** → add disclaimers; route decisions to
   humans.
5. **Re-prompting blindly on failure** → instead, refine the source facts and
   constraints.

## 8. Integration with Agent Pipelines

Wire these templates into the resource-generation pipeline:
- The **research agent** (Tier 0) gathers source facts.
- The **generator** applies the appropriate template.
- The **quality gate** (Tier 1) validates structure and banned terms.
- The **moderator** holds anything suspicious.
- **Publishing** is Tier 2 and requires a human directive.

---
*Generated documents are drafts until validated and approved.*
