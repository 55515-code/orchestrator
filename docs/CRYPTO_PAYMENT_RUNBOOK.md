---
title: Crypto Payment Flow Runbook
last_verified: 2026-08-08
owner: ahron
status: active
components:
  - workers/payment-verifier/index.js
  - workers/resource-delivery/index.js
  - workers/schema.sql
  - substrate/crypto/wallet_manager.py
  - substrate/crypto/backup.py
  - substrate/crypto/pricing.py
  - substrate/crypto/inventory.py
  - substrate/crypto/token_registry.py
  - substrate/crypto/policy.py
  - substrate/crypto/revenue.py
  - substrate/crypto/opportunities.py
  - substrate/resources/api_access.py
  - substrate/monitoring/crypto_alerts.py
  - substrate/security/audit_trail.py
  - substrate/security/abuse_detection.py
  - substrate/agents/market_research.py
  - substrate/agents/resource_gen.py
  - substrate/pipelines/resource_pipeline.py
  - substrate/pipelines/quality_gate.py
  - substrate/pipelines/expansion_trigger.py
  - scripts/crypto/wallet_gen.py
  - scripts/crypto/backup_proton.py
  - scripts/crypto/export_site_data.py
wallet_purposes: [payments, donations, kilo-code]
---

# Crypto Payment Flow Runbook

Standing rule (crypto-rules.yaml): **payment flows and their technology must
always be documented, current, and vetted.** This runbook is machine-checked:
`PaymentFlowGovernance.docs_status()` fails when this file is missing or when
`last_verified` is older than the configured freshness window (90 days).

## 1. Architecture

```
Buyer/Donor ── L2 transfer ──► Payment wallet (Polygon/Base)
                                     │
        POST /api/verify-payment     │ RPC fallback (≥2 providers)
Buyer ──────────────────────────► payment-verifier Worker
                                     │ D1: payments, delivery_tokens, rate_limits
                                     ▼
                              resource-delivery Worker ──► R2 signed URL (1h)
```

- **Edge**: Cloudflare Workers (`payment-verifier`, `resource-delivery`), D1
  (`crypto-payments`), R2 (`digital-resources`). Public addresses only — no
  keys ever leave `state/crypto/`.
- **Local**: `substrate/crypto/` manages wallets, backups, pricing, inventory,
  and governance. Audit trail: `state/crypto/audit.jsonl` (hash-chained).
- **Backup**: Proton Drive sync folder (`CryptoBackups/`) or staged under
  `state/crypto/backups/` for manual upload (Proton has no public write API).

## 2. Flows

### 2.1 Payment verification (`POST /api/verify-payment`)

Inputs: `{txHash, resourceId, network, token?}`.

1. Rate limit by IP (D1 `rate_limits`).
2. Fetch transaction + receipt from RPC providers in order (fallback list).
3. Reject unless: confirmed (`confirmations >= MIN_CONFIRMATIONS`), recipient
   matches the payment address (native) or ERC-20 Transfer to it (USDC/DAI),
   amount ≥ catalog price for the token's decimals, and `txHash` not already
   recorded (replay protection).
4. Insert payment row, issue one-time `delivery_token`, return it.

Failure modes: RPC outage (fallback to next provider; 503 if all fail),
underpayment (402 with reason), replay (409). Rollback: none needed — the
verification step is read-only on-chain; deleting a D1 payment row revokes the
delivery token.

### 2.2 Resource delivery (`GET /api/resource/:id`)

Requires header `X-Delivery-Token`. Token must be unused and unexpired. On
success the token is marked used (one-time) and an R2 signed URL is returned
(3600s expiry) with the resource checksum for client verification.

Free resources: `POST /api/free-token` issues a token for catalog items with
`price_usdc = 0`, rate-limited per IP. No payment is ever required for free
items.

### 2.3 Donations

Public donation addresses (purpose `donations`) are shown on the site
(`/support`) and served by `GET /api/donation-info`. Donations require no
verification loop; they are monitored by `crypto_alerts` balance checks.
Donation addresses are derived from an encrypted seed stored locally and
backed up per §2.5 — the site only ever contains public addresses.

### 2.4 Wallet operations (Tier 2)

`scripts/crypto/wallet_gen.py create --purpose <p> --directive "<text>"`
generates a BIP-39 (256-bit) master seed and derives BIP-44 addresses
`m/44'/60'/0'/0/<index>`. Seeds are Fernet-encrypted into
`state/crypto/seeds.enc`; the key resolves from (in order) explicit flag,
`SUBSTRATE_CRYPTO_KEY`, system keyring, then `state/crypto/master.key`
(chmod 600, gitignored). Every generation/derivation appends to the audit
trail. Without a directive the operation is refused and the refusal is audited.

### 2.5 Backup and recovery (verified)

