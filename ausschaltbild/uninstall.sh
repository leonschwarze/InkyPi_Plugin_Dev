#!/usr/bin/env bash
# Ausschaltbild wieder entfernen:  sudo bash uninstall.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo starten:  sudo bash uninstall.sh"
  exit 1
fi

# Stoppen löst ExecStop aus – das Skript erkennt aber, dass nicht ausgeschaltet wird,
# und lässt das Display in Ruhe.
systemctl disable --now inkypi-ausschaltbild.service 2>/dev/null || true
systemctl disable --now inkypi-ausschaltbild-start.service 2>/dev/null || true
rm -f /etc/systemd/system/inkypi-ausschaltbild.service /etc/systemd/system/inkypi-ausschaltbild-start.service
rm -rf /usr/local/inkypi-ausschaltbild
systemctl daemon-reload
echo "Ausschaltbild entfernt."
