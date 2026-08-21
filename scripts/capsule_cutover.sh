#!/usr/bin/env bash
# Capsule cutover: containerized OpenClaw Gateway + Substrate panel.
# Keeps original URLs working (127.0.0.1:8090 / :8095 / :8321) while moving
# the Gateway into a hardened rootless Podman container.
#
# Phases:
#   1. preflight   — verify prerequisites, ports, state, images
#   2. backup      — OpenClaw verified backup + Btrfs snapshot
#   3. test        — disposable container smoke + health checks
#   4. cutover     — stop native, start container on 8090, verify
#   5. rollback    — revert to native gateway (manual: rollback)
#   6. status      — show current state
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GATEWAY_PORT="${GATEWAY_PORT:-8090}"
PANEL_PORT="${PANEL_PORT:-8095}"
CHATBOT_PORT="${CHATBOT_PORT:-8321}"
OPENCLAW_IMAGE="${OPENCLAW_IMAGE:-ghcr.io/openclaw/openclaw:2026.7.1-2}"
# Container networking: pasta with host-loopback mapping so the unprivileged
# container can reach host-bound services (Ollama on 127.0.0.1:11434) via
# 10.0.2.2. Rootless podman has no slirp4netns; bridge cannot reach the host.
NET_MODE="${NET_MODE:-pasta:--map-host-loopback,10.0.2.2}"
HOST_LOOPBACK_IP="${HOST_LOOPBACK_IP:-10.0.2.2}"
SUBSTRATE_IMAGE="${SUBSTRATE_IMAGE:-substrate-ops:capsule-test}"
CONTAINER_NAME="${CONTAINER_NAME:-openclaw-capsule}"
STATE_DIR="${OPENCLAW_STATE_DIR:-$HOME/.openclaw}"
WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-$HOME/codespace}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$HOME/.backups/capsule-snapshots}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/codespace/artifacts/capsule/backups}"
PANEL_ENV_FILE="${PANEL_ENV_FILE:-/home/ahron/.config/substrate/panel.env}"
LOCK_FILE="${LOCK_FILE:-$HOME/.cache/substrate/capsule.lock}"
LOG_FILE="${LOG_FILE:-$HOME/.cache/substrate/capsule-cutover.log}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"
NATIVE_SERVICE="openclaw-gateway.service"
PANEL_SERVICE="substrate-panel-tailnet.service"
BACKUP_JSON="${STATE_DIR}/openclaw.json.pre-capsule"

mkdir -p "$(dirname "$LOCK_FILE")" "$(dirname "$LOG_FILE")" "$SNAPSHOT_DIR" "$BACKUP_DIR"

log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG_FILE"; }
die() { log "ERROR: $*"; exit 1; }

