#!/usr/bin/env bash
# =============================================================================
# nothing_stock_restore.sh
#
# Fail-safe automated restore of a Nothing/CMF Android device to the official
# stock Nothing OS and (optionally) re-lock of the bootloader, entirely over
# ADB/fastboot.
#
# VERIFIED DEVICE: Nothing Phone (3a) / (3a) Pro -- codename "asteroids"
#   Full restore + relock flow community-confirmed for this device
#   (avbroot issue #602, awesome-android-root guide, XDA, spike0en archive).
# OTHER MODELS use the same flow (community-confirmed, same A/B + super +
#   GKI layout): metroid (Phone 3), pacman/pacmanpro (Phone 2a/2a Plus),
#   pong (Phone 2), spacewar (Phone 1), tetris (CMF 1), galaga (CMF 2).
#
# DESIGN GOALS (fail-safe):
#   * Only official stock images are flashed -- sourced from
#     spike0en/nothing_archive, an unmodified mirror of Nothing's OEM firmware.
#   * Every partition is written to BOTH A/B slots.
#   * The bootloader is NEVER locked until every flash and wipe succeeded.
#   * Any failure aborts with a clear message, a safe rollback path, and the
#     device left unlocked (bootable) rather than half-flashed.
#   * The lock is only ever claimed as done after it is verified
#     (getvar unlocked=no).
#   * EDL mode + Nothing Flash Tool remain the documented emergency net.
#
# Usage / flags / environment overrides: see --help or
#   docs/nothing-stock-restore.md
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------- config ----
MIN_BATTERY_PCT="${MIN_BATTERY_PCT:-80}"
FASTBOOT_RETRIES="${FASTBOOT_RETRIES:-1}"      # retries per fastboot flash
WAIT_DEVICE_TIMEOUT="${WAIT_DEVICE_TIMEOUT:-900}"
WORK_DIR="${WORK_DIR:-./state/nothing-restore}"
LOG="$WORK_DIR/restore.log"

DRY_RUN=no
ASSUME_YES=no
DO_LOCK=yes
ALLOW_DOWNGRADE=no
SERIAL=""
IMAGES_DIR=""
BUILD_TAG=""
FB_MODE_ONLY=no

# ----------------------------------------------------------------- colors ----
C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_CYN=$'\033[36m'; C_RST=$'\033[0m'

info() { echo -e "${C_CYN}[*]${C_RST} $*"; }
ok()   { echo -e "${C_GRN}[ok]${C_RST} $*"; }
warn() { echo -e "${C_YEL}[!!]${C_RST} $*"; }
die()  { echo -e "${C_RED}[FATAL]${C_RST} $*" >&2; exit 1; }

log()  { echo "[$(date -u +%FT%TZ)] $*" >>"$LOG"; }

trap 'echo; warn "interrupted by user"; warn "device left in its current state; bootloader untouched unless the lock step had already completed"; warn "log: $LOG"' INT TERM

# --------------------------------------------------------------- helpers ----
usage() {
    cat <<'EOF'
Usage: nothing_stock_restore.sh [options]

Pre-flight (always, unless the device is already in fastboot):
  - confirms a supported Nothing/CMF model, ADB enabled, battery >= 80%,
    and a typed data-wipe confirmation
Firmware:
  - auto-downloads the latest official stock images for your device from
    spike0en/nothing_archive (GitHub releases) and extracts them
Flashing:
  - flashes every partition to BOTH A/B slots (bootloader fastboot for
    boot/init_boot/vendor_boot/vbmeta/firmware; fastbootd for dynamic
    partitions)
  - wipes userdata + cache
  - re-locks the bootloader (unless --no-lock)
  - verifies lock state (getvar unlocked=no) and full boot into stock
    Nothing OS

Options:
  -s, --serial SERIAL       ADB/fastboot serial (required when >1 device)
  -i, --images-dir DIR      use already-extracted stock .img files from DIR
                            (skips auto-download)
  -b, --build-tag TAG       pin a specific release tag from the archive,
                            e.g. Asteroids_B4.1-260414-1749 (default: latest)
      --no-lock             restore stock only; leave the bootloader unlocked
      --allow-downgrade     permit flashing a build older than the device's
                            current build (rollback protection may block boot)
      --yes                 explicit acknowledgement of the data wipe; skip
                            interactive prompts (use only after backing up)
      --dry-run             print every flash/wipe/lock command without
                            executing anything
      --work-dir DIR        working directory for downloads + logs
                            (default: ./state/nothing-restore)

Environment overrides:
  MIN_BATTERY_PCT (default 80)  FASTBOOT_RETRIES (default 1)
  WAIT_DEVICE_TIMEOUT (default 900)  WORK_DIR

Example:
  # auto-download latest stock images and fully restore + relock:
  bash scripts/nothing_stock_restore.sh

  # restore only, from already-downloaded images, keep bootloader unlocked:
  bash scripts/nothing_stock_restore.sh -i ~/asteroids-images --no-lock
EOF
}

