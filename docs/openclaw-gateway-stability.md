# OpenClaw Gateway Stability Runbook

## Problem

The OpenClaw Gateway (`openclaw-gateway.service`, Control UI on
`127.0.0.1:8090`) repeatedly goes offline and does not come back on its own.

## Root causes

1. **`Restart=on-failure` (or equivalent) on the unit.** The gateway's built-in
   channel health monitor sends itself `SIGTERM` for stale sockets (Discord
   401 storms, Telegram stale connections, etc.). A clean `SIGTERM` exit is
   exit code 0, which `Restart=on-failure` does **not** restart — so the
   gateway stays offline until manual intervention (`openclaw doctor`).
2. **Self-healing only checks liveness, not health.** `ensure_agency.py`
   restarts units that are `failed`/`inactive`, but a gateway that is `active`
   yet no longer answering HTTP (hung event loop / wedged adapter) is never
   restarted. A raw TCP connect to port 8090 also succeeds even when the
   process is wedged.
3. **Health-endpoint drift.** `monitor_panel.sh` probed `/healthz`, but the
   native gateway answers `/health` (`{"ok":true}`); `/healthz` is the
   container image's path. Endpoint drift can cause false "down" verdicts or
   missed real outages.
4. **No crash-loop breaker.** A broken config or port conflict would otherwise
   hot-loop restarts and fill the journal.
5. **Quadlet candidate disabled respawn.** `deploy/quadlet/openclaw-candidate.container`
   set `OPENCLAW_NO_RESPAWN=1` and `Restart=on-failure`.

## Fix (this change set)

| File | Change |
|------|--------|
| `deploy/openclaw-gateway.service` | Hardened unit: `Restart=always`, `RestartSec=3`, `RestartPreventExitStatus=78`, `StartLimitIntervalSec=300`/`StartLimitBurst=5` |
| `scripts/openclaw_gateway_watchdog.sh` | Deep HTTP health probe (`/health` then `/healthz`); restarts a hung-but-alive gateway; crash-loop breaker |
| `deploy/openclaw-gateway-watchdog.{service,timer}` | systemd user timer running the watchdog every 60s |
| `scripts/ensure_agency.py` | `ensure_gateway_health()` — restarts the gateway when `active` but HTTP is down |
| `scripts/monitor_panel.sh` | Probe `/health` then `/healthz`; crash-loop breaker |
| `deploy/quadlet/openclaw-candidate.container` | Drop `OPENCLAW_NO_RESPAWN`; `Restart=always` + breaker |
| `scripts/install_openclaw_gateway_unit.sh` | Idempotent installer for the unit + watchdog |

## Apply on the dev box

```bash
cd /home/ahron/codespace
git pull --ff-only origin main          # or the branch this lands on
bash scripts/install_openclaw_gateway_unit.sh
```

## Verify

```bash
systemctl --user status openclaw-gateway.service
systemctl --user list-timers openclaw-gateway-watchdog.timer
curl -s http://127.0.0.1:8090/health     # expect {"ok":true,...}
journalctl --user -u openclaw-gateway-watchdog.service -f
```

## Optional config hardening (in `~/.openclaw/openclaw.json`)

The built-in health monitor can be tuned so the gateway self-restarts less
often in the first place:

```jsonc
{
  "gateway": {
    "channelHealthCheckMinutes": 5,
    "channelStaleEventThresholdMinutes": 30,
    "channelMaxRestartsPerHour": 10
  }
}
```

With `Restart=always` in place, even a health-monitor `SIGTERM` now recovers
automatically within ~3 seconds instead of leaving the gateway offline.
