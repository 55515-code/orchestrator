#!/usr/bin/env bash
set -euo pipefail

MODE="emudeck"
ROOT="${HOME}/Emulation"
KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMS_FILE="${KIT_DIR}/config/systems.tsv"
APPLY=0
OPEN_LINKS=0
EXPECTED_HEADER=$'key\tdisplay_name\ttier\tdefault_collection\tstorage_hint\tbios_posture\tnotes'

usage() {
  cat <<'USAGE'
Steam Deck emulation console deployment prep

Usage:
  ./deck-emulation-console-deploy.sh [options]

Options:
  --apply                 Create folders and deployment notes.
  --dry-run               Print actions without changing files. Default.
  --mode emudeck          Prepare for EmuDeck + ES-DE. Default.
  --mode retrodeck        Prepare for RetroDECK appliance-style setup.
  --root PATH             Emulation root. Default: $HOME/Emulation
  --open-links            Open official project links in the browser.
  -h, --help              Show this help.

This script does not download ROMs, BIOS, firmware, keys, or emulator packages.
It prepares a clean local structure and writes the checklist needed to finish
the GUI steps on the Steam Deck.
USAGE
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

run() {
  if [[ "${APPLY}" -eq 1 ]]; then
    "$@"
  else
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
  fi
}

write_file() {
  local path="$1"
  local content="$2"
  if [[ "${APPLY}" -eq 1 ]]; then
    mkdir -p "$(dirname "${path}")"
    printf '%s\n' "${content}" >"${path}"
  else
    log "[dry-run] write ${path}"
  fi
}

require_systems_file() {
  [[ -f "${SYSTEMS_FILE}" ]] || die "systems file not found: ${SYSTEMS_FILE}"
}

validate_root() {
  [[ -n "${ROOT}" ]] || die "--root cannot be empty"
  [[ "${ROOT}" != "/" ]] || die "--root cannot be /"
  [[ "${ROOT}" != "/home" ]] || die "--root is too broad: ${ROOT}"
  [[ "${ROOT}" != "${HOME}" ]] || die "--root should be a dedicated folder, for example ${HOME}/Emulation"
}

validate_systems_file() {
  local header
  header="$(head -n 1 "${SYSTEMS_FILE}")"
  [[ "${header}" == "${EXPECTED_HEADER}" ]] || die "unexpected systems.tsv header"

  awk -F '\t' '
    NR == 1 { next }
    NF != 7 { printf("line %d has %d fields, expected 7\n", NR, NF); bad=1 }
    $1 !~ /^[a-z0-9][a-z0-9-]*$/ { printf("line %d has invalid key: %s\n", NR, $1); bad=1 }
    seen[$1]++ { printf("line %d has duplicate key: %s\n", NR, $1); bad=1 }
    $3 !~ /^(Excellent|Good|Mixed|Experimental|Excellent-Good|Good-Mixed|Mixed-Experimental)$/ { printf("line %d has unexpected tier: %s\n", NR, $3); bad=1 }
    $5 !~ /^(internal|microsd)$/ { printf("line %d has unexpected storage hint: %s\n", NR, $5); bad=1 }
    END {
      if (NR < 2) {
        print "systems.tsv has no systems"
        bad=1
      }
      exit bad
    }
  ' "${SYSTEMS_FILE}" || die "systems.tsv validation failed"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --apply)
        APPLY=1
        ;;
      --dry-run)
        APPLY=0
        ;;
      --mode)
        shift
        [[ $# -gt 0 ]] || die "--mode requires emudeck or retrodeck"
        MODE="$1"
        ;;
      --root)
        shift
        [[ $# -gt 0 ]] || die "--root requires a path"
        ROOT="$1"
        ;;
      --open-links)
        OPEN_LINKS=1
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        die "unknown option: $1"
        ;;
    esac
    shift
  done

  case "${MODE}" in
    emudeck | retrodeck) ;;
    *) die "--mode must be emudeck or retrodeck" ;;
  esac

  validate_root
}

preflight() {
  log "== Preflight =="
  log "Mode: ${MODE}"
  log "Target root: ${ROOT}"
  log "Apply changes: ${APPLY}"
  log "User: $(id -un 2>/dev/null || printf unknown)"
  log "Kernel: $(uname -srm 2>/dev/null || printf unknown)"

  if command -v flatpak >/dev/null 2>&1; then
    log "Flatpak: available"
  else
    log "Flatpak: not found; install EmuDeck/RetroDECK manually from Desktop Mode if needed"
  fi

  if command -v steamos-readonly >/dev/null 2>&1; then
    log "SteamOS readonly helper: available"
  else
    log "SteamOS readonly helper: not detected; this is fine during local non-Deck tests"
  fi
}