`scripts/crypto/backup_proton.py` builds a double-encrypted bundle, writes it
to `<ProtonDriveSync>/CryptoBackups/<ts>-substrate-wallets.enc`, reads it
back, decrypts, and compares checksums (3 attempts). Without a sync folder the
bundle is staged in `state/crypto/backups/` and the operator is told to upload
it via an official Proton app. Status lands in `state/crypto/backup-status.json`.

Recovery test: `wallet_gen.py verify-recovery --purpose <p>` re-derives all
recorded addresses from the supplied seed and reports mismatches.

### 2.6 Price updates (Tier 2)

`PricingEngine.update_prices()` persists new USD base prices only with a
directive; token prices recompute from live rates (stablecoins stay pegged;
volatile tokens are withheld when rates are unavailable rather than served
stale).

### 2.7 Competitive undercutting (Tier 2, PF-011)

`PricingEngine.apply_competitive_update()` proposes prices 5% under comparator
market prices, never below the cost-covering floor (50% of base). Cuts apply
only when `revenue_trend_ok` is true — a declining revenue trend blocks
discounting. All price changes require a directive and are audited.

### 2.8 Revenue loop and opportunity spend (PF-016/PF-017)

- Settled payments are recorded by `RevenueTracker.record_payment()` into
  `state/crypto/revenue.json`; `trend()` reports month-over-month movement.
- `OpportunityEngine` governs micro-spend (floor 0.1 cent, cap $0.05,
  EV/cost ≥ 2, max 10% of the stack) from the **earned stack only** — the
  principal/power-source is never allocated. Allocation requires a Tier 2
  directive; realized returns are credited back to the stack.
- The stack can be seeded by the `stack_provider` (e.g. the revenue tracker);
  no speculative instruments, leverage, or loss-accepting positions.

### 2.9 Programmatic buyers (bots and autonomous networks)

- Discovery: `resources/llm-catalog.json`, site `llms.txt`, worker `/api/llms`,
  `/api/catalog`. Pull-based and passive only (PF-015).
- Purchase contract: `GET /api/resource/:id` without a token returns HTTP 402
  with payment instructions (amount, tokens, networks, verify/deliver
  endpoints) — the x402-style pattern for payment-capable agents.
- Access: `APIAccessManager` issues API keys (Tier 2, expiring, revocable) for
  bots that buy offload services; keys live in `state/crypto/api_keys.json`
  and never in code.
- The `market-research` agent (Tier 0, weekly) scans channels/protocols into
  `.research/market-demand/`; `ExpansionTrigger` queues candidates (Tier 2);
  `resource-generator` (Tier 1) drafts and gates new resources (publish Tier 2).

## 3. Threat model (current)

| Threat | Mitigation |
|---|---|
| Key theft from edge | No keys on Workers; D1 holds public addresses only |
| Seed loss | Verified encrypted backups; recovery test command |
| Payment replay | `payments.tx_hash` primary key; one-time delivery tokens |
| Forged confirmation | Multi-RPC fallback + confirmation depth check |
| Delivery token leak | One-time use, 1h expiry, checksum in response |
| Free-tier abuse | Per-IP rate limits + burst detection (AbuseDetector) |
| Audit tampering | Hash-chained JSONL; chain verified during vetting |
| Stale docs / silent drift | This runbook is machine-checked (PF-001) |

## 4. Change procedure (mandatory)

Every change to a payment flow requires, in order:

1. Update this runbook (flow, failure modes, component list) and bump
   `last_verified` after end-to-end testing.
2. Add/adjust tests; run them to green.
3. Record the change: `PaymentFlowGovernance.gate_change(change_id, summary,
   directive=..., docs_updated=True, tests_green=True, checklist={...})`.
4. Deploy. Post-deploy, re-run `verify_all()` (vetting report).

Skipping any step causes `gate_change` / `verify_all` to fail, which blocks
promotion under crypto-rules PF-001/PF-002.

## 5. Vetting checklist

- [ ] Runbook sections match implemented behavior
- [ ] `last_verified` reflects the most recent end-to-end test
- [ ] `validate_checksums()` green for the full catalog
- [ ] Backup verified (`backup-status.json.verified == true`)
- [ ] Audit chain verifies (`AuditTrail.verify().ok`)
- [ ] Worker RPC fallback list has ≥2 providers
- [ ] Rate limits configured on all public endpoints

## 6. Incident response

1. Suspected key compromise: treat funds as lost; derive a new wallet (Tier 2
   directive), export new public addresses (`export_site_data.py`), update D1
   `donation_addresses`/`resources` payment address, and record in the audit
   trail. Never reuse a compromised purpose.
2. Forged payment reports: verify the tx hash on-chain via an independent
   explorer before any delivery; mark the payment row `disputed`.
3. Broken audit chain: stop financial operations, snapshot `state/crypto/`,
   and investigate before appending further records.
