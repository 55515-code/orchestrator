# HIPAA Security Risk Assessment Template

**Version:** 1.0 · **Category:** Compliance · **Audience:** Small practices, MSPs, health-tech startups

The HIPAA Security Rule (45 CFR §164.308(a)(1)) requires a documented risk
analysis. This template produces an artifact an OCR investigator or auditor
can follow: asset inventory → threat mapping → scoring → mitigation plan.

## 1. Scope Definition

- [ ] Covered entity or business associate? Document the role.
- [ ] List every system that creates, receives, maintains, or transmits ePHI:
      EHR, billing, imaging, email, backup, portals, mobile devices.
- [ ] List every business associate with ePHI access; confirm BAAs are signed
      and current.
- [ ] Note data flows: where ePHI enters, moves, and exits the organization.

## 2. Asset Inventory

| Asset | Type | ePHI? | Owner | Location | Criticality (1-5) |
|---|---|---|---|---|---|
| EHR system | Application | Yes | | Cloud/On-prem | |
| Workstations | Hardware | Yes | | | |
| Email system | Application | Maybe | | | |
| Backup storage | Storage | Yes | | | |
| Mobile devices | Hardware | Maybe | | | |

## 3. Threat and Vulnerability Mapping

For each asset with ePHI, consider:

| Threat | Likelihood (1-5) | Impact (1-5) | Risk Score | Current Safeguard |
|---|---|---|---|---|
| Ransomware on workstation | | | | |
| Lost/stolen device with ePHI | | | | |
| Unauthorized remote access | | | | |
| Insider snooping on records | | | | |
| Vendor breach (BA) | | | | |
| Email misdelivery of ePHI | | | | |
| Backup corruption/failure | | | | |
| Unpatched internet-facing system | | | | |

## 4. Safeguard Gap Analysis

Map findings to the Security Rule categories:

### Administrative (required)
- [ ] Security management process (risk analysis itself, sanctions, response)
- [ ] Assigned Security Official
- [ ] Workforce security: authorization and termination procedures
- [ ] Information access management: minimum necessary
- [ ] Security awareness training (annual, documented attendance)
- [ ] Incident response procedure with documented tests/tabletops
- [ ] Contingency plan: backup, disaster recovery, emergency mode operations
- [ ] Business associate agreements current and complete

### Technical (addressable — document decisions)
- [ ] Unique user identification; no shared logins
- [ ] Emergency access procedure
- [ ] Automatic logoff / session timeout
- [ ] Encryption at rest and in transit (or documented equivalent measure)
- [ ] Audit controls: logs of ePHI access, retained and reviewed
- [ ] Integrity controls: protection from improper alteration/destruction
- [ ] Authentication for network access
- [ ] Transmission security for ePHI in motion

### Physical
- [ ] Facility access controls
- [ ] Workstation use and security policies
- [ ] Device and media controls: disposal, reuse, transfer logs

## 5. Risk Scoring and Prioritization

Score = Likelihood × Impact. Treat:
- **15–25:** mitigate immediately with owner and deadline
- **8–14:** mitigate within the year; document interim safeguards
- **1–7:** accept with documented rationale, review annually

## 6. Remediation Plan

| Risk | Mitigation | Owner | Due Date | Budget | Status |
|---|---|---|---|---|---|
| | | | | | |

## 7. Documentation Requirements

- [ ] Risk analysis signed and dated by the Security Official
- [ ] Retain for 6 years minimum
- [ ] Re-perform annually and after significant changes (new EHR, merger,
      breach, new telehealth tool)
- [ ] Keep prior versions: OCR expects to see a history of the program

## Common OCR Findings in Small Practices

1. No written risk analysis at all (most cited deficiency).
2. Risk analysis exists but doesn't cover all ePHI systems.
3. No documentation for addressable safeguards ("we decided not to encrypt"
   without the required rationale).
4. Training not tracked.
5. Missing/expired BAAs with billing services and IT vendors.

---
*Educational material, not legal advice. Engage counsel or a HIPAA specialist
for organizational determinations.*
