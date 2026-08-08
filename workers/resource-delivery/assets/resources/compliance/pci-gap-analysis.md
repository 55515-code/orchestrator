# PCI DSS Gap Analysis Workbook

**Version:** 1.0 · **Category:** Compliance · **Audience:** Merchants, payment-adjacent SaaS, small businesses

PCI DSS v4.0 shifted emphasis toward continuous security and customized
approaches. This workbook first identifies the correct Self-Assessment
Questionnaire (SAQ) for your business, then walks the 12 requirements as a gap
analysis.

## Step 1 — Determine Your SAQ

Answer these in order; the first match usually wins:

| If you... | SAQ |
|---|---|
| Only accept card-present transactions with a standalone, PTS-approved terminal, no e-commerce | SAQ P2PE |
| Accept card-present with isolated terminals AND have e-commerce fully outsourced to a PCI-DSS-compliant third party (no touch) | SAQ B-IP |
| Have e-commerce fully outsourced (redirect/iframe/hosted fields), no storage/processing on your systems | SAQ A |
| Have card-present hardware plus fully outsourced e-commerce | SAQ A-EP (check eligibility carefully) |
| Process as a service provider or store/impact cardholder data in any way | Full ROC territory — engage a QSA |

**Key scope-reduction moves:** use a hosted payment page or tokenization so
cardholder data never touches your systems; document the data flow diagram.

## Step 2 — Scope Definition

- [ ] Draw the cardholder data environment (CDE) diagram: every system that
      stores, processes, or transmits PAN, and everything connected to it
- [ ] List all payment channels: in-store, web, phone, recurring
- [ ] List service providers: acquirer, gateway, hosted page provider, MSP
- [ ] Confirm which systems are OUT of scope and why (segmentation evidence)

## Step 3 — Gap Analysis Against the 12 Requirements

Rate each: **Met / Partially Met / Not Met / Not Applicable (with rationale)**.

1. **Install and maintain network security controls**
   - [ ] Firewall/NSG rules documented and reviewed every 6 months
   - [ ] CDE not directly exposed to the internet without controls
   - [ ] Personal devices blocked from the CDE network

2. **Apply secure configurations to all system components**
   - [ ] Vendor defaults changed (passwords, SNMP strings, accounts)
   - [ ] Hardening standards documented for servers, network devices, POS
   - [ ] Unnecessary services/ports removed or justified

3. **Protect stored account data**
   - [ ] PAN storage kept to absolute minimum; retention/disposal policy
   - [ ] PAN masked after authorization; full PAN visible only when needed
   - [ ] Encryption at rest with key management documentation
   - [ ] SAD (CVV, full track, PIN) never stored, even encrypted

4. **Protect cardholder data with strong cryptography in transit**
   - [ ] TLS 1.2+ for all public-network transmission
   - [ ] Certificates current; no expired or self-signed in production
   - [ ] Policies communicate secure transmission to staff

5. **Protect all systems and networks from malicious software**
   - [ ] Anti-malware on all endpoints and servers (or documented isolation)
   - [ ] Definitions current; scans logged
   - [ ] Staff trained on phishing/social engineering vectors

6. **Develop and maintain secure systems and software**
   - [ ] Security patches within one month of release (critical)
   - [ ] Change control for CDE software
   - [ ] Secure coding training for developers; code review for custom payment code
   - [ ] Web app protection: WAF or code review (SAQ A-EP requirement)

7. **Restrict access by business need to know**
   - [ ] Access control matrix; least privilege enforced
   - [ ] Access to cardholder data needs documented approval

8. **Identify users and authenticate access**
   - [ ] Unique IDs for every user; MFA for remote access and admin consoles
   - [ ] Strong password/passphrase policy (12+ chars for user accounts in v4.0)
   - [ ] Accounts locked after repeated failures; inactive accounts removed

9. **Restrict physical access to cardholder data**
   - [ ] Cameras/access logs for server rooms and POS areas
   - [ ] Media storage secure; visitors escorted and logged
   - [ ] POS devices inspected periodically for tampering

10. **Log and monitor all access**
    - [ ] Audit logs cover all CDE access, retained 12 months (3 hot)
    - [ ] Time synchronized across systems
    - [ ] Log reviews documented (daily for critical, automated alerts)

11. **Test security of systems and networks regularly**
    - [ ] Quarterly internal and external vulnerability scans (ASV for external)
    - [ ] Annual penetration test; after significant changes
    - [ ] Change detection for critical files; IDS/IPS or documented alternative
    - [ ] PAN-finding tools on public-facing web (v4.0 script monitoring)

12. **Support information security with organizational policies**
    - [ ] Information security policy reviewed annually
    - [ ] Security awareness program, including payment security
    - [ ] Service provider due diligence and written acknowledgment of responsibility
    - [ ] Incident response plan covering payment data

## Step 4 — Remediation Plan

| Gap | Requirement | Priority | Owner | Target Date | Evidence to Produce |
|---|---|---|---|---|---|
| | | | | | |

## Step 5 — Maintain Compliance

- [ ] Calendar quarterly scans, annual policy review, annual pen test
- [ ] Track every new service provider for PCI responsibility
- [ ] Re-run scoping after any change to payment flow
- [ ] Attestation of Compliance submitted per acquirer deadline

---
*Educational material. Confirm SAQ selection with your acquiring bank or a QSA.*