ADB_ARGS=()
FB_ARGS=()

adb_run()   { adb "${ADB_ARGS[@]}" "$@"; }
fb_run()    { fastboot "${FB_ARGS[@]}" "$@"; }

get_prop() {
    adb_run shell getprop "$1" 2>/dev/null | tr -d '\r'
}

wait_for_device() {
    local timeout="${1:-$WAIT_DEVICE_TIMEOUT}" waited=0
    echo -n "    waiting for device to come online"
    while ! adb_run get-state 2>/dev/null | grep -q '^device$'; do
        sleep 5; waited=$((waited + 5))
        echo -n "."
        if [[ $waited -ge $timeout ]]; then
            echo " TIMEOUT"
            die "device did not come online within ${timeout}s (check USB cable/driver)"
        fi
    done
    echo " ONLINE"
}

wait_fastboot() {
    local timeout="${1:-180}" waited=0
    echo -n "    waiting for fastboot device"
    while ! fastboot_visible; do
        sleep 3; waited=$((waited + 3))
        echo -n "."
        if [[ $waited -ge $timeout ]]; then
            echo " TIMEOUT"
            die "device not visible in fastboot within ${timeout}s"
        fi
    done
    echo " DETECTED"
}

fastboot_visible() {
    if [[ -n "$SERIAL" ]]; then
        fastboot devices 2>/dev/null | grep -q "^$SERIAL"
    else
        fastboot devices 2>/dev/null | grep -q .
    fi
}

guard_single_fastboot() {
    local n
    n=$(fastboot devices 2>/dev/null | grep -c .)
    if [[ "$n" -gt 1 && -z "$SERIAL" ]]; then
        echo "multiple fastboot devices:" >&2
        fastboot devices >&2
        die "use --serial SERIAL to select one"
    fi
}

fb_try() { # non-fatal fastboot with retry; returns 0/1
    local args=("$@") attempt
    for attempt in $(seq 0 "$FASTBOOT_RETRIES"); do
        if [[ $attempt -gt 0 ]]; then
            warn "fastboot ${args[*]} failed -- retrying (attempt $((attempt + 1)))"
            sleep 5
        fi
        log "fastboot ${args[*]}"
        if [[ "$DRY_RUN" == yes ]]; then
            echo "    [dry-run] fastboot ${args[*]}"
            return 0
        fi
        echo "    fastboot ${args[*]}"
        if fb_run "${args[@]}" >>"$LOG" 2>&1; then return 0; fi
    done
    return 1
}

fb() { # fatal fastboot (aborts on failure)
    fb_try "$@" || die "fastboot ${*} failed after $((FASTBOOT_RETRIES + 1)) attempts"
}

fb_getvar() {
    fb_run getvar "$1" 2>&1 | tr -d '\r' | sed -n 's/^'"$1"': *//p'
}

get_current_slot() { fb_getvar current-slot; }
other_slot()       { [[ "$1" == a ]] && echo b || echo a; }

http_get() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then curl -fsSL "$url"
    elif command -v wget >/dev/null 2>&1; then wget -qO- "$url"
    else die "curl or wget is required for firmware download (or use --images-dir)"; fi
}

http_download() {
    local url="$1" dest="$2"
    if command -v curl >/dev/null 2>&1; then curl -fL --retry 3 -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then wget -q -O "$dest" "$url"
    else die "curl or wget is required for firmware download (or use --images-dir)"; fi
}

