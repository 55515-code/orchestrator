#!/usr/bin/env bash
# Proton integration setup for the 1pointo substrate.
# Drive (rclone), Mail (Bridge), VPN (CLI).
#
# Interactive steps require your Proton credentials — run this from a terminal
# where you can type them. Each section is skippable.
set -uo pipefail

echo "=== Proton Setup ==="

# --- 1. Drive (rclone protondrive) ---
if command -v rclone >/dev/null 2>&1; then
  echo ""
  echo "[1/3] Proton Drive via rclone"
  echo "  Run: rclone config (choose 'n'ew remote, type 'protondrive')"
  echo "  OR if already configured, test with: rclone lsd protondrive:"
  if rclone listremotes 2>/dev/null | grep -q protondrive; then
    echo "  ✓ protondrive remote already configured."
  else
    echo "  ✗ not configured. Run: rclone config"
  fi
else
  echo "[1/3] rclone not found — install with: sudo pacman -S rclone"
fi

# --- 2. Mail (Proton Mail Bridge) ---
echo ""
echo "[2/3] Proton Mail Bridge (localhost IMAP :1143 / SMTP :1025)"
if command -v protonmail-bridge >/dev/null 2>&1; then
  echo "  ✓ bridge binary installed."
  echo "  First-time login: protonmail-bridge --cli (then: login, then: exit)"
  echo "  Daemon: systemctl --user start protonmail-bridge"
else
  echo "  ✗ not installed. Run: sudo pacman -S protonmail-bridge-core"
fi

# --- 3. VPN (Proton VPN CLI) ---
echo ""
echo "[3/3] Proton VPN CLI"
if command -v protonvpn-cli >/dev/null 2>&1; then
  echo "  ✓ CLI installed."
  echo "  Login: protonvpn-cli login"
  echo "  Connect: protonvpn-cli connect --fastest"
  echo "  Status: protonvpn-cli status"
else
  echo "  ✗ not installed. Run: sudo pacman -S proton-vpn-cli"
fi

echo ""
echo "=== Done. See ~/codespace/automation/actions.json for one-click variants. ==="
