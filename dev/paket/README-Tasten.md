# Tasten für InkyPi (Inky Impression 7,3″) – Version 1.0

Der Inky Impression hat vier Tasten (A bis D) an der linken Seite. InkyPi selbst kennt sie nicht. Dieser kleine Dienst läuft **neben** InkyPi, liest die Tasten und spricht InkyPi über dessen Weboberfläche an – genauso wie der Knopf „Display“ dort. Das Display gehört weiter InkyPi.

| Taste | Funktion |
|---|---|
| **A** | **Jetzt neu zeichnen** – das Dashboard zeichnet mit frischen Daten, ohne seinen Bild-Cache (dauert etwa eine Minute) |
| B | nicht belegt |
| C | nicht belegt |
| **D** | **Hilfsbild** – Belegung der Tasten, Version, Zustand des Pi; noch einmal D schließt es, sonst nach 3 Minuten |

- **Nachts** (im Nachtbild des Dashboards) tun die Tasten nichts.
- Die **LED** des Boards leuchtet, solange das Display arbeitet. Tasten, die in dieser Zeit gedrückt werden, zählen nicht.
- Das Hilfsbild gehört zum **Tagesdashboard ab Version 1.49**. Ohne diese Version zeichnet A zwar das Display neu, aber aus dem Bild-Cache (also dasselbe Bild).

## Voraussetzungen

- Raspberry Pi mit Inky Impression 7,3″ und laufendem InkyPi (Weboberfläche auf Port 80), Tagesdashboard 1.49.
- `gpiod` 2.x in InkyPis Python-Umgebung (`/usr/local/inkypi/venv_inkypi`): derselbe Weg wie beim Tastentest; fehlt es, meldet es die Prüfung bei der Installation.
- Der Tastentest (Leitungen 5, 6, 16, 24 und LED 13) war bei dir erfolgreich – das ist die Grundlage.

## Installieren

```bash
cd tasten
sudo bash install.sh
journalctl -u inkypi-tasten -f        # live mitlesen; Strg+C beendet nur das Mitlesen
```

`install.sh` kopiert alles nach `/usr/local/inkypi-tasten/`, prüft mit `--probe` (Einstellungen, Dashboard in der aktiven Playlist, GPIO-Chip) und startet den Dienst.

## Ohne Taste ausprobieren

```bash
sudo /usr/local/inkypi/venv_inkypi/bin/python /usr/local/inkypi-tasten/tasten.py --druck A    # wie Taste A
sudo /usr/local/inkypi/venv_inkypi/bin/python /usr/local/inkypi-tasten/tasten.py --druck D    # wie Taste D
sudo /usr/local/inkypi/venv_inkypi/bin/python /usr/local/inkypi-tasten/tasten.py --probe      # Installationsprüfung
```

Der Dienst darf dabei laufen. Die Ausgabe nennt, was passiert ist (`neu`, `hilfe-auf`, `hilfe-zu`, `nacht`, `frei`, …).

## Wenn etwas nicht geht

- **Taste tut nichts:** `journalctl -u inkypi-tasten -n 50`. Steht dort „Nachtbild – nichts getan“, ist gerade Nacht (Standard 23:00–6:00 Uhr, einstellbar im Dashboard).
- **A zeichnet dasselbe Bild:** Das Dashboard ist älter als 1.49 (Bild-Cache).
- **„Tasten-Leitungen konnten nicht angefordert werden“:** Läuft noch ein Tastentest oder ein zweiter Dienst? Beenden und neu starten.
- **„InkyPi nicht erreichbar“:** `systemctl status inkypi.service`.

## Entfernen

```bash
sudo bash uninstall.sh
```

## Wie es funktioniert

Der Dienst schreibt eine kleine Datei `tasten_zustand.json` neben InkyPis `device.json` (Zähler „neu“ und Ende des Hilfsbilds) und stößt InkyPi an. Das Dashboard liest die Datei beim Zeichnen: Ein neuer Zähler überspringt den Bild-Cache, ein laufendes Hilfsbild wird statt des Dashboards gezeichnet.
