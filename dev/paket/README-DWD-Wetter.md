# DWD Wetter für InkyPi – Version 1.11

Wetter vom Deutschen Wetterdienst (über Bright Sky) mit amtlichen Warnungen, Messwert-Kacheln, Stundenverlauf und Vorhersage.

## Installieren bzw. aktualisieren

1. Den Ordner `dwd_wetter/` aus diesem Paket nach `InkyPi/src/plugins/dwd_wetter/` kopieren (vorhandenen Ordner ersetzen).
2. `sudo systemctl restart inkypi.service` (eine Python-Datei hat sich geändert).
3. Die Plugin-Einstellungen öffnen, kurz prüfen und speichern.

## Neu in 1.11: Umlaute und Akzente sicher

InkyPi sagt dem Browser beim Zeichnen nicht, dass die Seite UTF-8 ist. Bei vielen Akzenten (z. B. französische Terminnamen) konnte Chromium deshalb falsch raten; dann stand überall „Ã©“ statt „é“. Das Plugin gibt den Zeichensatz jetzt selbst an (neue Datei `zeichensatz.py`). Sonst ändert sich nichts, das Bild bleibt gleich, die Einstellungen auch.

## Neu in 1.10: aufgeräumte Einstellungen

- Abschnitte **Ort** und **Inhalt**, eine Option pro Zeile. Die Kacheln stehen unter „Messwerte als Kacheln“, Wettersymbole und Nachtstunden unter „Stundenverlauf“. Ist die Hauptoption aus, werden die Unteroptionen blass; ihre Werte bleiben gespeichert.
- „Schärfer auf Inky-Displays“ steht unter **Erweitert**. Der Bereich klappt von selbst auf, wenn die Option abgeschaltet ist.
- **Titel im Kopf** ist jetzt ein einziges Feld: leer = Ortsname vom DWD, sonst dein eigener Titel. Die Ortssuche schreibt nicht mehr ins Titelfeld.

**Bestehende Einstellungen bleiben erhalten.** Das Plugin liest das alte Format weiter, bis du neu speicherst, und zeigt bis dahin dasselbe Bild. War „Ortsname vom DWD“ gewählt und stand trotzdem ein Text im Titelfeld, bleibt das Feld leer, wie bisher wirksam. Der alte Text wird dir mit „… übernehmen“ angeboten.
