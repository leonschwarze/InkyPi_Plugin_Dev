#!/usr/bin/env bash
# Tasten für InkyPi installieren:  sudo bash install.sh
set -euo pipefail

ZIEL=/usr/local/inkypi-tasten
PY=/usr/local/inkypi/venv_inkypi/bin/python
DIENST=inkypi-tasten.service

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo starten:  sudo bash install.sh"
  exit 1
fi
if [[ ! -x $PY ]]; then
  echo "InkyPi nicht gefunden ($PY). Ist InkyPi installiert?"
  exit 1
fi

cd "$(dirname "$0")"

# Bei einer erneuten Installation hält der laufende Dienst die Tasten-Leitungen – erst anhalten
systemctl stop "$DIENST" 2>/dev/null || true

echo "Kopiere nach $ZIEL …"
install -d "$ZIEL"
install -m 644 tasten.py "$ZIEL/"
install -m 644 "$DIENST" /etc/systemd/system/

echo "Prüfe Einstellungen, Dashboard, InkyPi und Tasten-Leitungen …"
if ! "$PY" "$ZIEL/tasten.py" --probe; then
  echo
  echo "Die Prüfung hat etwas gemeldet (siehe oben). Der Dienst wird trotzdem eingerichtet;"
  echo "nach dem Beheben:  sudo systemctl restart $DIENST"
fi

echo "Richte den Dienst ein …"
systemctl daemon-reload
systemctl enable --now "$DIENST"

echo
echo "Fertig. Taste A zeichnet das Dashboard neu, Taste D zeigt das Hilfsbild (noch einmal D schließt es)."
echo "Nachts (im Nachtbild) tun die Tasten nichts. Die LED leuchtet, solange das Display arbeitet."
echo "Mitlesen:  journalctl -u $DIENST -f"
echo "Ohne Taste ausprobieren:  sudo $PY $ZIEL/tasten.py --druck A   (oder D)"
echo
echo "Das Hilfsbild braucht das Tagesdashboard ab Version 1.49 (Ordner tagesdashboard/ ersetzen,"
echo "sudo systemctl restart inkypi.service). Taste A wirkt auch ohne – dann aber mit dem Bild-Cache des Dashboards."
