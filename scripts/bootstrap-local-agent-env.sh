#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_BIN="${HOME}/.local/bin"
BASHRC="${HOME}/.bashrc"
FISH_CONF_DIR="${HOME}/.config/fish/conf.d"
FISH_AGENT_CONF="${FISH_CONF_DIR}/20-local-agent-env.fish"
SIDECAR_ENV_FILE="${ROOT_DIR}/.env.local-agent-tools"

APPLY_SHELL_HOOKS=0
SKIP_MISE_TOOLS=0
SKIP_PYTHON_ENV=0

export PATH="${LOCAL_BIN}:${PATH}"

log() {
  printf '[bootstrap] %s\n' "$*"
}

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap-local-agent-env.sh [options]

Options:
  --apply-shell-hooks   Append shell hooks to ~/.bashrc and fish config (opt-in).
  --skip-mise-tools     Skip mise tool installation.
  --skip-python-env     Skip uv python install and dependency sync.
  -h, --help            Show this help.
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --apply-shell-hooks)
        APPLY_SHELL_HOOKS=1
        shift
        ;;
      --skip-mise-tools)
        SKIP_MISE_TOOLS=1
        shift
        ;;
      --skip-python-env)
        SKIP_PYTHON_ENV=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        log "Unknown argument: $1"
        usage
        exit 1
        ;;
    esac
  done
}

ensure_local_bin() {
  mkdir -p "${LOCAL_BIN}"
}

install_uv() {
  if [[ -x "${LOCAL_BIN}/uv" ]]; then
    log "uv already installed: ${LOCAL_BIN}/uv"
    return
  fi
  log "Installing uv to ${LOCAL_BIN}"
  curl -fsSL https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="${LOCAL_BIN}" sh
}

install_mise() {
  if [[ -x "${LOCAL_BIN}/mise" ]]; then
    log "mise already installed: ${LOCAL_BIN}/mise"
    return
  fi
  log "Installing mise to ${LOCAL_BIN}/mise"
  curl -fsSL https://mise.run | env MISE_INSTALL_PATH="${LOCAL_BIN}/mise" sh
}

install_direnv() {
  if [[ -x "${LOCAL_BIN}/direnv" ]]; then
    log "direnv already installed: ${LOCAL_BIN}/direnv"
    return
  fi
  log "Installing direnv to ${LOCAL_BIN}/direnv"
  bin_path="${LOCAL_BIN}" bash -c "$(curl -fsSL https://direnv.net/install.sh)"
}

configure_bash() {
  local marker_start="# >>> local-agent-env >>>"
  if grep -Fq "${marker_start}" "${BASHRC}" 2>/dev/null; then
    log ".bashrc already configured"
    return
  fi
  log "Configuring ${BASHRC}"
  cat >>"${BASHRC}" <<'EOF'

# >>> local-agent-env >>>
export PATH="$HOME/.local/bin:$PATH"
if command -v direnv >/dev/null 2>&1; then
  eval "$(direnv hook bash)"
fi
if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate bash)"
fi
# <<< local-agent-env <<<
EOF
}

configure_fish() {
  mkdir -p "${FISH_CONF_DIR}"
  log "Configuring ${FISH_AGENT_CONF}"
  cat >"${FISH_AGENT_CONF}" <<'EOF'
if not contains $HOME/.local/bin $PATH
  fish_add_path -m $HOME/.local/bin
end

if type -q direnv
  direnv hook fish | source
end

if type -q mise
  mise activate fish | source
end
EOF
}

write_sidecar_env() {
  log "Writing sidecar activation file: ${SIDECAR_ENV_FILE}"
  cat >"${SIDECAR_ENV_FILE}" <<EOF
export PATH="${LOCAL_BIN}:\$PATH"
if command -v direnv >/dev/null 2>&1; then
  eval "\$(direnv hook bash)"
fi
if command -v mise >/dev/null 2>&1; then
  eval "\$(mise activate bash)"
fi
EOF
}

install_mise_tools() {
  if [[ "${SKIP_MISE_TOOLS}" -eq 1 ]]; then
    log "Skipping mise tool install (--skip-mise-tools)"
    return
  fi
  local mise_bin="${LOCAL_BIN}/mise"
  if [[ ! -x "${mise_bin}" ]]; then
    log "Skipping mise tool install; binary not found at ${mise_bin}"
    return
  fi
  log "Installing tools defined in ${ROOT_DIR}/mise.toml"
  (
    cd "${ROOT_DIR}"
    PATH="${LOCAL_BIN}:${PATH}" "${mise_bin}" trust -y "${ROOT_DIR}/mise.toml"
    PATH="${LOCAL_BIN}:${PATH}" "${mise_bin}" install
  )
}

install_python_env() {
  if [[ "${SKIP_PYTHON_ENV}" -eq 1 ]]; then
    log "Skipping python env sync (--skip-python-env)"
    return
  fi
  local uv_bin="${LOCAL_BIN}/uv"
  if [[ ! -x "${uv_bin}" ]]; then
    log "Skipping python env sync; uv not found at ${uv_bin}"
    return
  fi
  log "Installing Python 3.12 with uv"
  PATH="${LOCAL_BIN}:${PATH}" "${uv_bin}" python install 3.12
  log "Syncing project dependencies"
  (
    cd "${ROOT_DIR}"
    PATH="${LOCAL_BIN}:${PATH}" "${uv_bin}" sync --python 3.12
    PATH="${LOCAL_BIN}:${PATH}" "${uv_bin}" tool install pre-commit
  )
}

main() {
  parse_args "$@"
  ensure_local_bin
  install_uv
  install_mise
  install_direnv
  write_sidecar_env
  if [[ "${APPLY_SHELL_HOOKS}" -eq 1 ]]; then
    configure_bash
    configure_fish
  else
    log "Skipping shell profile edits by default. Use --apply-shell-hooks to enable."
  fi
  install_mise_tools
  install_python_env
  log "Bootstrap complete. Activate with: source ${SIDECAR_ENV_FILE}"
}

main "$@"
