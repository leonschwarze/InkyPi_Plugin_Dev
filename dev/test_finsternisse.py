"""Tests für finsternisse.py (Mondfinsternisse im Nachtbild) ohne Rendern."""
import sys
from datetime import date, timedelta

sys.path.insert(0, "tagesdashboard")
import finsternisse  # noqa: E402

FAILED = []


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


# ----------------------------------------------------------------------
# next_eclipse: Abstand und Fundstelle
# ----------------------------------------------------------------------
# Erste Finsternis in der Tabelle: 21.02.2027, Halbschattenfinsternis, nicht stark.
weit_weg = finsternisse.next_eclipse(date(2026, 11, 13))
check("Mehr als 45 Tage entfernt -> None", weit_weg is None)

knapp_davor = finsternisse.next_eclipse(date(2027, 1, 7))  # 45 Tage vor dem 21.2.
check("Genau an der Grenze (45 Tage) -> gefunden", knapp_davor is not None)
check("Grenze: at_peak ist False", knapp_davor is not None and knapp_davor["at_peak"] is False)

zu_frueh = finsternisse.next_eclipse(date(2027, 1, 6))  # 46 Tage vor dem 21.2.
check("46 Tage entfernt -> None", zu_frueh is None)

# ----------------------------------------------------------------------
# Countdown-Text und Grammatik
# ----------------------------------------------------------------------
info = finsternisse.next_eclipse(date(2027, 1, 20))  # 32 Tage vor dem 21.2.
check("Countdown-Text nennt Tage und Datum",
      info is not None and info["text"] == "Mondfinsternis in 32 Tagen (21.2.): Halbschattenfinsternis · 0:13 Uhr, kaum wahrnehmbar")
check("Nicht stark (Halbschatten)", info is not None and info["stark"] is False)

ein_tag = finsternisse.next_eclipse(date(2027, 2, 20))
check("Einzahl 'Tag' statt 'Tagen'", ein_tag is not None and "in 1 Tag (" in ein_tag["text"])

# ----------------------------------------------------------------------
# Die Nacht selbst (at_peak)
# ----------------------------------------------------------------------
heute = finsternisse.next_eclipse(date(2027, 2, 21))
check("Am Finsternistag selbst: at_peak", heute is not None and heute["at_peak"] is True)
check("Text 'heute Nacht' statt Countdown",
      heute is not None and heute["text"] == "Mondfinsternis heute Nacht: Halbschattenfinsternis · 0:13 Uhr, kaum wahrnehmbar")

# Die Nacht einer Finsternis lässt sich auf zwei Arten lesen (wie bei meteore._at_peak): Je nach
# Uhrzeit von "jetzt" trägt dieselbe physische Nacht das Datum des Ereignisses oder den Folgetag.
tag_danach = finsternisse.next_eclipse(date(2027, 2, 22))
check("Folgetag zählt noch als dieselbe Nacht (Ambiguität wie bei den Meteorströmen)",
      tag_danach is not None and tag_danach["at_peak"] and tag_danach["date"] == date(2027, 2, 21))

# Zwei Tage danach ist die Nacht endgültig vorbei; die nächste Finsternis ist weit entfernt.
zwei_tage_danach = finsternisse.next_eclipse(date(2027, 2, 23))
check("Zwei Tage danach: vorbei, nächster Termin zu weit entfernt -> None", zwei_tage_danach is None)

# ----------------------------------------------------------------------
# Totale Mondfinsternis (stark) am 31.12.2028
# ----------------------------------------------------------------------
total_bald = finsternisse.next_eclipse(date(2028, 12, 20))
check("Totale Mondfinsternis als stark markiert", total_bald is not None and total_bald["stark"] is True)
check("Art korrekt übernommen", total_bald is not None and total_bald["kind"] == "totale Mondfinsternis")

total_heute = finsternisse.next_eclipse(date(2028, 12, 31))
check("Totale Mondfinsternis: at_peak und stark", total_heute is not None and total_heute["at_peak"] and total_heute["stark"])

# ----------------------------------------------------------------------
# Partielle Mondfinsternis (nicht stark) am 15.06.2030 -- letzter Eintrag der Tabelle
# ----------------------------------------------------------------------
partiell = finsternisse.next_eclipse(date(2030, 6, 15))
check("Partielle Mondfinsternis nicht stark", partiell is not None and partiell["stark"] is False)

nach_tabelle = finsternisse.next_eclipse(date(2030, 6, 17))
check("Zwei Tage nach der letzten Tabellenzeile -> None (Tabelle muss irgendwann aufgefrischt werden)",
      nach_tabelle is None)

# ----------------------------------------------------------------------
# show_blood_moon
# ----------------------------------------------------------------------
check("Blutmond bei totaler Finsternis in der Nacht selbst", finsternisse.show_blood_moon(total_heute))
check("Kein Blutmond bei Halbschattenfinsternis (auch am Tag selbst)", not finsternisse.show_blood_moon(heute))
check("Kein Blutmond vor der Nacht selbst (nur Countdown)", not finsternisse.show_blood_moon(total_bald))
check("Kein Blutmond ohne Finsternis (None)", not finsternisse.show_blood_moon(None))
check("Kein Blutmond bei partieller Finsternis", not finsternisse.show_blood_moon(partiell))

# ----------------------------------------------------------------------
# Tabelle in sich konsistent: chronologisch sortiert, keine Dubletten
# ----------------------------------------------------------------------
dates = [e[0] for e in finsternisse.ECLIPSES]
check("ECLIPSES ist chronologisch sortiert", dates == sorted(dates))
check("ECLIPSES hat keine doppelten Daten", len(dates) == len(set(dates)))
check("Alle Einträge liegen in der Zukunft ab dem Recherchestand (November 2026)",
      all(d > date(2026, 11, 13) for d in dates))

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER: {', '.join(FAILED)}")
    sys.exit(1)
print("ALLE TESTS OK")
