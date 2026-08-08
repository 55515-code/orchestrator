# System Reproducibility + Proton AI Integration — Plan

**Date:** 2026-08-07
**Stage:** local → hosted_dev
**Pass:** research → development → testing

---

## 1. Research Findings

### Reproducibility (dotfiles as code)
| Tool | Verdict | Why |
|---|---|---|
| **chezmoi** 2.72.0 (extra, 39.9 MB) | **CHOSEN** | Single static binary, Go templates per-machine, age/gpg/1Password secret encryption, `chezmoi apply` rebuilds a machine from a git repo in one command, `chezmoi diff`/dry-run, cross-platform (Linux/macOS/Windows). Matches the substrate's existing `config_sync_profiles.yaml` which already cites chezmoi as a source. |
| yadm | rejected | Bash wrapper, no password-manager integration |
| GNU Stow | rejected | No templating, no secrets, symlink-only |
| bare git | rejected | No templating, no secret handling |
| Nix Home Manager | rejected | Workflow shift, Nix-specific |

### Backups (snapshots, decentralized)
| Tool | Verdict | Why |
|---|---|---|
| **restic** 0.19.1 (cachyos-extra-v3, 41 MB) | **CHOSEN** | Encrypted, deduplicated, incremental snapshots. `restic backup ~` excludes via `.gitignore`-style ignore files; `restic restore latest` rebuilds. |
| **rclone → Proton Drive** | **CHOSEN** (backend) | restic's repo lives on Proton Drive via rclone's `proton:` remote — encrypted offsite + E2EE in Proton. |
| Syncthing | optional | Device-to-device live sync; add later if multi-device. |

### Proton AI
| Capability | Status |
|---|---|
| **Proton Scribe** (writing assistant) | Built into Proton Mail composer. **No public API** — cannot be called programmatically. GPL-3.0, Mistral 7B base, runs locally via WebGPU. |
| **Realistic integration** | 1) Use Scribe inside Proton Mail (user-level). 2) **Local Scribe-style action** using existing Ollama (llama3.1:8b already installed) — draft/proofread/shorten emails via `proton_ai_scribe` action in the panel, privacy-preserving (all local). |

---

## 2. Implementation Plan

### A. Install (sudo, one batch)
```bash
sudo pacman -S --noconfirm chezmoi restic age
```

### B. chezmoi dotfiles repo (user-level)
1. `chezmoi init` → creates `~/.local/share/chezmoi`
2. Add tracked files:
   - `~/.bashrc`, `~/.bash_profile`
   - `~/.gitconfig` (via template, no secrets)
   - `~/.config/kilo/kilo.jsonc`
   - `~/.ssh/config` (never private keys)
   - `~/.npmrc` (contains registry token → **age-encrypt**)
   - `~/.config/rclone/rclone.conf` (contains Proton creds → **age-encrypt**)
3. Create `dotfiles` GitHub repo (private — contains encrypted files, but safer private)
4. `chezmoi apply` on any new machine rebuilds everything

### C. restic backup (user-level)
1. `restic init --repo rclone:proton:restic` (repo on Proton Drive)
2. `~/.config/restic/ignore` — large dirs: `node_modules/`, `.venv/`, `dist/`, `work/`, `aosp-eos-asteroids/`, `state/`, `memory/`, `.git/`, `.kilo/node_modules/`
3. Script `scripts/backup_snapshot.sh`:
   - `restic backup ~ --exclude-file=...` → Proton Drive
   - `restic forget --keep-daily 7 --keep-weekly 4 --prune`
4. systemd user timer `restic-backup.timer` — daily 03:00

### D. Proton AI action (user-level)
- Add `proton_ai_scribe` action → calls Ollama `llama3.1:8b` with a Scribe-style system prompt (draft/proofread/shorten/formalize email text)

### E. Actions + panel wiring
- Add to `actions.json`: `dotfiles_status`, `dotfiles_apply`, `snapshot_backup`, `snapshot_restore_list`, `proton_ai_scribe`, `proton_ai_proofread`

---

## 3. Security model
- **Private dotfiles repo** (contains encrypted + config files, no plaintext secrets)
- age-encrypted: `.npmrc`, `rclone.conf`, any `.ssh` private keys
- restic repo encrypted (repo password) + Proton Drive E2EE
- No secrets in the public orchestrator repo

## 4. Rollback
- `pacman -Rns chezmoi restic age`
- `rm -rf ~/.local/share/chezmoi`
- delete restic repo on Proton Drive