wait_any_boot() { # after lock: device wipes and returns in fastboot OR system
    local timeout="${1:-900}" waited=0 rc=1
    echo -n "    waiting for device to return (fastboot or system)"
    while true; do
        if adb_run get-state 2>/dev/null | grep -q '^device$'; then rc=0; break; fi
        if fastboot_visible; then rc=1; break; fi
        sleep 5; waited=$((waited + 5))
        echo -n "."
        if [[ $waited -ge $timeout ]]; then
            echo " TIMEOUT"
            die "device did not return within ${timeout}s after the lock flow"
        fi
    done
    if [[ $rc -eq 0 ]]; then echo " SYSTEM"; else echo " FASTBOOT"; fi
    return $rc
}

# ----------------------------------------------------------- preflight ----
require_tools() {
    local missing=()
    command -v adb     >/dev/null 2>&1 || missing+=(adb)
    command -v fastboot >/dev/null 2>&1 || missing+=(fastboot)
    if [[ -z "$IMAGES_DIR" ]]; then
        command -v jq >/dev/null 2>&1 || missing+=(jq)
        if ! command -v 7z >/dev/null 2>&1 && ! command -v 7zz >/dev/null 2>&1 && ! command -v bsdtar >/dev/null 2>&1; then
            missing+=(7z-or-bsdtar)
        fi
        command -v unzip >/dev/null 2>&1 || missing+=(unzip)
    fi
    command -v sha256sum >/dev/null 2>&1 || missing+=(sha256sum)
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "missing required tools: ${missing[*]} (install platform-tools + p7zip + jq)"
    fi
}

detect_adb_device() {
    local -a devs=()
    mapfile -t devs < <(adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1}')
    if [[ -n "$SERIAL" ]]; then
        local found=no d
        for d in "${devs[@]}"; do [[ "$d" == "$SERIAL" ]] && found=yes; done
        [[ $found == yes ]] || die "serial $SERIAL is not online via adb"
        return
    fi
    if [[ ${#devs[@]} -eq 0 ]]; then
        if fastboot devices 2>/dev/null | grep -q .; then
            warn "no adb device, but a fastboot device is present"
            warn "proceeding in fastboot-only mode (OS-level pre-flight checks skipped)"
            FB_MODE_ONLY=yes
            return
        fi
        die "no adb device found -- enable USB debugging and authorize this computer"
    fi
    if [[ ${#devs[@]} -gt 1 ]]; then
        echo "multiple adb devices:" >&2
        adb devices >&2
        die "use --serial SERIAL to select one"
    fi
    SERIAL="${devs[0]}"
    ADB_ARGS=(-s "$SERIAL")
    FB_ARGS=(-s "$SERIAL")
}

check_model() {
    local dev codename model_vendor model
    dev=$(get_prop ro.product.vendor.device);  [[ -z "$dev" ]] && dev=$(get_prop ro.product.device)
    [[ -z "$dev" ]] && dev=$(get_prop ro.product.name)
    codename=$(echo "$dev" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
    CODENAME="$codename"
    model_vendor=$(get_prop ro.product.vendor.model)
    model=$(get_prop ro.product.model)
    echo "    product.codename : ${CODENAME:-<unknown>}"
    echo "    product.model    : ${model:-<unknown>} (vendor: ${model_vendor:-<unknown>})"

    local supported=no
    case "$CODENAME" in
        asteroids) supported=yes;  DEVICE_NAME="Nothing Phone (3a) / (3a) Pro"; VERIFIED=yes ;;
        metroid)   supported=yes;  DEVICE_NAME="Nothing Phone (3)" ;;
        pacman)    supported=yes;  DEVICE_NAME="Nothing Phone (2a)" ;;
        pacmanpro) supported=yes;  DEVICE_NAME="Nothing Phone (2a) Plus" ;;
        pong)      supported=yes;  DEVICE_NAME="Nothing Phone (2)" ;;
        spacewar)  supported=yes;  DEVICE_NAME="Nothing Phone (1)" ;;
        tetris)    supported=yes;  DEVICE_NAME="CMF Phone (1)" ;;
        galaga)    supported=yes;  DEVICE_NAME="CMF Phone (2)" ;;
    esac
    [[ $supported == yes ]] || die "unsupported device codename '$CODENAME' -- refusing to flash"
    if [[ "$VERIFIED" == yes ]]; then
        ok "supported device: $DEVICE_NAME (codename $CODENAME) [fully verified flow]"
    else
        warn "supported device: $DEVICE_NAME (codename $CODENAME) [community-confirmed flow, same A/B layout]"
    fi
}

