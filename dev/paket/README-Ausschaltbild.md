# Ausschaltbild für InkyPi

Wenn der Raspberry Pi ausgeschaltet wird, zeigt das Display zum Schluss:

**Ausgeschaltet – der Stecker kann jetzt gezogen werden**, dazu wann heruntergefahren wurde und die schlafende Katze aus dem Tagesdashboard.

![Ausschaltbild quer](docs/ausschaltbild_800x480.png)

Ein E-Ink-Display braucht nur Strom, während es das Bild wechselt. Danach bleibt das Bild ohne Strom stehen. Das Ausschaltbild ist darum das letzte, was der Pi tut, und es bleibt sichtbar, bis du ihn wieder einsteckst. Dann zeichnet InkyPi wie gewohnt.

Das ist **kein Plugin**, sondern ein kleiner Zusatz neben InkyPi: ein systemd-Dienst, der beim Herunterfahren ein Python-Skript startet. Er braucht nichts zusätzlich; er nutzt InkyPis Python-Umgebung, den Pimoroni-Treiber und die Schrift Jost aus InkyPi.

## Installieren

Ordner auf den Pi kopieren (z. B. per `scp`) und dort:

```bash
cd ausschaltbild
sudo bash install.sh
```

Das Skript kopiert die Dateien nach `/usr/local/inkypi-ausschaltbild/`, legt den Dienst `inkypi-ausschaltbild.service` an und schaltet ihn ein. Vorher prüft es, ob es InkyPis Einstellungen, die Schrift und den Treiber findet, und speichert eine Vorschau unter `/tmp/ausschaltbild-probe.png`.

## Ausprobieren, ohne auszuschalten

```bash
sudo systemctl stop inkypi.service
sudo /usr/local/inkypi/venv_inkypi/bin/python /usr/local/inkypi-ausschaltbild/ausschaltbild.py --zeigen
sudo systemctl start inkypi.service
```

InkyPi muss dafür kurz gestoppt sein, sonst würden zwei Programme gleichzeitig auf das Display schreiben (das Skript weist dich dann darauf hin). Nach dem Start zeichnet InkyPi bei der nächsten Runde wieder sein Bild. Mit „Update Now“ in der Weboberfläche geht es sofort.

## Im Alltag

- **Ausschalten:** `sudo poweroff` oder in InkyPis Weboberfläche „Shutdown“. Das Bild erscheint nach InkyPis Ende; ein volles Bild dauert auf dem Spectra-6-Display etwa eine halbe Minute. Danach braucht der Pi nur noch ein paar Sekunden. Ganz sicher bist du, wenn die grüne LED am Pi nicht mehr blinkt.
- **Neustart** (`sudo reboot`, „Reboot“): Das Display bleibt, wie es ist. „Stecker ziehen“ wäre hier falsch.
- **Strom einfach weg** (ohne Herunterfahren): Dann kann nichts mehr gezeichnet werden; es bleibt das letzte Bild stehen.
- **Nach dem Einschalten:** Das Skript setzt in InkyPis `device.json` die Prüfsumme des zuletzt gezeigten Bildes zurück. Sonst würde InkyPi ein gleiches Bild (zum Beispiel das Nachtbild, das die ganze Nacht gleich bleibt) für „schon angezeigt“ halten, und das Ausschaltbild bliebe stehen.
- Hochkant, „Bild drehen“ (inverted) und die Inky-Sättigung übernimmt das Skript aus InkyPis Einstellungen.

## Nachsehen, ob es geklappt hat

Nach dem nächsten Einschalten:

```bash
cat /usr/local/inkypi-ausschaltbild/letzter-lauf.txt
```

Dort steht zum Beispiel `Ausschaltbild gezeichnet in 24.3 s`, bei einem Neustart `kein Ausschalten (reboot) – Display bleibt, wie es ist`, oder eine Fehlermeldung. Fehler halten das Herunterfahren nie auf. Die gleichen Zeilen stehen im Journal: `journalctl -u inkypi-ausschaltbild -b -1` (vorheriger Start; nur wenn das Journal dauerhaft gespeichert wird).

## Entfernen

```bash
sudo bash uninstall.sh
```

## Wie es funktioniert

Beim Herunterfahren stoppt systemd alle Dienste in **umgekehrter Startreihenfolge**. Der Dienst hat `Before=inkypi.service`: beim Start vor InkyPi, beim Herunterfahren also **nach** InkyPi. So ist das Display frei, wenn das Skript zeichnet, und die Speicherkarte ist noch beschreibbar.

Der Dienst tut beim Start nichts (`ExecStart=/bin/true`) und gilt danach als aktiv (`RemainAfterExit=yes`). Nur deshalb wird er beim Herunterfahren gestoppt, und dabei läuft `ExecStop`, das Skript. Es fragt `systemctl list-jobs`, ob gerade `poweroff.target` (bzw. `halt.target`) startet; nur dann zeichnet es.

Das Bild zeichnet Pillow direkt, ohne Chromium (beim Herunterfahren zählt jede Sekunde): in vierfacher Größe für glatte Kurven und gleichmäßige Schrift, dann verkleinert. Danach rastet `eink.py` (dasselbe wie in den Plugins) die Farben auf die Displayfarben ein, damit der Treiber nichts mehr rastert.
