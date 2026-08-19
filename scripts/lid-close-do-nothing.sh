#!/usr/bin/env bash
# Lid-close power management: do NOTHING when the lid is closed.
#
# The gateway laptop was suspending when the lid closed, taking the OpenClaw
# gateway (and all automations) offline. This installs a systemd-logind
# drop-in so lid close never suspends, on battery or AC.
#
# Run once:
#   sudo bash scripts/lid-close-do-nothing.sh
#
# Rollback:
#   sudo rm /etc/systemd/logind.conf.d/lid-close-do-nothing.conf
#   sudo systemctl restart systemd-logind
#
set -euo pipefail

DROPIN=/etc/systemd/logind.conf.d/lid-close-do-nothing.conf

mkdir -p /etc/systemd/logind.conf.d
printf '[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\n' > "$DROPIN"
chmod 644 "$DROPIN"
systemctl restart systemd-logind
sleep 1

echo "Installed: $DROPIN"
echo "--- effective values ---"
busctl get-property org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager HandleLidSwitch
busctl get-property org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager HandleLidSwitchExternalPower
busctl get-property org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager HandleLidSwitchDocked
echo "--- sessions ---"
loginctl list-sessions --no-legend
echo "OK: lid close is now ignored (no suspend). Rollback: rm $DROPIN && systemctl restart systemd-logind"
