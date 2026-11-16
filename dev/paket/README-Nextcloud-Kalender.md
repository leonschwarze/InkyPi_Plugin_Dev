# Nextcloud Kalender für InkyPi – Version 1.26

Termine per CalDAV aus Nextcloud, als Terminliste (mit Monatsübersicht) oder Woche in 7 Spalten.

## Installieren bzw. aktualisieren

1. Den Ordner `nextcloud_kalender/` aus diesem Paket nach `InkyPi/src/plugins/nextcloud_kalender/` kopieren (vorhandenen Ordner ersetzen).
2. `sudo systemctl restart inkypi.service` (eine Python-Datei hat sich geändert).
3. Das App-Passwort gehört unter **API Keys** (Schlüssel `NEXTCLOUD_APP_PASSWORD`), nicht in die Plugin-Einstellungen.

## Neu in 1.26: abgelehnte Einladungen ausgeblendet

Hast du eine Einladung abgelehnt, bleibt der Termin in Nextcloud stehen – auf dem Display erscheint er jetzt nicht mehr. Bei Serien fehlt nur der einzelne Termin, den du abgelehnt hast. Zugesagte, vorläufige und noch offene Einladungen bleiben sichtbar, ebenso Termine, bei denen nur andere Gäste abgesagt haben.

Woran das Plugin dich erkennt: an der E-Mail-Adresse deines Nextcloud-Kontos (Persönliche Einstellungen → E-Mail). Ist dort keine eingetragen, kann es abgelehnte Einladungen nicht erkennen und zeigt sie wie bisher. Keine neue Einstellung; Ordner ersetzen und `sudo systemctl restart inkypi.service`.

## Neu in 1.11: Umlaute und Akzente sicher

InkyPi sagt dem Browser beim Zeichnen nicht, dass die Seite UTF-8 ist. Bei vielen Akzenten (z. B. französische Terminnamen) konnte Chromium deshalb falsch raten; dann stand überall „Ã©“ statt „é“. Das Plugin gibt den Zeichensatz jetzt selbst an (neue Datei `zeichensatz.py`). Sonst ändert sich nichts, das Bild bleibt gleich, die Einstellungen auch.

## Neu in 1.10: aufgeräumte Einstellungen

- Abschnitte **Nextcloud**, **Ansicht** und **Termine**. „Terminliste / Woche“ ist ein Umschalter; darunter stehen nur die passenden Optionen (Zeitraum und Monatsübersicht bzw. Wochenbeginn).
- Name des Schlüssels, SSL-Prüfung und „Schärfer auf Inky-Displays“ stehen unter **Erweitert**. Der Bereich klappt von selbst auf, wenn dort etwas vom Standard abweicht.
- Alle Einstellungen behalten ihren Namen; nach dem Update ist nichts neu einzustellen.