create_directories() {
  log "== Directories =="
  run mkdir -p "${ROOT}"
  run mkdir -p "${ROOT}/bios"
  run mkdir -p "${ROOT}/roms"
  run mkdir -p "${ROOT}/saves"
  run mkdir -p "${ROOT}/tools"
  run mkdir -p "${ROOT}/media"
  run mkdir -p "${ROOT}/backups"
  run mkdir -p "${ROOT}/docs"

  tail -n +2 "${SYSTEMS_FILE}" | while IFS=$'\t' read -r key _display _tier _collection _storage _bios _notes; do
    [[ -n "${key}" ]] || continue
    run mkdir -p "${ROOT}/roms/${key}"
  done
}

systems_markdown() {
  {
    printf '# Systems Manifest\n\n'
    printf 'Generated for %s mode. Keep experimental systems hidden until tested.\n\n' "${MODE}"
    printf '| Folder | System | Tier | Collection | Storage | BIOS/Firmware | Notes |\n'
    printf '| --- | --- | --- | --- | --- | --- | --- |\n'
    tail -n +2 "${SYSTEMS_FILE}" | while IFS=$'\t' read -r key display tier collection storage bios notes; do
      printf '| `%s` | %s | %s | %s | %s | %s | %s |\n' "${key}" "${display}" "${tier}" "${collection}" "${storage}" "${bios}" "${notes}"
    done
  }
}

