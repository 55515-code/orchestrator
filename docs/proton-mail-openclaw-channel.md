# Proton Mail — OpenClaw Communication Channel

Proton Mail is fully integrated as a two-way communication channel with OpenClaw:
- **Outbound (send)**: Proton Mail Bridge SMTP (`127.0.0.1:1025`) — used by the substrate approval lane and any script.
- **Inbound (receive)**: Bridge IMAP (`127.0.0.1:1143`) → poll daemon → OpenClaw hook (`POST /hooks/proton`) → agent run.

## Architecture

```
Outbound:
  script/substrate ──SMTP AUTH──▶ Proton Bridge (:1025) ──▶ Proton servers ──▶ recipient

Inbound:
  Proton servers ──▶ Proton Bridge (:1143) ──▶ proton-bridge-hook.service
        ──HTTP POST──▶ OpenClaw gateway (/hooks/proton) ──▶ agent:main (hook:proton:<id>)
```

## Components

| Component | Where | Status |
|---|---|---|
| Proton Mail Bridge | systemd user service `protonmail-bridge.service` | running, v3.25.0, account loaded |
| Bridge SMTP | `127.0.0.1:1025` (STARTTLS + AUTH) | working |
| Bridge IMAP | `127.0.0.1:1143` (STARTTLS) | working |
| Hook bridge daemon | systemd user service `proton-bridge-hook.service` → `scripts/proton_bridge_hook.py` | running, polls every 30s |
| OpenClaw hooks | `/hooks/proton` mapping → `agent:main` | verified 200 + agent runs |

## Credentials (no plaintext)

The Proton Bridge per-account password is stored in the OS keyring
(secret-service), **not** in any config file:

```
service=substrate-credentials  account=proton-bridge-smtp
```

Runtime lookup: `secret-tool lookup service substrate-credentials account proton-bridge-smtp`

`~/.config/substrate/approval_lane.json` now contains **no passwords** — the
`imap.password` / `smtp.password` fields are empty strings and resolved from
the keyring at runtime by `substrate/approvals.py` (`_bridge_smtp_password()`).

The OpenClaw hook token lives in `~/.config/substrate/hooks-token.txt`
(mode 600), referenced by the daemon.

## Sending email

From Python (any script):

```python
import smtplib
from email.mime.text import MIMEText
import subprocess

pw = subprocess.run(
    ["secret-tool", "lookup", "service", "substrate-credentials", "account", "proton-bridge-smtp"],
    capture_output=True, text=True, check=True,
).stdout.strip()

msg = MIMEText("body")
msg["From"] = "ahronzombi@protonmail.com"
msg["To"] = "someone@example.com"
msg["Subject"] = "Subject"

s = smtplib.SMTP("127.0.0.1", 1025, timeout=30)
s.starttls()
s.ehlo()
s.login("ahronzombi@protonmail.com", pw)
s.sendmail("ahronzombi@protonmail.com", ["someone@example.com"], msg.as_string())
s.quit()
```

Or use the substrate lane: `substrate/approvals.py` → `email_backend_send()`
(now authenticates automatically via the keyring).

## Receiving email (inbound → agent)

The daemon (`scripts/proton_bridge_hook.py`) polls Bridge IMAP every 30
seconds for new messages and POSTs each to the OpenClaw hook endpoint:

```
POST http://127.0.0.1:8090/hooks/proton
Authorization: Bearer <hook-token>
Content-Type: application/json

{ "messages": [ { "id": "<message-id>", "from": "...", "to": "...",
                  "subject": "...", "date": "...", "body": "...", "uid": "..." } ] }
```

The gateway mapping (`hooks.mappings[0]`, match path `proton`) converts each
message into an isolated agent run:

- session key: `hook:proton:<message-id>` (per-thread sessions)
- agent: `main`
- message template includes From/To/Subject/Date/body
- `deliver: false` (no reply routing; the agent can reply via SMTP tools)

Already-seen messages are tracked in
`~/.local/state/proton-bridge-hook/seen.json` (UID + content-hash dedup), so
restarts never re-post old mail.

### Daemon operations

```bash
systemctl --user status proton-bridge-hook      # status
journalctl --user -u proton-bridge-hook -f      # live log
uv run python scripts/proton_bridge_hook.py --once   # one-shot process new mail
```

Config via env (`~/.config/substrate/proton-bridge-hook.env`):

| Env | Default |
|---|---|
| `PROTON_IMAP_HOST` | `127.0.0.1` |
| `PROTON_IMAP_PORT` | `1143` |
| `PROTON_EMAIL` | `ahronzombi@protonmail.com` |
| `PROTON_BRIDGE_PW` | keyring lookup |
| `OPENCLAW_HOOK_URL` | `http://127.0.0.1:8090/hooks/proton` |
| `OPENCLAW_HOOK_TOKEN` | `~/.config/substrate/hooks-token.txt` |
| `PROTON_POLL_SECONDS` | `30` |

## OpenClaw hook config

In `~/.openclaw/openclaw.json`:

```json5
hooks: {
  enabled: true,
  token: "<dedicated hook token>",
  path: "/hooks",
  defaultSessionKey: "hook:proton:default",
  allowRequestSessionKey: true,          // required for templated sessionKey
  allowedSessionKeyPrefixes: ["hook:"],  // constrained to hook: prefix only
  allowedAgentIds: ["main"],
  mappings: [
    {
      match: { path: "proton" },
      action: "agent",
      agentId: "main",
      wakeMode: "now",
      name: "Proton Mail",
      sessionKey: "hook:proton:{{messages[0].id}}",
      messageTemplate: "From: {{messages[0].from}}\nTo: {{messages[0].to}}\nSubject: {{messages[0].subject}}\nDate: {{messages[0].date}}\n\n{{messages[0].body}}",
      deliver: false,
    },
  ],
}
```

## Verification

```bash
# 1. Bridge healthy
systemctl --user is-active protonmail-bridge.service
grep "Finished loading users" ~/.local/share/protonmail/bridge-v3/logs/*.log | tail -1

# 2. Hook endpoint responds
TOKEN=$(cat ~/.config/substrate/hooks-token.txt)
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8090/hooks/proton \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"messages":[{"id":"ping","from":"t@t","subject":"s","body":"b"}]}'
# expect 200

# 3. Daemon healthy
systemctl --user is-active proton-bridge-hook.service

# 4. End-to-end: send self-email, watch daemon log, check gateway log
#    journalctl --user -u proton-bridge-hook -f
#    grep "hook agent run" /tmp/openclaw/openclaw-*.log | tail
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no such user` on SMTP | Bridge account not loaded — restart `protonmail-bridge.service`, verify keyring unlocked (`secret-tool` lookup works) |
| SMTP auth rejected | Re-read bridge password via `protonmail-bridge-core --cli` (`info`), update keyring: `secret-tool store --label "..." service substrate-credentials account proton-bridge-smtp` |
| Hook 401 | Token mismatch — check `~/.config/substrate/hooks-token.txt` vs `hooks.token` in openclaw.json |
| Hook 404 | Gateway not restarted after config change — `systemctl --user restart openclaw-gateway` |
| Daemon `Connection refused` on :8090 | Gateway down; ensure `openclaw-gateway.service` active |
| Duplicate agent runs | Clear `~/.local/state/proton-bridge-hook/seen.json` only if you want re-processing |
