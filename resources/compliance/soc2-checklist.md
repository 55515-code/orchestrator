# SOC 2 Type II Readiness Checklist

**Version:** 1.0 · **Category:** Compliance · **Audience:** SaaS founders, CTOs, compliance leads

This checklist takes a service organization from "we should probably get SOC 2" to
"our auditor has everything they need." It follows the AICPA Trust Services
Criteria structure and reflects what actually gets asked in evidence requests.

## Phase 0 — Scoping (Week 1)

- [ ] Define the services in scope (which product(s), which customers)
- [ ] Identify the Trust Services Criteria: Security is mandatory; select
      Availability, Confidentiality, Processing Integrity, and/or Privacy only
      if customers contractually require them
- [ ] Define the system boundary: infrastructure, software, people, data,
      third parties
- [ ] Choose Type I (point-in-time) vs Type II (observation period, typically
      3–12 months) — Type II is what enterprise buyers usually want
- [ ] Select an auditor (CPA firm) and agree on the observation window

## Phase 1 — Risk Assessment (Weeks 1–2)

- [ ] Maintain a formal, documented risk assessment (at least annual)
- [ ] Identify threats to each criterion: unauthorized access, disclosure,
      loss of availability, improper processing
- [ ] Score risks (likelihood × impact) and assign owners
- [ ] Map mitigating controls to each significant risk
- [ ] Document residual risk acceptance with management sign-off

## Phase 2 — Control Design (Weeks 2–6)

### Access Control (CC6.x)
- [ ] SSO with MFA enforced for all employees and production access
- [ ] Role-based access; least privilege documented per role
- [ ] Quarterly access reviews with evidence (tickets/spreadshots)
- [ ] Immediate deprovisioning on termination (target: same day)
- [ ] Unique IDs everywhere; no shared credentials, including service
      accounts (use scoped tokens instead)

### Change Management (CC8.x)
- [ ] All production changes via pull request with at least one reviewer
- [ ] CI runs tests before merge; deployments from the main branch only
- [ ] Emergency change procedure with documented after-the-facto review
- [ ] Segregation of duties: developer ≠ deployer where team size allows,
      otherwise compensating controls documented

### Security Operations (CC7.x)
- [ ] Vulnerability scanning (infrastructure + dependencies) at least quarterly
- [ ] Penetration test at least annually, with remediation tracking
- [ ] Centralized logging with retention ≥ observation period
- [ ] Incident detection path: alert → triage → response → postmortem
- [ ] Vendor risk review: annual review of critical vendors (hosting, auth,
      backups) with SOC 2 reports or questionnaires on file

### HR Security (CC1.x)
- [ ] Background checks where lawful, before access is granted
- [ ] Security awareness training at hire and annually
- [ ] Signed confidentiality agreements
- [ ] Acceptable use policy acknowledged by all staff

### Data Protection
- [ ] Encryption in transit (TLS 1.2+) everywhere; at rest for customer data
- [ ] Backup schedule with documented restoration test at least annually
- [ ] Data classification (public/internal/confidential/restricted)
- [ ] Retention and disposal schedule

## Phase 3 — Evidence Collection (continuous during observation window)

- [ ] Every control has an evidence artifact: screenshot, ticket, log export,
      config file, or meeting note
- [ ] Evidence is timestamped and attributable
- [ ] Maintain an evidence index mapping control → artifact → owner
- [ ] Monthly internal self-check: sample 2–3 controls, verify evidence exists

## Phase 4 — Auditor Fieldwork

- [ ] Provide the system description draft to the auditor early (it is the
      largest writing task; start in Phase 1)
- [ ] Pre-clear samples: auditor selects evidence samples; gather them within
      48 hours
- [ ] Track exceptions honestly — one well-explained exception is better than
      a hidden pattern
- [ ] Management response letter for any exceptions

## Common Failure Points

1. **Access reviews skipped in one quarter** — auditors sample every period;
   one missed review becomes an exception.
2. **No evidence of restoration testing** — having backups is not the control;
   proving they restore is.
3. **Contractor access not reviewed** — contractors count as personnel.
4. **Change management bypasses for "small" changes** — if it touches
   production, it needs review evidence.

## Estimated Timeline and Cost

| Item | Typical range |
|---|---|
| Readiness (this checklist) | 4–8 weeks internal effort |
| Type II observation period | 3–12 months |
| Auditor fees | $15K–$40K for small organizations |
| Automation platforms (optional) | $10K–$30K/year |

---
*This document is educational material, not legal advice. Validate scope and
criteria selection with your auditor.*
