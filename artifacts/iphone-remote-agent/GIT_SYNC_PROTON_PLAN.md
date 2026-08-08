# Git Sync Protection + Proton Integration — Plan

**Date:** 2026-08-07
**Stage:** local → hosted_dev
**Pass:** research → development → testing

---

## 1. Audit Findings

### Git safety gaps (critical)
| # | Finding | Risk |
|---|---|---|
| G1 | `.kilo/` (62 MB incl. 61 MB `node_modules`) is **NOT** in `.gitignore` | `git add -A` in auto-sync would commit it → 61 MB junk in public repo + agent config exposure |
| G2 | `ahrondarnell-site` has **no git remote** | Public site not backed up, not on GitHub |
| G3 | `auto_git_sync.sh` exists but is **not scheduled** (no timer, no cron) | Changes accumulate uncommitted |
| G4 | `auto_git_sync.sh` does blind `git add -A` | Sweeps secrets if `.gitignore` misses them |
| G5 | Global git identity **not set** (only per-repo) | New repos get bot identity or fail |
| G6 | LinkedIn screenshots (`linkedin-*.png`) in site workdir | Personal data could be committed |
| G7 | `dist/` build output in site workdir | Build artifacts shouldn't be tracked (already built) |

### Repo visibility (already correct)
- `orchestrator` → PUBLIC ✓
- `kilo-workspace` → PUBLIC ✓
- `LuigiOS` → PUBLIC ✓
- `open-provenance-knowledge` → PUBLIC ✓
- `ahrondarnell-site` → **does not exist on GitHub** → create PUBLIC (it's a public marketing site)

### Proton tooling available
| Service | Tool | Availability |
|---|---|---|
| Drive (storage) | `rclone v1.75.0` with `protondrive` backend | ✅ installed, backend built-in |
| Mail | `protonmail-bridge-core 3.25.0` (cachyos-extra-v3) | ✅ installable, provides localhost IMAP/SMTP |
| VPN | `proton-vpn-cli 1.0.1` (extra) | ✅ installable (official CLI) |

---

## 2. Implementation Plan

### A. Git safety (all user-level, no root)

1. **Add to `codespace/.gitignore`**: `.kilo/`, `dist/`, `linkedin-*.png`, `*.png` site screenshots
2. **Add to `ahrondarnell-site/.gitignore`**: `dist/`, `node_modules/`, `linkedin-*.png`, `.wrangler/`
3. **Harden `auto_git_sync.sh`**: replace blind `git add -A` with:
   - run a **secret scan** (grep for key patterns) on the staged diff
   - refuse to commit if secrets found
   - skip directories in a hardcoded blocklist even if gitignore fails
4. **Set global git identity**: `ahronzombi@gmail.com / Ahron Darnell`
5. **Create pre-sync secret scanner** `scripts/scan_secrets.sh` — reusable, run by timer + pre-commit
6. **Schedule sync**: systemd user timer `git-sync.timer` → runs `auto_git_sync.sh` every 30 min + on boot

### B. Repo provisioning (user-level + gh CLI already authed)

7. **Create `ahrondarnell-site` on GitHub as PUBLIC**, push `main`
8. Verify all 5 repos' visibility: 4 already public; site now public

### C. Proton integration (needs credentials — interactive, user action)

9. **Drive**: `rclone config` for protondrive backend → `rclone lsd protondrive:` smoke test
10. **Mail**: install `protonmail-bridge-core` → `protonmail-bridge --cli` login (interactive) → expose localhost IMAP :1143 / SMTP :1025 → config file
11. **VPN**: install `proton-vpn-cli` → `protonvpn-cli login` (interactive) → `protonvpn-cli status`
12. **Automation actions**: add `proton_drive_sync`, `proton_vpn_status`, `mail_status` to `actions.json` so they're callable from the iPhone panel

---

## 3. Security model

- **Public repos**: contain code only. No `.env`, no `.kilo/`, no screenshots, no `dist/`, no keys.
- **Secret scan**: blocks any commit containing `password=`, `token=`, `api_key=`, `BEGIN PRIVATE KEY`, etc.
- **Proton creds**: stored only in `~/.config/rclone/rclone.conf` (chmod 600), `~/.config/protonmail`, and keyring — never in git.
- **VPN/mail**: localhost-bound services, no inbound exposure.

## 4. Rollback
- gitignore changes: `git checkout -- .gitignore`
- timer: `systemctl --user disable --now git-sync.timer`
- Proton: `rclone config delete protondrive` / `pacman -Rns protonmail-bridge-core proton-vpn-cli`

## 5. Gates
- [ ] `.gitignore` coverage test: `git check-ignore .kilo/kilo.json` → path matches
- [ ] Secret scan test: scan a repo with a fake secret → refuses
- [ ] Timer fires: `systemctl --user list-timers` shows next run
- [ ] Site pushed: `gh repo view 55515-code/ahrondarnell-site` → PUBLIC
- [ ] rclone: `rclone lsd protondrive:` lists folders (after interactive login)
