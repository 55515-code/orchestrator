# Substrate Automation Deep Review — 2026-08-17

## Findings & Fixes

### 1. 🔴 CRITICAL: Agent timer + daily report timer were DISABLED
- `substrate-agent-timer.timer` and `daily-security-report.timer` existed but were `disabled/inactive` — no automation was running from systemd.
- **Fixed**: enabled + started both. Agent cycle now runs every 5 min; daily report at 06:30.
- Note: agents were still running via manual runs/sessions (community-manager last ran 15:01), but the automated loop was dead.

### 2. 🔴 CRITICAL: gnome-keyring wedged by stuck secret-tool processes
- 3 `secret-tool lookup` processes stuck since **Aug 16** (1+ day) — hammering the keyring → fd exhaustion → "Too many open files" → keyring permanently locked.
- **Fixed**: killed stuck processes, restarted gnome-keyring-daemon. Keyring now healthy.

### 3. 🔴 CRITICAL: proton-bridge-hook crash loop — 5,893 restarts
- `proton-bridge-hook.service` (Restart=always, RestartSec=15) crashed on missing keyring password → restart counter 5893 → kept spawning secret-tool → keyring wedge.
- **Fixed**: stopped + disabled the service. The bridge itself (protonmail-bridge.service) still runs.
- **Root cause remains**: Proton Bridge has **no account loaded** ("no such user" on SMTP) — needs the user's Proton password to re-add. Email delivery (both report + hook) is degraded until then.

### 4. 🟠 HIGH: Daily security report email fails silently
- Report generated fine but email send fails: `no such user` (bridge has no account).
- **Fixed**: added **WhatsApp fallback** — when email fails, delivers via `openclaw message send --channel whatsapp --target +17163528536` (verified working end-to-end through systemd).
- Config: `~/.config/substrate/security_report.json` → `whatsapp: {enabled: true, target: "+17163528536"}`.

### 5. 🟠 HIGH: change-snapshot.service failing (exit 127)
- `uv` not on systemd user PATH (`/usr/local/bin:/usr/bin` only).
- **Fixed**: added `Environment=PATH=/home/ahron/.local/bin:...` to service. Now runs clean (rc=0).

### 6. 🟡 MEDIUM: system_monitor.sh false "disk I/O errors"
- The monitor's own WARNING lines matched its `grep -E 'I/O error|BTRFS'` pattern → self-amplifying count (75 "errors" growing every run, while kernel had **0** actual errors).
- **Fixed**: exclude own lines from the grep + tightened BTRFS pattern to `BTRFS.*(error|fail)`.

### 7. 🟡 MEDIUM: email-manager agent fails daily
- `No bridge password found in keyring` (credential locked/missing).
- **Fixed**: `_bridge_password()` now checks `PROTON_BRIDGE_PW` env → credentials file → keyring. Added missing `import os`.
- Still degrades gracefully until bridge account is re-added.

### 8. ✅ Verified healthy
- `restic-backup` — 03:00 daily, SUCCESS (last: Aug 17 03:00)
- `substrate-lister` — ok:true, all required services active
- `panel-monitor`, `system-monitor` — running clean
- Health check: **ALL PASSED** (after fixes)
- Test suite: 358 passed, 4 failed (pre-existing: crypto extra deps missing, openclaw module import — unrelated)

## Final state: 6 active timers
| Timer | Schedule | Status |
|---|---|---|
| substrate-agent-timer | every 5 min | ✅ enabled+running |
| daily-security-report | 06:30 daily | ✅ enabled+running (WhatsApp fallback) |
| system-monitor | every 15 min | ✅ |
| panel-monitor | every 2 min | ✅ |
| change-snapshot | every 10 min | ✅ (PATH fixed) |
| restic-backup | 03:00 daily | ✅ |

## Still needs user action (can't do without secrets)
- **Re-add Proton account to Bridge** (bridge CLI needs the Proton password): restores email sending + IMAP email-manager + proton-bridge-hook. Until then, WhatsApp covers daily report delivery.

## Commits
- `4c260854` fix(automation): daily report WhatsApp fallback, monitor self-match, email-manager credential fallback
- `ba8734c0` chore(automation): install script for daily report timer
- `65ad8a59` fix(automation): npm-global PATH in report service