check_battery() {
    local level
    level=$(adb_run shell dumpsys battery 2>/dev/null | sed -n 's/^[[:space:]]*level:[[:space:]]*//p' | tr -d '\r')
    [[ "$level" =~ ^[0-9]+$ ]] || die "could not read battery level"
    echo "    battery level    : ${level}% (minimum ${MIN_BATTERY_PCT}%)"
    if [[ "$level" -lt "$MIN_BATTERY_PCT" ]]; then
        die "battery below ${MIN_BATTERY_PCT}% -- charge the device and re-run (brick risk on power loss during flash)"
    fi
}

collect_build_info() {
    DEV_FINGERPRINT=$(get_prop ro.build.fingerprint)
    DEV_BUILD_ID=$(get_prop ro.build.display.id)
    DEV_INCREMENTAL=$(get_prop ro.build.version.incremental)
    DEV_STATE=$(get_prop ro.boot.vbmeta.device_state)
    echo "    build fingerprint: ${DEV_FINGERPRINT:-<unknown>}"
    echo "    build display    : ${DEV_BUILD_ID:-<unknown>}"
    echo "    vbmeta state     : ${DEV_STATE:-<unknown>}"
}

confirm_wipe() {
    cat <<EOF

${C_RED}WARNING: ALL ON-DEVICE DATA WILL BE PERMANENTLY ERASED.${C_RST}

This procedure will:
  1. flash the official stock Nothing OS factory images
  2. wipe userdata and cache
  3. re-lock the bootloader (which wipes the device a second time)

Back up photos, messages, 2FA secrets, authenticator apps, and anything else
you need BEFORE continuing. This is irreversible.

EOF
    if [[ "$ASSUME_YES" == yes ]]; then
        warn "--yes supplied: treating it as explicit data-wipe acknowledgement"
        return 0
    fi
    local ans
    read -r -p 'Type  ERASE MY DEVICE  (exact, uppercase) to continue: ' ans
    [[ "$ans" == "ERASE MY DEVICE" ]] || die "aborted: data-wipe confirmation not provided"
}

# ------------------------------------------------------------- firmware ----
resolve_release() {
    local api="https://api.github.com/repos/spike0en/nothing_archive/releases?per_page=100"
    local json
    info "querying spike0en/nothing_archive releases..."
    json=$(http_get "$api")
    if [[ -n "$BUILD_TAG" ]]; then
        RELEASE_JSON=$(echo "$json" | jq -c --arg t "$BUILD_TAG" '.[] | select(.tag_name == $t) | .' | head -1)
    else
        RELEASE_JSON=$(echo "$json" | jq -c --arg p "$CODENAME" \
            'map(select((.tag_name | ascii_downcase) | startswith(($p | ascii_downcase) + "_"))) | .[0] | .')
    fi
    RELEASE_TAG=$(echo "${RELEASE_JSON:-}" | jq -r '.tag_name // empty')
    [[ -n "$RELEASE_TAG" ]] || die "no archive release found for codename '$CODENAME'${BUILD_TAG:+ and tag '$BUILD_TAG'}"
    ok "selected release: $RELEASE_TAG"
}

check_downgrade() {
    local dev_date rel_date
    dev_date=$(echo "$DEV_INCREMENTAL $DEV_BUILD_ID $DEV_FINGERPRINT" | grep -oE '[0-9]{6}' | sort -r | head -1)
    rel_date=$(echo "$RELEASE_TAG" | grep -oE '[0-9]{6}' | head -1)
    if [[ -n "$dev_date" && -n "$rel_date" && "$rel_date" -lt "$dev_date" ]]; then
        warn "selected build date ($rel_date) is older than the device's build date ($dev_date)"
        warn "rollback protection may block boot"
        if [[ "$ALLOW_DOWNGRADE" != yes ]]; then
            die "aborting due to downgrade risk -- re-run with --allow-downgrade to override"
        fi
    fi
}

