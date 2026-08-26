# Surgical Credential Restore Runbook

**Principle:** all stateful channel data (credentials, pairing, config) must be
surgically restorable. Before any destructive operation — logout, forced
re-auth, config overwrite — a timestamped snapshot is taken so rollback is one
command, not a re-setup.

Motivated by incident 2026-08-25: a forced WhatsApp re-auth (`force=true`)
cleared live Baileys credentials; the extension's `.bak` was a same-moment
copy (useless) and the session was already server-invalidated. No rollback
existed. This tooling prevents that class of failure.

## Commands

All via the substrate CLI (run from workspace root):

| Action | Command |
|--------|---------|
| Snapshot a credential/config path | `uv run python scripts/substrate_cli.py credential-snapshot <path> --reason "<why>"` |
| List snapshots | `uv run python scripts/substrate_cli.py credential-snapshots` |
| Restore (atomic, reversible) | `uv run python scripts/substrate_cli.py credential-restore <snapshot-dir>` |
| Prune old snapshots | `uv run python scripts/substrate_cli.py credential-snapshots-prune --days 30` |

Standalone (no substrate deps):

| Action | Command |
|--------|---------|
| Snapshot | `python3 scripts/credential_snapshots.py snapshot <path> --reason "<why>"` |
| List | `python3 scripts/credential_snapshots.py list` |
| Restore | `python3 scripts/credential_snapshots.py restore <snapshot-dir>` |
| Prune | `python3 scripts/credential_snapshots.py prune --days 30` |

Pre-op guard wrapper (snapshot then exec the guarded command):

```bash
python3 scripts/snapshot_guard.py --path ~/.openclaw/credentials/whatsapp \
  --reason "pre-logout guard" -- openclaw channels logout --channel whatsapp
```

Guard check mode (exit 0 if protected):

```bash
python3 scripts/snapshot_guard.py --path ~/.openclaw/credentials/whatsapp --check
```

## Snapshot layout

Snapshots live in `state/credential-snapshots/` (gitignored, local only):

```
state/credential-snapshots/
  <sanitized-source>__<UTC-timestamp>/
    manifest.json   # source, createdAt, reason, kind, entryCount
    data/           # full copy of the file or directory
```

## WhatsApp recovery playbook

### Credentials were wiped but the session may still be server-valid

1. `uv run python scripts/substrate_cli.py credential-snapshots` — find the
   latest snapshot of `~/.openclaw/credentials/whatsapp`.
2. Restore it: `credential-restore <snapshot-dir>`.
3. Restart the channel: `openclaw channels status --deep` to check; the
   gateway reconnects with the restored creds.
4. If the server already invalidated the session (status 440 / "session
   conflict"), a fresh QR is required — restoration only helps if the
   server-side session is still alive.

### Session conflict (status 440)

WhatsApp refuses two live sessions from the same device. The old phone
session must be removed from **WhatsApp → Linked Devices**, then the gateway
re-links. Use `snapshot_guard.py` before `openclaw channels logout` so the
next link attempt is protected.

### Prevention (do this now)

```bash
# After any successful WhatsApp link, snapshot immediately:
uv run python scripts/substrate_cli.py credential-snapshot \
  ~/.openclaw/credentials/whatsapp \
  --reason "post-link known-good state"
```

## Rules

- **Never** run `openclaw channels logout` or `whatsapp_login(force=true)`
  without a prior snapshot of the credential dir.
- A `.bak` created at overwrite-time is **not** a restore point.
- Snapshots are local and unencrypted — treat them like the credentials they
  mirror (mode 600, never commit).
- Restores are atomic (temp dir + rename) and always leave a pre-restore
  snapshot as rollback.
