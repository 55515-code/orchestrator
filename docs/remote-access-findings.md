# Remote Access & Device Setup — Research Findings + Implementation

Date: 2026-08-25

## Problem statement

1. Remote login to the gateway always required a token (friction, mismatches).
2. The Android node (`phone-3a`) was repeatedly rejected with
   `gateway token missing/mismatch` over the already-working HTTPS Serve URL.
3. WhatsApp connection was accidentally broken by a forced re-auth.

## Root causes found (deep research: docs + installed gateway source + logs)

### 1. Tokenless remote login was possible all along — just disabled

OpenClaw has `gateway.auth.allowTailscale`: when enabled, tailnet devices
authenticate to the Control UI/WebSocket via **Tailscale identity headers**
(`tailscale-user-login`) instead of a token. Confirmed in installed source
(`dist/auth-resolve-*.js`):

```js
allowTailscale = authConfig.allowTailscale
  ?? (tailscaleMode === "serve" && mode !== "password" && mode !== "trusted-proxy")
```

Before this change: `allowTailscale` unset AND `tailscale.mode` off → the
`??` fallback resolved to `false` → token required everywhere.

### 2. The Serve route was already working

`tailscale serve status` showed a live, tailnet-only HTTPS route:

```
https://cachyos-x8664.tail0b124a.ts.net:10000  →  proxy http://127.0.0.1:8090
```

This is the right topology per docs ("keep `gateway.bind: loopback` and use
Tailscale Serve"). The phone was reaching it (`curl` → HTTP 200) but being
rejected at the WS auth layer for missing token.

### 3. Token mismatch confusion

The "gateway token" I sent earlier was actually the **substrate panel token**
(`state/panel-auth-token.txt`), not the OpenClaw gateway token — hence the
`token mismatch` errors in the logs.

### 4. HTTPS origin not allowlisted

`gateway.controlUi.allowedOrigins` listed only HTTP loopback/LAN origins, not
the HTTPS Serve origin, so even a successful token auth would hit origin
checks.

## Implementation (applied)

1. `gateway.auth.allowTailscale = true` — tailnet devices authenticate via
   Tailscale identity, no token.
2. Added `https://cachyos-x8664.tail0b124a.ts.net:10000` to
   `gateway.controlUi.allowedOrigins`.

Config validated clean (`openclaw config validate` → valid). Both keys are
`restart` reloadKind, so they apply on gateway restart. Gateway restart was
safely deferred while sessions drained (no loop risk; `bind` and
`tailscale.mode` were NOT touched).

## The design you asked for

- **Always-on HTTPS remote login, no token:** any device on your tailnet
  (`phone-3a`, `phone`, the gateway host) now reaches
  `https://cachyos-x8664.tail0b124a.ts.net:10000` and authenticates via
  Tailscale identity — no token pasting.
- **Keep token auth as fallback:** `auth.mode` stays `token`; Tailscale
  identity is an *additional* accepted path, not a removal of the fallback.
- **Surgical restore:** `scripts/credential_snapshots.py` + `snapshot_guard.py`
  + `docs/credential-restore-runbook.md` (built earlier today) cover the
  credential-wipe class of failure.

## Open items

- **WhatsApp:** channel is `logged out` (terminal-disconnect). Requires one
  fresh QR scan to re-link; session was server-invalidated (status 440), no
  client-side restore possible. After linking, snapshot the creds dir.
- **Gateway restart:** apply pending config by restarting once sessions drain.

## Trusted references

- `docs/gateway/tailscale.md` — Serve/Funnel modes, `allowTailscale`
- `docs/gateway/remote.md` — remote topology (loopback + Serve recommended)
- `docs/gateway/trusted-proxy-auth.md` — identity-aware proxy (not used here)