deployment_notes() {
  cat <<NOTES
# Steam Deck ES-DE Console Deployment Checklist

Prepared: $(date -u '+%Y-%m-%d %H:%M:%S UTC')
Mode: ${MODE}
Emulation root: ${ROOT}

## One-Time Desktop Mode Steps

1. Update SteamOS from Gaming Mode, then reboot.
2. Copy this kit to the Deck and run:
   \`\`\`bash
   cd steamdeck-emulation-deploy
   EMULATION_ROOT="\$(cd ../.. && pwd)"
   ./deck-emulation-console-deploy.sh --apply --mode ${MODE} --root "\${EMULATION_ROOT}"
   \`\`\`
3. Install the chosen platform:
   - EmuDeck mode: install from https://www.emudeck.com/ and choose custom setup with ES-DE, Steam ROM Manager, RetroArch, standalone emulators, BIOS checker, compressor, and save tools.
   - RetroDECK mode: install RetroDECK from Flathub/Discover and use RetroDECK Configurator for BIOS checks and resets.
4. Put only owned games into \`${ROOT}/roms/<system>\`.
5. Put only owned/legally obtained BIOS or firmware files into the locations required by the chosen tool, then run its BIOS checker.
6. In Steam ROM Manager, enable only ES-DE, Emulators, and optional handpicked favorites. Do not parse the whole library into Steam.
7. Launch ES-DE, scrape metadata in batches, and manually audit Favorites.

## Console UI Defaults

- Main visible collections: Favorites, Recently Played, Arcade, Nintendo, Sega, Sony, Microsoft, Handhelds, Ports.
- Keep Experimental hidden until each title is tested.
- Use box art, screenshot/video snap, and logo/marquee consistently.
- Add individual Steam shortcuts only for 25-100 favorites or couch multiplayer showpieces.

## Final Acceptance Test

- ES-DE launches from Gaming Mode.
- Every visible system launches at least one game and exits back to ES-DE with controller only.
- Handheld and docked modes are readable.
- Sleep/resume, save/load, controller reconnect, and audio switching pass.
- The test log in \`docs/test-log.tsv\` has one representative entry per visible system.

## Safety Boundary

This kit never provides ROMs, BIOS files, firmware, keys, or DRM bypass steps.
NOTES
}

quickstart_notes() {
  cat <<NOTES
# Start Here

Run from Desktop Mode on the Steam Deck:

\`\`\`bash
cd steamdeck-emulation-deploy
EMULATION_ROOT="\$(cd ../.. && pwd)"
./deck-emulation-console-deploy.sh --apply --mode ${MODE} --root "\${EMULATION_ROOT}"
\`\`\`

Then follow \`../../docs/DEPLOYMENT-CHECKLIST.md\`.

Recommended path: EmuDeck + ES-DE as the main console interface, with Steam ROM Manager limited to ES-DE, Emulators, and handpicked favorites.

Do not add the full ROM library directly to Steam. Keep the complete library inside ES-DE.
NOTES
}

acceptance_notes() {
  cat <<'NOTES'
# Acceptance Checklist

Use this after EmuDeck or RetroDECK is installed and ES-DE can launch.

## Pass/Fail Gates

- [ ] ES-DE launches from Steam Gaming Mode.
- [ ] Built-in Deck controls can navigate ES-DE, launch a game, open emulator menu/hotkeys, and exit back to ES-DE.
- [ ] Every visible system has at least one tested game in `test-log.tsv`.
- [ ] Experimental systems are hidden unless each visible title has passed handheld and docked tests.
- [ ] Favorites are manually reviewed for artwork, metadata, launch behavior, and controller feel.
- [ ] Handheld mode is readable at 1280x800.
- [ ] Docked mode is readable at 1080p from couch distance.
- [ ] External controller disconnect/reconnect works after sleep/resume.
- [ ] Save/load and save-state behavior is confirmed for each emulator family.
- [ ] Steam ROM Manager exposes only ES-DE, Emulators, and intentional favorites.
- [ ] No ROM, BIOS, firmware, key, or bypass-source notes are stored in this kit.

## First Systems to Validate

NES, SNES, GBA, Genesis, PS1, N64, Dreamcast, PSP, GameCube/Wii, PS2, Arcade, Ports.

Keep PS3, Wii U, Xbox, Xbox 360, Vita, 3DS, and PS4-class experiments out of the polished view until individually proven.
NOTES
}

readiness_report() {
  local system_count
  system_count="$(tail -n +2 "${SYSTEMS_FILE}" | wc -l | tr -d ' ')"
  cat <<NOTES
# Readiness Report

Mode: ${MODE}
Root: ${ROOT}
Systems prepared: ${system_count}
Generated docs:
- DEPLOYMENT-CHECKLIST.md
- SYSTEMS-MANIFEST.md
- QUICKSTART.md
- READINESS-REPORT.md
- ACCEPTANCE.md
- test-log.tsv
- source-links.txt

Before calling the Deck complete, fill one test-log row for each visible system and confirm docked plus handheld acceptance tests pass.
NOTES
}

test_log_template() {
  cat <<'TEMPLATE'
date	system	game	emulator	mode	storage	resolution_or_scale	fps_or_pacing	battery_or_tdp	sleep_resume	controller	save_load	artwork	status	notes
TEMPLATE
}

write_outputs() {
  log "== Deployment files =="
  write_file "${ROOT}/docs/DEPLOYMENT-CHECKLIST.md" "$(deployment_notes)"
  write_file "${ROOT}/docs/SYSTEMS-MANIFEST.md" "$(systems_markdown)"
  write_file "${ROOT}/docs/QUICKSTART.md" "$(quickstart_notes)"
  write_file "${ROOT}/docs/READINESS-REPORT.md" "$(readiness_report)"
  write_file "${ROOT}/docs/ACCEPTANCE.md" "$(acceptance_notes)"
  write_file "${ROOT}/docs/test-log.tsv" "$(test_log_template)"
  write_file "${ROOT}/docs/source-links.txt" "EmuDeck https://www.emudeck.com/
EmuDeck Wiki https://emudeck.github.io/
ES-DE https://es-de.org/
RetroDECK https://retrodeck.net/
Decky Loader https://decky.xyz/
Steam ROM Manager https://steamgriddb.github.io/steam-rom-manager/
Valve Steam Deck specs https://www.steamdeck.com/en/tech"
}

open_links() {
  [[ "${OPEN_LINKS}" -eq 1 ]] || return 0
  if ! command -v xdg-open >/dev/null 2>&1; then
    log "xdg-open not found; skipping browser links"
    return 0
  fi
  case "${MODE}" in
    emudeck)
      run xdg-open "https://www.emudeck.com/"
      ;;
    retrodeck)
      run xdg-open "https://flathub.org/apps/net.retrodeck.retrodeck"
      ;;
  esac
  run xdg-open "https://es-de.org/"
}

main() {
  parse_args "$@"
  require_systems_file
  validate_systems_file
  preflight
  create_directories
  write_outputs
  open_links

  if [[ "${APPLY}" -eq 1 ]]; then
    log "Ready: ${ROOT}/docs/DEPLOYMENT-CHECKLIST.md"
  else
    log "Dry run complete. Re-run with --apply on the Steam Deck."
  fi
}

main "$@"
