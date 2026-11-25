#!/usr/bin/env bash
# Tasten für InkyPi wieder entfernen:  sudo bash uninstall.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo starten:  sudo bash uninstall.sh"
  exit 1
fi

systemctl disable --now inkypi-tasten.service 2>/dev/null || true
rm -f /etc/systemd/system/inkypi-tasten.service
systemctl daemon-reload
rm -rf /usr/local/inkypi-tasten
# Die Zustandsdatei neben InkyPis device.json ist harmlos, ohne Dienst schreibt sie niemand mehr
rm -f /usr/local/inkypi/src/config/tasten_zustand.json
echo "Tasten entfernt. Das Dashboard läuft unverändert weiter."