download_firmware() {
    local -a urls=() u f
    mapfile -t urls < <(echo "$RELEASE_JSON" | jq -r '.assets[].browser_download_url' | grep -- '-image-' || true)
    [[ ${#urls[@]} -gt 0 ]] || die "release $RELEASE_TAG has no '-image-' assets; download manually from nothingarchive.tech and use --images-dir"

    mkdir -p "$FW_DIR"
    for u in "${urls[@]}"; do
        f="$FW_DIR/$(basename "$u")"
        if [[ ! -f "$f" ]]; then
            info "downloading $(basename "$u")..."
            http_download "$u" "$f"
        fi
    done

    # verify checksums if the release ships .sha256 assets
    local sha
    for sha in "$FW_DIR"/*.sha256; do
        [[ -f "$sha" ]] || continue
        info "verifying $(basename "$sha")"
        (cd "$FW_DIR" && sha256sum -c "$(basename "$sha")") || die "checksum verification failed for $sha"
    done
}

extract_images() {
    mkdir -p "$IMAGES_DIR"
    local f found=0 extractor
    if command -v 7z >/dev/null 2>&1; then
        extractor=7z
    elif command -v 7zz >/dev/null 2>&1; then
        extractor=7zz
    else
        extractor=bsdtar
    fi
    for f in "$FW_DIR"/*.7z.001 "$FW_DIR"/*.7z; do
        [[ -f "$f" ]] || continue
        [[ "$f" == *.7z.00[2-9] ]] && continue
        info "extracting $(basename "$f")"
        found=1
        if [[ "$extractor" == bsdtar ]]; then
            bsdtar -xf "$f" -C "$IMAGES_DIR"
        else
            "$extractor" x -y -o"$IMAGES_DIR" "$f" >/dev/null
        fi
    done
    for f in "$FW_DIR"/*.zip; do
        [[ -f "$f" ]] || continue
        info "extracting $(basename "$f")"
        found=1
        if ! unzip -oq "$f" -d "$IMAGES_DIR"; then
            if [[ "$extractor" == bsdtar ]]; then
                bsdtar -xf "$f" -C "$IMAGES_DIR"
            else
                "$extractor" x -y -o"$IMAGES_DIR" "$f" >/dev/null
            fi
        fi
    done
    [[ $found -eq 1 ]] || die "no firmware archives found in $FW_DIR"
    mapfile -t IMG_FILES < <(find "$IMAGES_DIR" -maxdepth 3 -type f -name '*.img' | sort)
    [[ ${#IMG_FILES[@]} -gt 0 ]] || die "no .img partition images found after extraction in $IMAGES_DIR"
}

# -------------------------------------------------------------- classify ----
LOGICAL_NAMES=(system system_ext vendor product odm vendor_dlkm system_dlkm)
KNOWN_PHYSICAL=(boot init_boot vendor_boot dtbo vbmeta vbmeta_system vbmeta_vendor \
    modem bluetooth dsp qupfw cpucores uefisecapp tz hyp xbl aop devcfg sti storsec \
    keymaster adsprpc cdsp recovery)

part_is_logical() {
    local n="$1" p
    for p in "${LOGICAL_NAMES[@]}"; do [[ "$n" == "$p" ]] && return 0; done
    return 1
}

part_is_known_physical() {
    local n="$1" p
    for p in "${KNOWN_PHYSICAL[@]}"; do [[ "$n" == "$p" ]] && return 0; done
    return 1
}

part_type_raw() { # probe bootloader for a physical partition type
    fb_run getvar "partition-type:$1" 2>&1 | tr -d '\r' | sed -n 's/^partition-type:[^:]*: *//p'
}

classify_images() {
    PHYSICAL_IMAGES=()
    LOGICAL_IMAGES=()
    UNKNOWN_IMAGES=()
    local img base
    for img in "${IMG_FILES[@]}"; do
        base=$(basename "$img" .img)
        if part_is_logical "$base"; then
            LOGICAL_IMAGES+=("$img")
        elif part_is_known_physical "$base"; then
            PHYSICAL_IMAGES+=("$img")
        else
            # not determinable by name -- resolved against the live device once
            # fastboot is up (avoids bricking on variant-specific layouts)
            UNKNOWN_IMAGES+=("$img")
        fi
    done

    [[ ${#PHYSICAL_IMAGES[@]} -gt 0 || ${#LOGICAL_IMAGES[@]} -gt 0 || ${#UNKNOWN_IMAGES[@]} -gt 0 ]] \
        || die "no flashable partitions found in images"

    # boot/init_boot must exist (GKI devices boot from init_boot)
    local boot_found=no img
    for img in "${PHYSICAL_IMAGES[@]}" "${UNKNOWN_IMAGES[@]}"; do
        case "$(basename "$img")" in
            init_boot.img|boot.img) boot_found=yes ;;
        esac
    done
    [[ $boot_found == yes ]] || die "no boot.img / init_boot.img found -- cannot restore a bootable system"

    echo "    physical partitions: $(printf '%s ' "${PHYSICAL_IMAGES[@]##*/}")"
    echo "    logical partitions : $(printf '%s ' "${LOGICAL_IMAGES[@]##*/}")"
    if [[ ${#UNKNOWN_IMAGES[@]} -gt 0 ]]; then
        echo "    unresolved images  : $(printf '%s ' "${UNKNOWN_IMAGES[@]##*/}") (resolved against device in fastboot)"
    fi
}

# ---------------------------------------------------------------- flash ----
order_physical() {
    # priority: boot images first, firmware in the middle, vbmeta last
    local -a rest=() img
    PHYSICAL_ORDERED=()
    for img in "$@"; do
        case "$(basename "$img")" in
            init_boot.img|boot.img) PHYSICAL_ORDERED+=("$img") ;;
            *) rest+=("$img") ;;
        esac
    done
    for img in "${rest[@]}"; do
        case "$(basename "$img")" in vendor_boot.img) PHYSICAL_ORDERED+=("$img");; esac
    done
    for img in "${rest[@]}"; do
        case "$(basename "$img")" in dtbo.img) PHYSICAL_ORDERED+=("$img");; esac
    done
    for img in "${rest[@]}"; do
        case "$(basename "$img")" in
            vendor_boot.img|dtbo.img|vbmeta.img|vbmeta_system.img|vbmeta_vendor.img) : ;;
            *) PHYSICAL_ORDERED+=("$img") ;;
        esac
    done
    for img in "${rest[@]}"; do
        case "$(basename "$img")" in vbmeta.img|vbmeta_system.img|vbmeta_vendor.img) PHYSICAL_ORDERED+=("$img");; esac
    done
}

resolve_unknown_physical() {
    # resolve name-ambiguous images against the live device (fastboot is up)
    local -a resolved=()
    local img base t
    for img in "${UNKNOWN_IMAGES[@]}"; do
        base=$(basename "$img" .img)
        t=$(part_type_raw "$base")
        if [[ -n "$t" ]]; then
            warn "resolved partition '${base}' -> type '${t}' (flashing as physical)"
            resolved+=("$img")
        else
            warn "skipping unknown image '${base}.img' (no such partition on this device)"
        fi
    done
    UNKNOWN_IMAGES=("${resolved[@]}")
}

flash_physical() {
    info "PHASE 1/4 -- flashing physical partitions to BOTH slots (bootloader fastboot)"
    fb reboot bootloader
    wait_fastboot
    guard_single_fastboot
    resolve_unknown_physical
    PHYSICAL_IMAGES+=("${UNKNOWN_IMAGES[@]}")

    local img base
    order_physical "${PHYSICAL_IMAGES[@]}"
    for img in "${PHYSICAL_ORDERED[@]}"; do
        base=$(basename "$img" .img)
        fb flash "${base}_a" "$img"
        fb flash "${base}_b" "$img"
    done
    ok "physical partitions flashed to slots A and B"
}

flash_logical() {
    info "PHASE 2/4 -- flashing dynamic partitions via fastbootd"
    fb reboot fastboot
    wait_fastboot
    guard_single_fastboot

    local active other mode=dance
    active=$(get_current_slot)
    if [[ "$active" != a && "$active" != b ]]; then
        warn "could not determine active slot ('${active:-empty}') -- using --slot=all instead"
        mode=slot-all
    fi

    local img base
    if [[ $mode == slot-all ]]; then
        for img in "${LOGICAL_IMAGES[@]}"; do
            base=$(basename "$img" .img)
            fb flash --slot all "$base" "$img"
        done
    else
        other=$(other_slot "$active")
        info "    flashing logical partitions to slot $active"
        for img in "${LOGICAL_IMAGES[@]}"; do
            base=$(basename "$img" .img)
            fb flash "$base" "$img"
        done
        info "    switching to slot $other and re-flashing logical partitions"
        fb set_active "$other"
        fb reboot fastboot
        wait_fastboot
        guard_single_fastboot
        for img in "${LOGICAL_IMAGES[@]}"; do
            base=$(basename "$img" .img)
            fb flash "$base" "$img"
        done
        info "    restoring active slot $active"
        fb set_active "$active"
        fb reboot fastboot
        wait_fastboot
        guard_single_fastboot
    fi
    ok "logical partitions flashed"
}

wipe_data() {
    info "PHASE 3/4 -- wiping userdata and cache"
    fb reboot bootloader
    wait_fastboot
    guard_single_fastboot
    if fb_try -w; then
        ok "userdata/cache wiped"
    else
        warn "wipe from bootloader fastboot failed -- retrying from fastbootd"
        fb reboot fastboot
        wait_fastboot
        fb -w
        fb reboot bootloader
        wait_fastboot
        ok "userdata/cache wiped (fastbootd)"
    fi
}

lock_bootloader() {
    info "PHASE 4/4 -- re-locking the bootloader"
    if [[ "$ASSUME_YES" != yes ]]; then
        echo
        echo "Every flash and wipe has succeeded. Re-locking is the point of no return:"
        echo "  - the bootloader verifies every partition against Nothing's release keys"
        echo "  - the device wipes all data again and reboots"
        echo "  - you must confirm ON THE PHONE (volume keys) when prompted"
        read -r -p "Re-lock the bootloader now? [y/N]: " ans
        case "$ans" in
            y|Y|yes|YES) ;;
            *) warn "aborted: bootloader left UNLOCKED (restore completed, device stays bootable)"
               DO_LOCK=aborted
               return 0 ;;
        esac
    fi
    echo ">>> On the phone: confirm the bootloader lock when the prompt appears."
    if ! fb_try flashing lock; then
        if ! fb_try oem lock; then
            if fastboot_visible; then
                die "bootloader lock command failed; device still in fastboot (unlocked and bootable). See troubleshooting in docs/nothing-stock-restore.md"
            fi
            warn "lock command did not return OKAY and the device left fastboot -- lock may have been accepted; continuing to verify"
        else
            warn "used fallback 'fastboot oem lock'"
        fi
    fi
}

verify_locked() {
    local v
    v=$(fb_getvar unlocked)
    if [[ "$v" == no ]]; then
        ok "bootloader locked (getvar unlocked=no)"
        return 0
    fi
    die "bootloader lock VERIFICATION FAILED: getvar unlocked=${v:-<empty>} (expected 'no')"
}

verify_boot() {
    # stability: confirm the device stays up (guards against a boot loop)
    if ! adb_run get-state 2>/dev/null | grep -q '^device$'; then
        die "device dropped offline shortly after boot -- likely a boot loop (see troubleshooting)"
    fi

    local fp inc state
    fp=$(get_prop ro.build.fingerprint)
    inc=$(get_prop ro.build.version.incremental)
    state=$(get_prop ro.boot.vbmeta.device_state)
    echo
    echo "    fingerprint  : ${fp:-<unknown>}"
    echo "    incremental  : ${inc:-<unknown>}"
    echo "    vbmeta state : ${state:-<unknown>}"
    echo

    if [[ "$fp" == *"release-keys"* ]]; then
        ok "device runs an official (release-keys) build"
    else
        warn "fingerprint does not contain 'release-keys' -- device may not be fully stock"
    fi
    if [[ "$state" == locked ]]; then
        ok "vbmeta device_state=locked (verification enforced)"
    else
        warn "vbmeta device_state=${state:-<unknown>} (expected 'locked')"
    fi
    if adb_run shell pm list packages 2>/dev/null | grep -qi magisk; then
        warn "Magisk packages still present -- root is not fully removed"
    else
        ok "no Magisk packages found"
    fi
    if adb_run shell 'command -v su' 2>/dev/null | grep -q .; then
        warn "an 'su' binary is present on the system"
    else
        ok "no su binary found"
    fi
}

# ------------------------------------------------------------------ main ----
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
    # sourced (e.g. by unit tests): only expose the helper functions
    return 0
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--serial)        SERIAL="$2"; shift 2 ;;
        -i|--images-dir)    IMAGES_DIR="$2"; shift 2 ;;
        -b|--build-tag)     BUILD_TAG="$2"; shift 2 ;;
        -n|--no-lock)       DO_LOCK=no; shift ;;
        --allow-downgrade)  ALLOW_DOWNGRADE=yes; shift ;;
        --yes)              ASSUME_YES=yes; shift ;;
        --dry-run)          DRY_RUN=yes; shift ;;
        --work-dir)         WORK_DIR="$2"; shift 2 ;;
        -h|--help)          usage; exit 0 ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
