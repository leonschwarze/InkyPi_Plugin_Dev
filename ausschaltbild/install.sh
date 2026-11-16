#!/usr/bin/env bash
# Ausschaltbild für InkyPi installieren:  sudo bash install.sh
set -euo pipefail

ZIEL=/usr/local/inkypi-ausschaltbild
PY=/usr/local/inkypi/venv_inkypi/bin/python
DIENST=inkypi-ausschaltbild.service
START=inkypi-ausschaltbild-start.service

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo starten:  sudo bash install.sh"
  exit 1
fi
if [[ ! -x $PY ]]; then
  echo "InkyPi nicht gefunden ($PY). Ist InkyPi installiert?"
  exit 1
fi

cd "$(dirname "$0")"
echo "Kopiere nach $ZIEL …"
install -d "$ZIEL"
install -m 644 ausschaltbild.py eink.py "$ZIEL/"
install -m 644 "$DIENST" "$START" /etc/systemd/system/

echo "Prüfe Einstellungen, Schrift und Treiber …"
"$PY" "$ZIEL/ausschaltbild.py" --probe

echo "Richte die Dienste ein …"
systemctl daemon-reload
systemctl enable --now "$DIENST"
# Nur einschalten, nicht jetzt starten: Er läuft ab jetzt jedes Mal mit, wenn InkyPi startet.
systemctl enable "$START"

echo
echo "Fertig. Beim nächsten Ausschalten (sudo poweroff oder „Shutdown“ in InkyPi)"
echo "zeigt das Display: Ausgeschaltet – der Stecker kann gezogen werden."
echo "Bei einem Neustart bleibt das Display, wie es ist."
echo "Startet InkyPi (Einschalten, Neustart, systemctl restart), zeichnet es sofort neu,"
echo "statt erst nach einem ganzen Takt – so sieht man, dass der Pi wieder läuft."
echo
echo "Ohne Ausschalten ausprobieren:"
echo "  sudo systemctl stop inkypi.service"
echo "  sudo $PY $ZIEL/ausschaltbild.py --zeigen"
echo "  sudo systemctl start inkypi.service     # zeichnet gleich wieder das Dashboard"
