# Incident Response Plan Template (Small Business Edition)

**Version:** 1.0 · **Category:** Security · **Audience:** Teams of 2–50 without a dedicated security staff

A usable IR plan is short, role-based, and rehearsed. This template is sized
for small teams: it works when the "security team" is one person with an MSP
on call.

## 1. Scope and Activation

This plan activates on any confirmed or strongly suspected:
- Unauthorized access to systems or data
- Ransomware/malware affecting business systems
- Data breach involving customer, employee, or regulated data (PHI, PCI, PII)
- Business email compromise or financial fraud attempts
- Denial of service affecting customer-facing systems

**Any employee can raise an incident.** No blame for false alarms.

## 2. Roles (assign names, not just titles)

| Role | Person | Backup | Contact |
|---|---|---|---|
| Incident Commander (IC) | | | |
| Technical Lead | | | |
| Communications Lead | | | |
| Executive Sponsor | | | |
| External: MSP/security vendor | | | |
| External: counsel (if regulated data) | | | |
| External: cyber insurance hotline | | | |

The IC may hold multiple roles in a small team; document which.

## 3. Severity Classification

| Severity | Definition | Response time |
|---|---|---|
| SEV-1 | Active breach, ransomware spreading, regulated data exfiltration | Immediate; all hands |
| SEV-2 | Contained compromise, BEC attempt with funds at risk | Within 1 hour |
| SEV-3 | Suspicious activity, failed attempts, single infected endpoint | Within 4 hours |
| SEV-4 | Policy violation, minor anomaly | Next business day |

## 4. Response Workflow

### Detect → Triage (first 30 minutes)
- [ ] Record what was observed, by whom, when (timestamp everything)
- [ ] Classify severity; notify the IC
- [ ] Open an incident log (single document, append-only)

### Contain
- [ ] Isolate affected endpoints (network quarantine, do NOT power off if
      forensics may be needed)
- [ ] Disable compromised accounts; rotate exposed credentials
- [ ] Block attacker infrastructure at firewall/email gateway
- [ ] Preserve evidence: memory/disk images for SEV-1/2 before remediation

### Eradicate and Recover
- [ ] Identify root cause (phishing, vulnerability, credential theft)
- [ ] Remove persistence (scheduled tasks, registry keys, rogue accounts)
- [ ] Rebuild affected systems from known-good images
- [ ] Restore data from last clean backup; verify integrity
- [ ] Patch the exploited weakness before reconnecting

### Notify (know your clocks)
- [ ] HIPAA breach: notify individuals without unreasonable delay, HHS per
      thresholds (60-day outer limit)
- [ ] PCI: notify acquirer per card brand requirements
- [ ] State laws: check affected-resident thresholds and timelines
- [ ] Cyber insurance: notify per policy terms BEFORE some remediation steps
- [ ] Customers/partners if contractually required

### Post-Incident
- [ ] Postmortem within 5 business days: timeline, root cause, what worked,
      what didn't
- [ ] Corrective actions with owners and dates
- [ ] Update this plan with lessons learned
- [ ] Retain the incident log per retention policy

## 5. Quick Reference — First Hour for Common Scenarios

**Ransomware:** isolate infected machines from network (pull cable/disable
Wi-Fi), do not reboot if possible, photograph screens, call insurance hotline
before engaging negotiators, assess backup integrity offline.

**BEC / fraudulent wire:** contact bank immediately for recall, lock the
compromised mailbox, enable MFA and check mail rules (attackers add
forwarding), review recent logins.

**Cloud account takeover:** revoke sessions, rotate keys, review audit logs
for data access, enable MFA enforcement, check for new users/sharing links.

**PHI/PII exposure:** contain access, document exactly which records were
involved, engage counsel for notification analysis.

## 6. Maintenance

- [ ] Tabletop exercise annually (walk one scenario end-to-end with all roles)
- [ ] Verify contact list quarterly (people change jobs)
- [ ] Test backup restoration quarterly
- [ ] Review after every real incident

---
*Educational material. Legal notification obligations vary by jurisdiction;
confirm with counsel.*
