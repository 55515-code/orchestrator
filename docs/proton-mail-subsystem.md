# Proton Mail Subsystem — Stability Runbook

> Status: **STABLE** (2026-09-06). Durable outbox + watchdog + transition alerting.

## Architecture

```
Proton Mail Bridge (protonmail-bridge.service, :1143 IMAP / :1025 SMTP)
        │ IMAP poll every 30s
        ▼
proton_bridge_hook.py  (proton-bridge-hook.service)
  1. retry durable outbox  (~/.local/state/proton-bridge-hook/outbox/)
  2. fetch last 25 INBOX messages, POST to hook on 2xx only
  3. failure → write outbox entry → retried next poll (bounded 7d)
        │ POST /hooks/proton (Bearer token)
        ▼
OpenClaw Gateway hook → agent run (main, kilo-auto/free + local fallbacks)
        ▲
        │ 15-min health poll
proton-health-check.timer → proton_health_check.py
   → state/proton-health.json   (ok | degraded | down, transition flags)
        │ heartbeat reads
        ▼
proton_heartbeat_report.py → prints SILENT | alert | recovery (no spam)
```

## Durability guarantee (no silent email loss)

- A message is **only marked delivered after the hook returns 2xx**.
- On failure the hook writes `~/.local/state/proton-bridge-hook/outbox/<id>.json`
  and keeps it (drop only after 7 days, with a WARN log).
- The outbox is drained **before** new mail on every poll.
- OpenClaw hook delivery is idempotent per message id → retries are safe.
- Verified in production 2026-09-06 16:40–17:01: 3 emails hit 503 during a
  gateway restart, queued, and auto-delivered on recovery. Zero loss.

## Files

| Path | Role |
|---|---|
| `scripts/proton_bridge_hook.py` | IMAP poll → hook POST, durable outbox (daemon or `--once`) |
| `scripts/proton_health_check.py` | 6-layer health check → `state/proton-health.json` |
| `scripts/proton_heartbeat_report.py` | Transition-based alert text for heartbeat polls |
| `~/.config/systemd/user/proton-health-check.{service,timer}` | 15-min watchdog |
| `~/.config/systemd/user/proton-bridge-hook.service` | Hook daemon (Restart=always) |
| `~/.config/systemd/user/protonmail-bridge.service` | Proton Bridge (keyring drop-in) |
| `state/proton-health.json` | Current health + transition flags |
| `state/proton-heartbeat-state.json` | Last alert state (re-alert throttle) |

## Health checks (proton_health_check.py)

| Check | Failure meaning |
|---|---|
| `bridge_service` | `protonmail-bridge.service` not active |
| `hook_service` | `proton-bridge-hook.service` not active |
| `imap` | IMAP login/select on 127.0.0.1:1143 failed (bounded, single try) |
| `outbox` | Outbox entry older than 1h (drain stuck) |
| `hook_endpoint` | `/hooks/proton` unreachable (401/403 = up + auth enforced) |
| `agent_runs` | Hook agent run `status=error` in gateway log within 60 min |

Status: `ok` (all pass) · `degraded` (backlog/agent-run issues) · `down`
(bridge/hook/imap down). Exit: ok/degraded = 0, down = 1.

## Alert policy (no heartbeat spam)

Heartbeat polls run `proton_heartbeat_report.py`; it prints **SILENT** unless:

- transition into degraded/down → one alert
- degraded → down escalation → one alert
- recovery → one ✅ notice
- persistent degraded re-alert ≤ 24h; persistent down re-alert ≤ 6h

Never alert on every poll for the same underlying condition.

## Operations

```bash
# Manual health probe
.venv/bin/python scripts/proton_health_check.py; echo $?

# What would the heartbeat say right now?
.venv/bin/python scripts/proton_heartbeat_report.py

# Drain a stuck outbox (e.g. gateway long down)
ls -la ~/.local/state/proton-bridge-hook/outbox/

# One-shot mail fetch (no daemon)
.venv/bin/python scripts/proton_bridge_hook.py --once
echo $?   # 0 = outbox empty, 1 = still pending

# Restart pieces
systemctl --user restart proton-bridge-hook.service
systemctl --user restart protonmail-bridge.service
```

## Config invariants (do not regress)

- `channels.whatsapp.dmPolicy: allowlist`, `allowFrom: ["+17163528536"]` — owner only.
- `channels.whatsapp.groupPolicy: disabled`.
- `commands.ownerAllowFrom: ["whatsapp:+17163528536"]` — privileged commands + heartbeat route.
- Hook mapping: `/hooks/proton` → agent `main`, `deliver: false`.
- Bridge password lives in the OS keyring (`substrate-credentials`), never plaintext.
- Snapshots before config surgery: `~/.openclaw/snapshots/openclaw.json.<stamp>.before-*`.

## Known residual risks

1. Hook agent runs still depend on provider health; fallbacks
   (ollama/qwen3.5:9b → llama3.1:8b) absorb 503s but a run can still error —
   now surfaced via `agent_runs` check + transition alerts only, never spam.
2. Ollama embeddings can be cold right after gateway restart → memory search
   may fail briefly; outbox keeps the email until the run succeeds.
3. Emails older than the last-25 window are not re-fetched after a >7-day
   outage (bounded by design); the daily digest agent covers the last 24h.
