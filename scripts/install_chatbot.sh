#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: bash scripts/install_chatbot.sh [--no-autostart] [--no-systemd] [--with-systemd]

Installs the Substrate Chatbot desktop integration:
  - tray/app icon at ~/.local/share/icons/substrate-chatbot.png
  - app launcher at ~/.local/share/applications/substrate-chatbot.desktop
  - optional autostart entry at ~/.config/autostart/substrate-chatbot.desktop
  - optional systemd user service for headless HTTP serving

Flags:
  --no-autostart   skip the login autostart entry
  --no-systemd     skip installing the headless systemd service
  --with-systemd   install AND enable the headless systemd service
USAGE
}

AUTOSTART=1
SYSTEMD_MODE="skip"  # skip | install | enable

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --no-autostart) AUTOSTART=0 ;;
    --no-systemd) SYSTEMD_MODE="skip" ;;
    --with-systemd) SYSTEMD_MODE="enable" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_BIN="$(command -v uv || echo /home/ahron/.local/bin/uv)"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
ICON_PATH="$ICON_DIR/substrate-chatbot.png"
DESKTOP_PATH="$APP_DIR/substrate-chatbot.desktop"
AUTOSTART_PATH="$AUTOSTART_DIR/substrate-chatbot.desktop"

mkdir -p "$ICON_DIR" "$APP_DIR"

echo "Generating tray/app icon..."
"$UV_BIN" run --project "$ROOT_DIR" python -c "
from substrate.chatbot.tray import _make_icon_image
_make_icon_image().save('$ICON_PATH')
print('wrote $ICON_PATH')
"

write_desktop() {
  local path="$1"
  cat >"$path" <<EOF
[Desktop Entry]
Type=Application
Name=Substrate Chat
GenericName=AI Chatbot
Comment=Desktop chatbot with autonomous Kilo agency for desktop and internet tasks
Exec=${UV_BIN} run --project ${ROOT_DIR} python ${ROOT_DIR}/scripts/chatbot.py tray
Icon=${ICON_PATH}
Terminal=false
Categories=Utility;Network;Chat;
Keywords=ai;agent;chat;automation;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF
  echo "wrote $path"
}

write_desktop "$DESKTOP_PATH"
if [[ "$AUTOSTART" -eq 1 ]]; then
  mkdir -p "$AUTOSTART_DIR"
  write_desktop "$AUTOSTART_PATH"
  echo "Autostart entry installed at $AUTOSTART_PATH"
fi

if [[ "$SYSTEMD_MODE" != "skip" ]]; then
  SERVICE_NAME="substrate-chatbot"
  SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  mkdir -p "$SYSTEMD_USER_DIR"
  SERVICE_FILE="$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"
  cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Substrate Chatbot HTTP server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${ROOT_DIR}
ExecStart=${UV_BIN} run python ${ROOT_DIR}/scripts/chatbot.py serve
Restart=on-failure
RestartSec=5
Environment=SUBSTRATE_ROOT=${ROOT_DIR}

[Install]
WantedBy=default.target
EOF
  echo "wrote $SERVICE_FILE"

  if [[ "$SYSTEMD_MODE" == "enable" ]] && command -v systemctl >/dev/null 2>&1 \
    && systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable --now "${SERVICE_NAME}.service"
    echo "Enabled ${SERVICE_NAME}.service"
    echo "Logs: journalctl --user -u ${SERVICE_NAME} -f"
  else
    echo "Systemd service written; enable it manually with:"
    echo "  systemctl --user daemon-reload"
    echo "  systemctl --user enable --now ${SERVICE_NAME}.service"
  fi
fi

echo
echo "Done. Launch the chatbot from your app menu (Substrate Chat) or run:"
echo "  ${UV_BIN} run --project ${ROOT_DIR} python ${ROOT_DIR}/scripts/chatbot.py tray"
echo "Open the UI directly:"
echo "  ${UV_BIN} run --project ${ROOT_DIR} python ${ROOT_DIR}/scripts/chatbot.py open"
