# Ausschaltbild für InkyPi – Version 1.1

Wenn der Raspberry Pi ausgeschaltet wird, zeigt das Display zum Schluss:

**Ausgeschaltet – der Stecker kann jetzt gezogen werden**, dazu wann heruntergefahren wurde und die schlafende Katze aus dem Tagesdashboard.

![Ausschaltbild quer](docs/ausschaltbild_800x480.png)

Ein E-Ink-Display braucht nur Strom, während es das Bild wechselt. Danach bleibt das Bild ohne Strom stehen. Das Ausschaltbild ist darum das letzte, was der Pi tut, und es bleibt sichtbar, bis du ihn wieder einsteckst. Sobald InkyPi dann läuft, zeichnet es sofort neu (seit 1.1) – so siehst du, dass der Pi wieder da ist.

Das ist **kein Plugin**, sondern ein kleiner Zusatz neben InkyPi: zwei systemd-Dienste, die beim Herunterfahren bzw. nach dem Start von InkyPi ein Python-Skript starten. Er braucht nichts zusätzlich; er nutzt InkyPis Python-Umgebung, den Pimoroni-Treiber und die Schrift Jost aus InkyPi.

## Installieren bzw. aktualisieren

Direkt auf dem Pi aus GitHub holen:

```bash
git clone https://github.com/leonschwarze/InkyPi_Ausschaltbild
sudo bash InkyPi_Ausschaltbild/ausschaltbild/install.sh
```

Später aktualisieren: `git -C InkyPi_Ausschaltbild pull` und `install.sh` noch einmal ausführen. Alternativ das ZIP-Paket entpacken (bzw. den Ordner `ausschaltbild/` per `scp` auf den Pi kopieren) und dort `sudo bash ausschaltbild/install.sh` ausführen.

Das Skript kopiert die Dateien nach `/usr/local/inkypi-ausschaltbild/`, legt die Dienste `inkypi-ausschaltbild.service` (beim Ausschalten) und `inkypi-ausschaltbild-start.service` (nach dem Start) an und schaltet sie ein. Eine ältere Version wird dabei einfach ersetzt – zum Aktualisieren also genauso installieren. Vorher prüft es, ob es InkyPis Einstellungen, die Schrift und den Treiber findet, und speichert eine Vorschau unter `/tmp/ausschaltbild-probe.png`.

## Ausprobieren, ohne auszuschalten

```bash
sudo systemctl stop inkypi.service
sudo /usr/local/inkypi/venv_inkypi/bin/python /usr/local/inkypi-ausschaltbild/ausschaltbild.py --zeigen
sudo systemctl start inkypi.service
```

InkyPi muss dafür kurz gestoppt sein, sonst würden zwei Programme gleichzeitig auf das Display schreiben (das Skript weist dich dann darauf hin). Nach dem Start zeichnet InkyPi gleich wieder sein Bild (dafür sorgt der zweite Dienst).

## Im Alltag

- **Ausschalten:** `sudo poweroff` oder in InkyPis Weboberfläche „Shutdown“. Das Bild erscheint nach InkyPis Ende; ein volles Bild dauert auf dem Spectra-6-Display etwa eine halbe Minute. Danach braucht der Pi nur noch ein paar Sekunden. Ganz sicher bist du, wenn die grüne LED am Pi nicht mehr blinkt.
- **Neustart** (`sudo reboot`, „Reboot“): Das Display bleibt, wie es ist. „Stecker ziehen“ wäre hier falsch.
- **Strom einfach weg** (ohne Herunterfahren): Dann kann nichts mehr gezeichnet werden; es bleibt das letzte Bild stehen.
- **Nach dem Einschalten:** InkyPi selbst wartet nach dem Start erst einen ganzen Takt (bei 15 Minuten also 15 Minuten), bevor es zeichnet. Der zweite Dienst startet deshalb mit InkyPi, wartet, bis die Weboberfläche antwortet, und löst dann dasselbe aus wie der Knopf „Display“ in der Playlist – für die Instanz, die laut Playlist gerade dran ist. Das gilt auch nach `sudo systemctl restart inkypi.service` und nach einem Absturz. Hat das Plugin beim Start noch kein Netz, versucht er es dreimal im Abstand von 30 Sekunden; klappt es nicht, zeichnet InkyPi beim nächsten Takt.
- **Prüfsumme:** Das Skript setzt in InkyPis `device.json` die Prüfsumme des zuletzt gezeigten Bildes zurück. Sonst würde InkyPi ein gleiches Bild (zum Beispiel das Nachtbild, das die ganze Nacht gleich bleibt) für „schon angezeigt“ halten, und das Ausschaltbild bliebe stehen.
- Hochkant, „Bild drehen“ (inverted) und die Inky-Sättigung übernimmt das Skript aus InkyPis Einstellungen.

## Nachsehen, ob es geklappt hat

Nach dem nächsten Einschalten:

```bash
cat /usr/local/inkypi-ausschaltbild/letzter-lauf.txt
```

Dort steht zum Beispiel `Ausschaltbild gezeichnet in 24.3 s` und nach dem Einschalten `Nach dem Start neu gezeichnet: Tagesdashboard (tagesdashboard, Playlist Default) in 41.2 s`, bei einem Neustart `kein Ausschalten (reboot) – Display bleibt, wie es ist`, oder eine Fehlermeldung. Die Datei behält die letzten 200 Zeilen. Fehler halten das Herunterfahren nie auf. Die gleichen Zeilen stehen im Journal: `journalctl -u inkypi-ausschaltbild -b -1` (vorheriger Start; nur wenn das Journal dauerhaft gespeichert wird) bzw. `journalctl -u inkypi-ausschaltbild-start -b`.

## Entfernen

```bash
sudo bash uninstall.sh
```

## Wie es funktioniert

Beim Herunterfahren stoppt systemd alle Dienste in **umgekehrter Startreihenfolge**. Der Dienst hat `Before=inkypi.service`: beim Start vor InkyPi, beim Herunterfahren also **nach** InkyPi. So ist das Display frei, wenn das Skript zeichnet, und die Speicherkarte ist noch beschreibbar.

Der Dienst tut beim Start nichts (`ExecStart=/bin/true`) und gilt danach als aktiv (`RemainAfterExit=yes`). Nur deshalb wird er beim Herunterfahren gestoppt, und dabei läuft `ExecStop`, das Skript. Es fragt `systemctl list-jobs`, ob gerade `poweroff.target` (bzw. `halt.target`) startet; nur dann zeichnet es.

Das Bild zeichnet Pillow direkt, ohne Chromium (beim Herunterfahren zählt jede Sekunde): in vierfacher Größe für glatte Kurven und gleichmäßige Schrift, dann verkleinert. Danach rastet `eink.py` (dasselbe wie in den Plugins) die Farben auf die Displayfarben ein, damit der Treiber nichts mehr rastert.

Nach dem Start: InkyPis Hintergrund-Thread beginnt mit Warten (`condition.wait(timeout=…)` in `refresh_task.py`), nicht mit Zeichnen. Der Dienst `inkypi-ausschaltbild-start.service` hat `WantedBy=inkypi.service` und `After=inkypi.service`: Er wird jedes Mal mitgestartet, wenn InkyPi startet, und erst danach. `Type=exec` sorgt dafür, dass `systemctl restart inkypi.service` nicht auf das Display wartet. Das Skript wählt die Instanz wie InkyPi (aktive Playlist, bei mehreren die kürzeste; darin die zuletzt gezeigte Instanz) und schickt `POST /display_plugin_instance` an `http://127.0.0.1`.
