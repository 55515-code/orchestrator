# MEMORY.md

## Standing Design Principle: Surgical Restorability (2026-08-25)

**Principle:** All system data, configs, and credentials must be surgically restorable. Before any destructive operation (logout, credential rotation, config overwrite), snapshot the current state with a timestamp. Not just a `.bak` of the same content.

**Requirements:**
- Versioned state snapshots before destructive operations
- Atomic operations with rollback capability
- Server-validated state tracking (separate from raw credential files)
- Pre-operation safety checks and dry-run modes

**Incident that motivated this:** WhatsApp credentials were cleared by `whatsapp_login(force=true)` at 21:32, then the session was server-invalidated at 21:35 with "status 440: session conflict." The `.bak` file was identical to the current file (same-moment copy), and even if it had been older, the server-side session was already gone. No surgical rollback was possible; required a fresh QR scan.

**Action items:**
- Add pre-operation snapshot hook for WhatsApp credential operations (and other stateful integrations)
- Version credential backups with timestamps, not just `.bak`
- Track server-validated session state separately from raw credential files
- Add dry-run mode for destructive operations



## Incident: Android node remote-setup failure (2026-08-25) — must not repeat

**What happened:** While configuring remote connectivity for the Android node (`nothing-3a`), I:
1. Set `gateway.tailscale.mode=funnel` without the validator-required `gateway.bind=loopback` → **gateway restart loop** (`Invalid config`), user had to manually recover.
2. Hit a privileged step (`sudo tailscale set --operator=ahron`) that cannot run from a WhatsApp session → blocked, and looped trying.

**Rules going forward:**
- **Validate before applying any restart-required config.** Run `openclaw config validate` (or a JSON sanity check) and use `gateway config.schema.lookup` to check dependent fields *before* writing. The known dependency: `tailscale.mode=funnel` requires `gateway.bind=loopback` **and** `gateway.auth.mode=password`.
- **Elevated/sudo commands need the user.** From WhatsApp sessions `tools.elevated` is blocked; do not retry sudo in a loop. Surface the exact one-time command and wait.
- **Tailscale Serve/Funnel on this host needs the operator grant** `sudo tailscale set --operator=ahron` (one-time, user-run). Without it, gateway-initiated serve/funnel fails with "Access denied: serve config denied".
- **Config was reverted by user during recovery**: `gateway.bind=lan`, `tailscale: {}` (funnel removed), `trustedProxies: [100.64.0.0/10, 127.0.0.1]` still set, `auth.mode=token`. Re-apply carefully if resuming funnel.

## Android node connectivity notes
- Node `nothing-3a` (a303aa53…): Termux node-host, caps system/browser/file/local-inference, approved. Connect path historically = LAN (dies when phone remote).
- Phone Tailscale (`nothing-phone-3a`, 100.105.175.41) has been **offline ~9 days** — remote connectivity depends on fixing this.
- Gateway already has a tailnet-only Serve URL: `https://cachyos-x8664.tail0b124a.ts.net:10000` → 127.0.0.1:8090.
- Robust remote path options: (A) Tailscale on phone + node-host pointed at serve URL, or (B) Funnel (public wss://) — B requires password auth mode + operator grant.
- Setup code generation: `openclaw qr --setup-code-only` / `--url wss://...`; approval via `openclaw devices approve <requestId>`.