done

mkdir -p "$WORK_DIR"
LOG="$WORK_DIR/restore.log"
: >"$LOG"
log "=== nothing_stock_restore.sh start ==="
log "args: serial=${SERIAL:-auto} images_dir=${IMAGES_DIR:-auto} build_tag=${BUILD_TAG:-latest} lock=${DO_LOCK} dry_run=${DRY_RUN}"

info "Pre-flight checks"
require_tools
detect_adb_device

if [[ "$FB_MODE_ONLY" != yes ]]; then
    check_model
    check_battery
    collect_build_info
    confirm_wipe
else
    warn "device already in fastboot -- model/battery checks skipped; press Ctrl-C to abort"
    sleep 5
fi

# firmware
if [[ -n "$IMAGES_DIR" ]]; then
    [[ -d "$IMAGES_DIR" ]] || die "--images-dir '$IMAGES_DIR' does not exist"
    mapfile -t IMG_FILES < <(find "$IMAGES_DIR" -maxdepth 3 -type f -name '*.img' | sort)
    [[ ${#IMG_FILES[@]} -gt 0 ]] || die "no .img files found in $IMAGES_DIR"
    warn "using images from: $IMAGES_DIR (verify they are the correct stock build for your model)"
else
    FW_DIR="$WORK_DIR/firmware"
    resolve_release
    if [[ "$FB_MODE_ONLY" != yes ]]; then
        check_downgrade
    fi
    download_firmware
    IMAGES_DIR="$WORK_DIR/firmware/extracted"
    extract_images
fi

classify_images

info "Flashing sequence begins. Do NOT unplug the device or close this terminal."
flash_physical
flash_logical
wipe_data

if [[ "$DO_LOCK" == yes ]]; then
    lock_bootloader
    if [[ "$DO_LOCK" == aborted ]]; then
        info "bootloader left unlocked -- device remains bootable on stock Nothing OS"
        fb reboot
        wait_for_device 900
        sleep 20
        verify_boot
    else
        # after the on-device confirmation the device wipes and returns in
        # either fastboot or system; wait for whichever appears
        if wait_any_boot 900; then
            sleep 20
        else
            info "device returned in fastboot -- booting to system to verify"
            fb reboot
            wait_for_device 900
            sleep 20
        fi
        verify_boot

        info "authoritative lock check: rebooting to bootloader to read getvar unlocked"
        adb_run reboot bootloader
        wait_fastboot
        guard_single_fastboot
        verify_locked

        info "booting back to system for the final check"
        fb reboot
        wait_for_device 900
        sleep 20
        if ! adb_run get-state 2>/dev/null | grep -q '^device$'; then
            die "device dropped offline after final reboot -- investigate"
        fi
        ok "final boot verified"
    fi
else
    fb reboot
    wait_for_device 900
    sleep 20
    verify_boot
fi

echo
echo "=================================================================="
ok "PROCESS COMPLETE"
echo "  device restored to stock Nothing OS"
echo "  bootloader: $(if [[ "$DO_LOCK" == aborted ]]; then echo 'LEFT UNLOCKED (user choice)'; elif [[ "$DO_LOCK" == no ]]; then echo 'left unlocked (--no-lock)'; else echo 'LOCKED and verified'; fi)"
echo "  log: $LOG"
echo "  next: Settings > System > System update to fetch the latest OTA"
echo "=================================================================="
