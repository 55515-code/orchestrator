# Approval Lane

The approval lane is the substrate's verified outbound communication channel
for automation that requires human input. Instead of waiting for the operator
to log in, automation routes approval requests through a verified channel
(email; SMS when a provider is configured) and accepts the operator's
code-verified reply as the explicit directive.

**Core guarantee: the lane never auto-approves.** A pending approval is only
resolved by a reply carrying its single-use code. The verified reply *is* the
explicit human directive required by the substrate autonomy-tier rules
(Tier 2 actions always require an explicit human directive).

## Channels

| Channel key       | Backend             | Status on this host                                   |
|-------------------|---------------------|-------------------------------------------------------|
| `email`           | Proton Bridge SMTP  | Account loaded & syncing (ahronzombi@protonmail.com)  |
| `sms:7163528536`  | provider            | Blocked: no SMS provider configured                   |
| `sms:7162666606`  | provider            | Blocked: no SMS provider configured                   |

- Email is sent through the Proton Mail Bridge SMTP relay
  (`127.0.0.1:1025`, STARTTLS, unauthenticated local). The bridge account
  `ahronzombi` (`ahronzombi@protonmail.com`, combined address mode) is loaded
  and syncing (v3.25.0, SecretService keychain). The SMTP relay accepts sends
  once the account's address registers after the initial sync; until then it
  rejects with "The account is not available in Bridge".
  `scripts/wait_for_mail_sync.py` polls and delivers the coded test message the
  moment the account registers.
- SMS requires a provider (e.g. Twilio). Add credentials under
  `~/.config/substrate/approval_lane.json` and implement provider delivery in
  `substrate/approvals.py::sms_backend_send()`.

## CLI

```
uv run python scripts/substrate_cli.py approval-lane status
uv run python scripts/substrate_cli.py approval-lane send-test --channel email
uv run python scripts/substrate_cli.py approval-lane verify --channel email --code XXXX
uv run python scripts/substrate_cli.py approval-lane request --subject "deploy" --body "details"
uv run python scripts/substrate_cli.py approval-lane resolve --id apv-... --code XXXX --decision approve
uv run python scripts/substrate_cli.py approval-lane poll
uv run python scripts/substrate_cli.py approval-lane watch
```

- `status` — lane state: channels, verification status, pending approvals
  (never includes codes).
- `send-test` — issues a single-use verification code and dispatches a test
  message on a channel. On delivery failure the code is invalidated and the
  precise error is recorded.
- `verify` — verifies a channel with its code and, if no primary exists,
  promotes it to the permanent primary approval lane.
- `request` — records a pending approval and dispatches a notification with a
  single-use approval code through the verified primary channel.
- `resolve` — resolves a pending approval with its code (`approve`/`deny`).
- `poll` — polls the verified channel's mailbox (IMAP) for coded replies and
  auto-verifies/auto-resolves. Requires IMAP credentials under
  `~/.config/substrate/approval_lane.json` (`imap: {host, port, username,
  password}`).
- `watch` — one autonomous watch pass (see below).

## Autonomous background operation

`scripts/approval_lane_watch.py` runs the lane autonomously with no operator
login:

1. **Retries test-message delivery** for unverified channels every interval
   (default 30 min). Email becomes deliverable the moment the bridge account
   is re-added; SMS the moment a provider is configured.
2. **Polls the verified primary channel** for coded replies and
   auto-verifies / auto-resolves approvals.
3. **Confirms the primary lane exactly once** by sending a "lane is live"
   message through the verified channel.

Idempotent: it never re-sends a test while a code is awaiting reply, and never
verifies without a matching reply code.

```
uv run python scripts/approval_lane_watch.py                # default 30 min
uv run python scripts/approval_lane_watch.py --interval 300 # every 5 min
uv run python scripts/approval_lane_watch.py --once         # single pass
```

Each pass is appended to `state/approval-lane-watch.json`. For reboot
persistence, install a systemd user timer modeled on
`scripts/install_agent_timer.sh`.

## Integration

- State: `state/approval-lane.json` (0600 perms).
- Operator config (credentials): `~/.config/substrate/approval_lane.json`.
- Gate hook: `substrate/approvals.py::notify_approval_gate()` — wired into the
  `config-sync-deploy` / `dotfiles-deploy` `--directive` gates. When a
  directive is missing, an approval request is dispatched through the lane
  (gate semantics unchanged — the gate still fails until the operator
  resolves it). Agents can call the same hook for their own directive gates.
- Catalog: `integrations.yaml` entry `approval_lane`.
- Audit: every lane operation is recorded in the learning log via
  `record_execution`.

## Verification flow

1. `send-test --channel <key>` — code lands on the channel.
2. The operator replies with the code through the same platform.
3. `verify --channel <key> --code <CODE>` (or the watch loop, via IMAP polling)
   marks the channel verified and promotes it to the primary approval lane.
4. Automation that needs input calls `request_approval(...)`; the operator's
   reply with the approval code resolves it. The primary lane then carries the
   "lane is live" confirmation message.

## Security posture

- Single-use, expiring codes (72 h), max 5 failed verification attempts.
- Codes are never returned by `status`; undelivered codes are invalidated.
- A channel is promoted to primary only after a code-verified reply from the
  operator; its address is fixed at verification time.
- Nothing auto-approves: `resolve` requires the matching single-use code.