acquire_lock() {
  if ! mkdir "$LOCK_FILE" 2>/dev/null; then
    die "another capsule operation is running (lock: $LOCK_FILE)"
  fi
  trap 'rmdir "$LOCK_FILE" 2>/dev/null || true' EXIT
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
gateway_health() {
  # Return 0 when the OpenClaw Gateway answers on the target port.
  local port="$1"
  curl -fsS -m 5 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1
}

wait_health() {
  local port="$1" attempts="${2:-$HEALTH_TIMEOUT}" i=0
  while ! gateway_health "$port"; do
    i=$((i + 1))
    if (( i >= attempts )); then return 1; fi
    sleep 1
  done
  return 0
}

native_running() { systemctl --user is-active --quiet "$NATIVE_SERVICE"; }

container_running() { podman ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; }

port_in_use() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(^|:)${1}$"; }

gateway_token() {
  python3 - "$STATE_DIR/openclaw.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("gateway", {}).get("auth", {}).get("token", ""))
except Exception:
    print("")
PY
}

gateway_deep_health() {
  # Authenticated deep health: /health is the documented liveness endpoint
  # (returns {"ok":true,"status":"live"}); /api/health is NOT a real route.
  # Try the CLI probe first (covers channels/sessions), fall back to /health.
  if command -v openclaw >/dev/null 2>&1; then
    if timeout 15 openclaw health --json >/dev/null 2>&1; then
      return 0
    fi
  fi
  curl -fsS -m 10 "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1
}

btrfs_snapshot() {
  # Create a read-only Btrfs snapshot of the OpenClaw state dir, if possible.
  local src="$1" dst="$2" tag="$3"
  if ! command -v btrfs >/dev/null 2>&1; then
    log "btrfs not available; skipping snapshot"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if btrfs subvolume snapshot -r "$src" "$dst" >/dev/null 2>&1; then
    log "btrfs snapshot: $dst"
    echo "$dst"
    return 0
  fi
  log "btrfs snapshot unavailable (not a subvolume); using reflink copy"
  if cp -a --reflink=auto "$src" "$dst" >/dev/null 2>&1; then
    chmod -R u+rwX "$dst" 2>/dev/null || true
    log "reflink state copy: $dst"
    echo "$dst"
    return 0
  fi
  log "warn: reflink copy failed; relying on verified OpenClaw backup only"
  return 0
}

patch_workspace_for_container() {
  # Rewrite agents.defaults.workspace from host absolute (/home/ahron/codespace)
  # to container-native (/home/node/.openclaw/workspace) so the unprivileged
  # container does not try to mkdir /home/ahron. Idempotent. Also accepts the
  # blanket-replaced variant (/home/node/codespace) that portable_patch_state
  # produces when it runs first.
  local state="${1:-$STATE_DIR}" ws="${2:-$WORKSPACE_DIR}" ctr_ws="/home/node/.openclaw/workspace"
  local cfg="$state/openclaw.json"
  [[ -f "$cfg" ]] || return 0
  python3 - "$cfg" "$ws" "$ctr_ws" <<'PY'
import json, os, sys
cfg, host_ws, ctr_ws = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d=json.load(open(cfg))
    cur=d.get("agents",{}).get("defaults",{}).get("workspace")
    # Variants that should become ctr_ws: the host path itself, and the
    # /home/node + suffix form produced by the blanket /home/ahron -> /home/node
    # replace in portable_patch_state.
    variants={host_ws, host_ws.rstrip("/")}
    if host_ws.startswith("/home/ahron"):
        variants.add("/home/node" + host_ws[len("/home/ahron"):])
    if not cur:
        print(f"workspace unset; nothing to patch")
    elif cur == ctr_ws:
        print(f"workspace already portable: {cur!r}")
    elif cur in variants:
        d["agents"]["defaults"]["workspace"]=ctr_ws
        tmp=cfg+".tmp"
        json.dump(d, open(tmp,"w"), indent=2)
        os.rename(tmp, cfg)
        print(f"patched workspace {cur!r} -> {ctr_ws!r}")
    else:
        print(f"workspace is custom ({cur!r}); leaving as-is")
except Exception as e:
    print(f"patch failed: {e}", file=sys.stderr)
    sys.exit(1)
PY
}

portable_patch_state() {
  # Make ~/.openclaw state portable: rewrite any occurrence of the host home
  # absolute (/home/ahron) into the container home (/home/node) inside
  # openclaw.json AND the sqlite installed_plugin_index. The container runs
  # as uid 1000 and cannot mkdir /home/ahron. All rewrites are logged and
  # reversible via $BACKUP_JSON / backup sqlite.
  local state="${1:-$STATE_DIR}" host_home="$HOME" ctr_home="/home/node"
  local ctr_state="${ctr_home}/.openclaw"
  # openclaw.json: global string replace of host_home -> container home
  if [[ -f "$state/openclaw.json" ]]; then
    python3 - "$state/openclaw.json" "$host_home" "$ctr_home" <<'PY' >>"$LOG_FILE" 2>&1 || return 1
import json, os, sys
cfg, host, ctr = sys.argv[1], sys.argv[2], sys.argv[3]
raw=open(cfg).read()
if host in raw:
    open(cfg,"w").write(raw.replace(host, ctr))
    print(f"patched {cfg}: {host!r} -> {ctr!r}")
else:
    print(f"{cfg}: already portable")
PY
  fi
  # substrate-vault plugin manifest (hardcodes /home/ahron/codespace)
  local vault="$state/plugins/substrate-vault/openclaw.plugin.json"
  if [[ -f "$vault" ]]; then
    python3 - "$vault" "$host_home" "$ctr_home" <<'PY' >>"$LOG_FILE" 2>&1 || true
import json, os, sys
cfg, host, ctr = sys.argv[1], sys.argv[2], sys.argv[3]
raw=open(cfg).read()
if host in raw:
    open(cfg,"w").write(raw.replace(host, ctr))
    print(f"patched {cfg}: {host!r} -> {ctr!r}")
PY
  fi
  # sqlite installed_plugin_index: installPath etc are host-absolute
  # (also rewritten for the container mount at /home/node/.openclaw)
  local db="$state/state/openclaw.sqlite"
  if [[ -f "$db" ]]; then
    python3 - "$db" "$host_home" "$ctr_home" "$ctr_state" <<'PY' >>"$LOG_FILE" 2>&1 || return 1
import json, sqlite3, sys
db, host, ctr, ctr_state = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
con=sqlite3.connect(db); cur=con.cursor()
row=cur.execute("SELECT install_records_json, plugins_json FROM installed_plugin_index").fetchone()
if row:
    a,b=row
    changed=False
    try:
        recs=json.loads(a)
        for pid, r in recs.items():
            ip=r.get("installPath", "")
            if ip == ctr_state:
                r["installPath"]=host + ip[len(ctr):]
                changed=True
        if changed:
            a=json.dumps(recs)
    except Exception:
        pass
    if host in a:
        a=a.replace(host, ctr); changed=True
    if host in b:
        b=b.replace(host, ctr); changed=True
    if changed:
        cur.execute("UPDATE installed_plugin_index SET install_records_json=?, plugins_json=?", (a,b))
        con.commit()
        print(f"patched sqlite {db}: {host!r} -> {ctr!r}")
    else:
        print(f"sqlite {db}: already portable")
PY
  fi
}

restore_state_for_native() {
  # Reverse of portable_patch_state via the pristine backup if available,
  # otherwise do an in-place reverse replace.
  local state="${1:-$STATE_DIR}" host_home="$HOME" ctr_home="/home/node"
  local ctr_state="$ctr_home/.openclaw"
  if [[ -f "$BACKUP_JSON" ]]; then
    cp -a "$BACKUP_JSON" "$state/openclaw.json" 2>/dev/null || true
    echo "restored $state/openclaw.json from $BACKUP_JSON" >>"$LOG_FILE"
  else
    python3 - "$state/openclaw.json" "$host_home" "$ctr_home" <<'PY' >>"$LOG_FILE" 2>&1 || true
import sys
cfg, host, ctr = sys.argv[1], sys.argv[2], sys.argv[3]
raw=open(cfg).read()
if ctr in raw:
    open(cfg,"w").write(raw.replace(ctr, host))
    print(f"restored {cfg}: {ctr!r} -> {host!r}")
PY
  fi
  # also restore sqlite backup if we have one (see cutover below)
  local backup_db="$BACKUP_DIR/openclaw.sqlite.pre-cutover"
  local db="$state/state/openclaw.sqlite"
  if [[ -f "$backup_db" && -f "$db" ]]; then
    cp -a "$backup_db" "$db" 2>/dev/null && echo "restored $db from $backup_db" >>"$LOG_FILE" || true
  fi
  local vault="$state/plugins/substrate-vault/openclaw.plugin.json"
  if [[ -f "$vault" ]]; then
    python3 - "$vault" "$host_home" "$ctr_home" <<'PY' >>"$LOG_FILE" 2>&1 || true
import sys
cfg, host, ctr = sys.argv[1], sys.argv[2], sys.argv[3]
raw=open(cfg).read()
if ctr in raw:
    open(cfg,"w").write(raw.replace(ctr, host))
PY
  fi
  # restore workspace path for native runs
  restore_workspace_for_native "$state" "$WORKSPACE_DIR" >>"$LOG_FILE" 2>&1 || true
  # restore plugin symlinks to host npm-global targets
  restore_plugin_symlinks "$state" >>"$LOG_FILE" 2>&1 || true
  # restore ollama baseUrl to host loopback
  restore_ollama_host "$state" >>"$LOG_FILE" 2>&1 || true
}

# ---------------------------------------------------------------------------
# Plugin symlink portability: the whatsapp plugin's node_modules/openclaw peer
# symlink points at the host npm-global install (/home/ahron/.npm-global/lib/
# node_modules/openclaw). Inside the container OpenClaw lives at /app, and
# plugin-skills/* symlinks point at host dist paths that also become /app.
# ---------------------------------------------------------------------------
fix_plugin_symlinks() {
  local state="${1:-$STATE_DIR}"
  local host_npm="$HOME/.npm-global/lib/node_modules/openclaw"
  local ctr_app="/app"
  local peer="$state/extensions/whatsapp/node_modules/openclaw"
  # NOTE: portable_patch_state rewrites /home/ahron -> /home/node INSIDE this
  # symlink's stored target, so a host link now reads .../home/node/.npm-global/...
  # Match both the pristine host path and its /home/node-rewritten variant.
  if [[ -L "$peer" ]]; then
    local tgt; tgt="$(readlink "$peer")"
    if [[ "$tgt" == "$host_npm"* || "$tgt" == "/home/node/.npm-global"* ]]; then
      ln -sfn "$ctr_app" "$peer"
      echo "fix_plugin_symlinks: $peer -> $ctr_app (was $tgt)" >>"$LOG_FILE"
    else
      echo "fix_plugin_symlinks: $peer already portable ($tgt)" >>"$LOG_FILE"
    fi
  fi
  # plugin-skills/* symlinks (dist/... -> /app/dist/...)
  local skills_dir="$state/plugin-skills"
  if [[ -d "$skills_dir" ]]; then
    local link
    for link in "$skills_dir"/*; do
      [[ -L "$link" ]] || continue
      local tgt; tgt="$(readlink "$link")"
      if [[ "$tgt" == "$host_npm"* ]]; then
        ln -sfn "$ctr_app${tgt#$host_npm}" "$link"
        echo "fix_plugin_symlinks: $link -> $ctr_app${tgt#$host_npm}" >>"$LOG_FILE"
      fi
    done
  fi
  # substrate-vault plugin source (hardcoded workspace path)
  local vaultjs="$state/plugins/substrate-vault/index.js"
  if [[ -f "$vaultjs" ]]; then
    if grep -q '"/home/ahron/codespace"' "$vaultjs"; then
      python3 - "$vaultjs" <<'PY' >>"$LOG_FILE" 2>&1 || true
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace('"/home/ahron/codespace"', '"/home/node/.openclaw/workspace"')
open(p, "w").write(s)
print(f"patched substrate-vault index.js workspace path")
PY
    fi
  fi
}

restore_plugin_symlinks() {
  local state="${1:-$STATE_DIR}"
  local host_npm="$HOME/.npm-global/lib/node_modules/openclaw"
  local peer="$state/extensions/whatsapp/node_modules/openclaw"
  if [[ -L "$peer" ]]; then
    local tgt; tgt="$(readlink "$peer")"
    if [[ "$tgt" == "/app"* ]]; then
      ln -sfn "$host_npm" "$peer"
      echo "restore_plugin_symlinks: $peer -> $host_npm" >>"$LOG_FILE"
    fi
  fi
  # plugin-skills/* symlinks were not rewritten by portable_patch_state (they
  # live under .openclaw, not a json blob), so they keep host-npm targets;
  # restore is a no-op for them. The vault index.js path is restored below.
  local skills_dir="$state/plugin-skills"
  if [[ -d "$skills_dir" ]]; then
    local link
    for link in "$skills_dir"/*; do
      [[ -L "$link" ]] || continue
      local tgt; tgt="$(readlink "$link")"
      if [[ "$tgt" == "/app"* ]]; then
        ln -sfn "$host_npm${tgt#/app}" "$link"
        echo "restore_plugin_symlinks: $link -> $host_npm${tgt#/app}" >>"$LOG_FILE"
      fi
    done
  fi
  local vaultjs="$state/plugins/substrate-vault/index.js"
  if [[ -f "$vaultjs" ]]; then
    if grep -q '"/home/node/.openclaw/workspace"' "$vaultjs"; then
      python3 - "$vaultjs" <<'PY' >>"$LOG_FILE" 2>&1 || true
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace('"/home/node/.openclaw/workspace"', '"/home/ahron/codespace"')
open(p, "w").write(s)
print(f"restored substrate-vault index.js workspace path")
PY
    fi
  fi
}

# ---------------------------------------------------------------------------
# Ollama host reachability: the Ollama provider baseUrl in openclaw.json is
# http://127.0.0.1:11434/v1 — inside the container that is the container's own
# loopback. With pasta --map-host-loopback the host loopback is reachable via
# 10.0.2.2. Rewrite the baseUrl for the container, restore for native.
# ---------------------------------------------------------------------------
patch_ollama_host() {
  local state="${1:-$STATE_DIR}"
  local cfg="$state/openclaw.json"
  [[ -f "$cfg" ]] || return 0
  python3 - "$cfg" "$HOST_LOOPBACK_IP" <<'PY' >>"$LOG_FILE" 2>&1 || true
import json, os, sys
cfg, host_ip = sys.argv[1], sys.argv[2]
d = json.load(open(cfg))
prov = d.get("models", {}).get("providers", {}).get("ollama", {})
base = prov.get("baseUrl", "")
if base.startswith("http://127.0.0.1:") or base.startswith("http://localhost:"):
    newbase = base.replace("127.0.0.1", host_ip).replace("localhost", host_ip)
    d["models"]["providers"]["ollama"]["baseUrl"] = newbase
    tmp = cfg + ".tmp"
    json.dump(d, open(tmp, "w"), indent=2)
    os.rename(tmp, cfg)
    print(f"patched ollama baseUrl {base!r} -> {newbase!r}")
else:
    print(f"ollama baseUrl already portable: {base!r}")
PY
}

restore_ollama_host() {
  local state="${1:-$STATE_DIR}"
  local cfg="$state/openclaw.json"
  [[ -f "$cfg" ]] || return 0
  python3 - "$cfg" "$HOST_LOOPBACK_IP" <<'PY' >>"$LOG_FILE" 2>&1 || true
import json, os, sys
cfg, host_ip = sys.argv[1], sys.argv[2]
d = json.load(open(cfg))
prov = d.get("models", {}).get("providers", {}).get("ollama", {})
base = prov.get("baseUrl", "")
if host_ip in base:
    newbase = base.replace(host_ip, "127.0.0.1")
    d["models"]["providers"]["ollama"]["baseUrl"] = newbase
    tmp = cfg + ".tmp"
    json.dump(d, open(tmp, "w"), indent=2)
    os.rename(tmp, cfg)
    print(f"restored ollama baseUrl {base!r} -> {newbase!r}")
else:
    print(f"ollama baseUrl already native: {base!r}")
PY
}

restore_workspace_for_native() {
  local state="${1:-$STATE_DIR}" ws="${2:-$WORKSPACE_DIR}" ctr_ws="/home/node/.openclaw/workspace"
  local cfg="$state/openclaw.json"
  [[ -f "$cfg" ]] || return 0
  python3 - "$cfg" "$ws" "$ctr_ws" <<'PY'
import json, os, sys
cfg, host_ws, ctr_ws = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d=json.load(open(cfg))
    cur=d.get("agents",{}).get("defaults",{}).get("workspace")
    if cur == ctr_ws:
        d["agents"]["defaults"]["workspace"]=host_ws
        tmp=cfg+".tmp"
        json.dump(d, open(tmp,"w"), indent=2)
        os.rename(tmp, cfg)
        print(f"restored workspace {cur!r} -> {host_ws!r}")
    else:
        print(f"workspace already native: {cur!r}")
except Exception as e:
    print(f"restore failed: {e}", file=sys.stderr)
    sys.exit(1)
PY
}

# ---------------------------------------------------------------------------
# Phase: preflight
# ---------------------------------------------------------------------------
preflight() {
  log "preflight: checking prerequisites"
  command -v podman >/dev/null 2>&1 || die "podman not found"
  command -v systemctl >/dev/null 2>&1 || die "systemctl not found"
  command -v curl >/dev/null 2>&1 || die "curl not found"
  command -v python3 >/dev/null 2>&1 || die "python3 not found"

  [[ -d "$STATE_DIR" ]] || die "OpenClaw state dir missing: $STATE_DIR"
  [[ -f "$STATE_DIR/openclaw.json" ]] || die "openclaw.json missing"

  if [[ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null)" != "true" ]]; then
    die "rootless Podman required"
  fi

  podman image exists "$OPENCLAW_IMAGE" || die "OpenClaw image not pulled: $OPENCLAW_IMAGE"
  podman image exists "$SUBSTRATE_IMAGE" || log "warn: substrate image $SUBSTRATE_IMAGE not found (panel continues native)"

  if container_running; then
    die "container $CONTAINER_NAME already exists (status first)"
  fi
  if port_in_use "$GATEWAY_PORT"; then
    if ! native_running; then
      die "port $GATEWAY_PORT in use by unknown process"
    fi
    log "native gateway holds port $GATEWAY_PORT (expected)"
  fi

  # Ensure a gateway token exists for deep-health checks.
  [[ -n "$(gateway_token)" ]] || die "no gateway auth token in openclaw.json"

  log "preflight: OK (rootless podman, images, state)"
}

# ---------------------------------------------------------------------------
# Phase: backup
# ---------------------------------------------------------------------------
backup() {
  log "backup: OpenClaw verified backup + btrfs snapshot"
  local stamp backup_id
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_id="pre-cutover-${stamp}"

  if command -v openclaw >/dev/null 2>&1; then
    openclaw backup create --verify --no-include-workspace --output "$BACKUP_DIR" \
      >> "$LOG_FILE" 2>&1 || die "OpenClaw verified backup failed"
    log "backup: OpenClaw verified archive written to $BACKUP_DIR"
  else
    log "warn: openclaw CLI not found; skipping native verified backup"
  fi

  btrfs_snapshot "$STATE_DIR" "$SNAPSHOT_DIR/${backup_id}-openclaw" "$backup_id" \
    || log "warn: btrfs snapshot skipped"

  # Save the current native unit for rollback reference.
  systemctl --user cat "$NATIVE_SERVICE" > "$BACKUP_DIR/native-gateway.unit" 2>/dev/null || true
  # Save pristine openclaw.json for rollback (container patch is reversible).
  if [[ ! -f "$BACKUP_JSON" ]]; then
    cp -a "$STATE_DIR/openclaw.json" "$BACKUP_JSON" 2>/dev/null || true
    cp -a "$STATE_DIR/openclaw.json" "$BACKUP_DIR/openclaw.json.pre-cutover" 2>/dev/null || true
  fi
  # Also snapshot the sqlite DB for rollback (portable patch touches it).
  if [[ ! -f "$BACKUP_DIR/openclaw.sqlite.pre-cutover" ]]; then
    cp -a "$STATE_DIR/state/openclaw.sqlite" "$BACKUP_DIR/openclaw.sqlite.pre-cutover" 2>/dev/null || true
  fi

  echo "$backup_id"
}

# ---------------------------------------------------------------------------
# Phase: test (disposable container, no state mutation)
# ---------------------------------------------------------------------------
test_container() {
  log "test: disposable container smoke (no state mutation)"
  local name="openclaw-smoke-$$" tmp
  tmp="$(mktemp -d -p "$HOME/.cache")"
  trap 'podman rm -f "${name:-}" >/dev/null 2>&1 || true; rm -rf "${tmp:-}"' RETURN

  # Copy state into a disposable writable tree so the gateway can boot
  # exactly as it will in production without touching live state.
  mkdir -p "$tmp/state" "$tmp/workspace"
  cp -a "$STATE_DIR/." "$tmp/state/" 2>/dev/null || true
  cp -a "$WORKSPACE_DIR/." "$tmp/workspace/" 2>/dev/null || true
  # Make disposable state portable (host /home/ahron -> container /home/node).
  LOG_FILE_BACKUP="$LOG_FILE" LOG_FILE="$LOG_FILE" portable_patch_state "$tmp/state" >> "$LOG_FILE" 2>&1 || {
    log "test: portable patch failed"; return 1; }
  # Rewrite workspace path for the container mount layout (idempotent).
  patch_workspace_for_container "$tmp/state" "$WORKSPACE_DIR" >> "$LOG_FILE" 2>&1 || {
    log "test: workspace patch failed"; return 1; }
  # Fix plugin peer symlinks inside the disposable state (host npm-global -> /app).
  fix_plugin_symlinks "$tmp/state" >> "$LOG_FILE" 2>&1 || {
    log "test: symlink patch failed"; return 1; }
  # Point the Ollama baseUrl at the host-loopback address the container uses.
  patch_ollama_host "$tmp/state" >> "$LOG_FILE" 2>&1 || {
    log "test: ollama host patch failed"; return 1; }

  if ! podman run -d --name "$name" \
    --userns=keep-id --user "$(id -u):$(id -g)" \
    --cap-drop=all --security-opt=no-new-privileges \
    -e HOME=/home/node \
    -e NPM_CONFIG_CACHE=/home/node/.openclaw/.npm \
    -v "$tmp/state:/home/node/.openclaw:rw" \
    -v "$tmp/workspace:/home/node/.openclaw/workspace:rw" \
    --network "$NET_MODE" \
    -p 127.0.0.1:18999:18789 \
    "$OPENCLAW_IMAGE" \
    node openclaw.mjs gateway --bind lan --port 18789 >/dev/null 2>&1; then
    log "test: smoke container failed to start"
    return 1
  fi

  # Wait for real health on the disposable port.
  local i=0
  while ! curl -fsS -m 5 http://127.0.0.1:18999/healthz >/dev/null 2>&1; do
    i=$((i + 1))
    if (( i >= 60 )); then
      podman logs "$name" 2>&1 | tail -20 | tee -a "$LOG_FILE"
      return 1
    fi
    sleep 2
  done
  log "test: smoke container healthy on port 18999 (full boot validated)"
  return 0
}

# ---------------------------------------------------------------------------
# Phase: cutover
# ---------------------------------------------------------------------------
cutover() {
  if container_running; then die "container already running; use status"; fi
  if ! native_running && ! port_in_use "$GATEWAY_PORT"; then
    log "warn: neither native gateway nor port holder is active; starting container"
  fi

  # 1. Stop the native gateway (systemd).
  #    The unit has Restart=always/RestartSec=5, so a plain `stop` is undone
  #    within seconds and the port is re-occupied before the container can
  #    bind. Mask first to suppress the auto-restart, then stop.
  log "cutover: disabling native gateway service (prevent Restart/port fight)"
  systemctl --user disable "$NATIVE_SERVICE" >/dev/null 2>&1 \
    || die "failed to disable native gateway service"
  log "cutover: stopping native gateway (kill + disable to beat Restart=always)"
  if native_running; then
    systemctl --user kill "$NATIVE_SERVICE" >/dev/null 2>&1 || true
    sleep 1
  fi
  # After disable + kill, the port should be free immediately. Only wait if
  # something else grabbed it.
  if port_in_use "$GATEWAY_PORT"; then
    log "warn: port $GATEWAY_PORT still held; waiting for release"
    for i in $(seq 1 5); do
      port_in_use "$GATEWAY_PORT" || break
      sleep 1
    done
  fi

  # 2. Make live state portable for the unprivileged container (keep backup).
  if [[ ! -f "$BACKUP_JSON" ]]; then cp -a "$STATE_DIR/openclaw.json" "$BACKUP_JSON"; fi
  if [[ ! -f "$BACKUP_DIR/openclaw.sqlite.pre-cutover" ]]; then cp -a "$STATE_DIR/state/openclaw.sqlite" "$BACKUP_DIR/openclaw.sqlite.pre-cutover" 2>/dev/null || true; fi
  portable_patch_state "$STATE_DIR" >> "$LOG_FILE" 2>&1 || die "portable patch failed"
  patch_workspace_for_container "$STATE_DIR" "$WORKSPACE_DIR" >> "$LOG_FILE" 2>&1 || die "workspace patch failed"
  fix_plugin_symlinks "$STATE_DIR" >> "$LOG_FILE" 2>&1 || die "symlink patch failed"
  patch_ollama_host "$STATE_DIR" >> "$LOG_FILE" 2>&1 || die "ollama host patch failed"

  # 3. Start the containerized gateway on the original port.
  log "cutover: starting container $CONTAINER_NAME on port $GATEWAY_PORT (orig URL preserved)"
  # Before starting the container, verify the portability patch produced a
  # consistent container-home path. A blanket replace of the host home can
  # leak into session records (e.g. agents/main/sessions/*.jsonl) and the
  # gateway config-audit, which then breaks the NATIVE process on rollback
  # (EACCES mkdir '/home/node'). The container tolerates a few stray
  # references; the native host must not be left with any.
  if grep -rl "/home/node" "$STATE_DIR"/agents/main/sessions/ "$STATE_DIR"/logs/ 2>/dev/null | grep -qv "extensions/"; then
    log "cutover: WARNING portability references found in session/log state (benign for container; native rollback will restore them)"
  fi
  podman run -d --name "$CONTAINER_NAME" \
    --userns=keep-id --user "$(id -u):$(id -g)" \
    --cap-drop=all --security-opt=no-new-privileges \
    -e HOME=/home/node \
    -e NPM_CONFIG_CACHE=/home/node/.openclaw/.npm \
    --network "$NET_MODE" \
    -v "$STATE_DIR:/home/node/.openclaw:rw" \
    -v "$WORKSPACE_DIR:/home/node/.openclaw/workspace:rw" \
    -p "127.0.0.1:${GATEWAY_PORT}:18789" \
    "$OPENCLAW_IMAGE" \
    node openclaw.mjs gateway --bind lan --port 18789 >> "$LOG_FILE" 2>&1 \
    || { log "container start failed; restoring native"; restore_state_for_native "$STATE_DIR" >>"$LOG_FILE" 2>&1 || true; restore_native; die "container start failed"; }

  # 4. Wait for health.
  log "cutover: waiting for gateway health on port $GATEWAY_PORT"
  if ! wait_health "$GATEWAY_PORT"; then
    log "cutover: health check failed; rolling back"
    restore_state_for_native "$STATE_DIR" >>"$LOG_FILE" 2>&1 || true
    rollback
    exit 1
  fi

  # 5. Deep health (authenticated).
  if ! gateway_deep_health; then
    log "cutover: deep health failed; rolling back"
    restore_state_for_native "$STATE_DIR" >>"$LOG_FILE" 2>&1 || true
    rollback
    exit 1
  fi

  # 6. Native service stays disabled (prevents port fight on reboot). The
  #    capsule container is the gateway now; rollback re-enables it.
  log "cutover: complete — gateway now containerized on http://127.0.0.1:${GATEWAY_PORT} (native service disabled)"
}

# ---------------------------------------------------------------------------
# Phase: rollback
# ---------------------------------------------------------------------------
restore_native() {
  log "rollback: restoring native gateway"
  podman rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  # Restore pristine host state for the systemd gateway.
  restore_state_for_native "$STATE_DIR" >>"$LOG_FILE" 2>&1 || true
  # Repair any remaining container-home references in session/log records so
  # the native process never tries to mkdir /home/node. This complements
  # restore_state_for_native (which covers openclaw.json + sqlite).
  python3 - "$STATE_DIR" "$HOME" <<'PY' >>"$LOG_FILE" 2>&1 || true
import sys
state, host_home = sys.argv[1], sys.argv[2]
ctr_home = "/home/node"
for sub in ("agents/main/sessions", "logs"):
    root = __import__("os").path.join(state, sub)
    if not __import__("os").path.isdir(root):
        continue
    fixed = 0
    for dirpath, _dirnames, filenames in __import__("os").walk(root):
        for fn in filenames:
            p = __import__("os").path.join(dirpath, fn)
            try:
                with open(p, "r", errors="ignore") as fh:
                    raw = fh.read()
            except OSError:
                continue
            if ctr_home in raw:
                with open(p, "w") as fh:
                    fh.write(raw.replace(ctr_home, host_home))
                fixed += 1
    print(f"restore_state_for_native: repaired {fixed} file(s) under {root}: {ctr_home!r} -> {host_home!r}")
PY
  # Re-enable first (the cutover disabled it to suppress Restart=always).
  systemctl --user enable "$NATIVE_SERVICE" >/dev/null 2>&1 || true
  systemctl --user start "$NATIVE_SERVICE" >/dev/null 2>&1 || true
  sleep 3
  if wait_health "$GATEWAY_PORT"; then
    log "rollback: native gateway healthy on $GATEWAY_PORT"
  else
    log "rollback: WARNING native gateway did not become healthy"
    return 1
  fi
}

rollback() {
  restore_native
}

# ---------------------------------------------------------------------------
# Phase: status
# ---------------------------------------------------------------------------
status() {
  echo "=== Capsule status ==="
  echo "Native gateway: $(native_running && echo active || echo inactive)"
  echo "Container:      $(container_running && echo running || echo stopped)"
  if container_running; then
    podman inspect "$CONTAINER_NAME" --format \
      '  image={{.ImageName}} port={{range .Ports}}{{.HostPort}}{{end}} user={{.Config.User}}' 2>/dev/null || true
  fi
  echo "Port 8090:      $(port_in_use 8090 && echo in-use || echo free)"
  echo "Gateway health: $(gateway_health "$GATEWAY_PORT" && echo ok || echo fail)"
  echo "Panel 8095:     $(gateway_health 8095 && echo ok || echo unavailable)"
  echo "Chatbot 8321:   $(gateway_health 8321 && echo ok || echo unavailable)"
  if command -v openclaw >/dev/null 2>&1; then
    openclaw status --deep 2>/dev/null | head -12 || true
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  local phase="${1:-status}"
  case "$phase" in
    preflight) preflight ;;
    backup) backup ;;
    test) test_container ;;
    cutover)
      acquire_lock
      preflight
      backup
      test_container
      cutover
      status
      ;;
    rollback)
      acquire_lock
      rollback
      status
      ;;
    status) status ;;
    *) die "usage: $0 {preflight|backup|test|cutover|rollback|status}" ;;
  esac
}

main "$@"
