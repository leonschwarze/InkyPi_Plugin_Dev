"""Adventskranz und freie Abende (seit 1.29) ohne Rendern.

  python dev/test_advent.py

Prüft: Adventssonntage (bekannte Jahre, Sonderfälle 25.12. bzw. 24.12. am Sonntag, 1990–2099 immer
Sonntage im Abstand von einer Woche, 4. Advent zwischen 18. und 24.12.), Kerzenzahl über die ganze
Adventszeit bis Heiligabend, Grenzen für den Bild-Cache, gültiges SVG (Zahl der Flammen), freie Abende
(Grenzen 18 und 22 Uhr, über Nacht, mehrtägig, ganztägig ein- und mehrtägig, Termin ohne Dauer),
Liste der Tage mit Spannen, Texte, Zusammenfassung der Wochenvorschau (ohne Kalender keine Aussage,
Kurzform des Zeitraums). Die Streupixel prüft dev/kranz_pruefstand.py (braucht Chromium).
"""
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import advent  # noqa: E402
import ansichten  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


# ---------------------------------------------------------------- Adventssonntage
KNOWN = {2022: date(2022, 11, 27), 2023: date(2023, 12, 3), 2024: date(2024, 12, 1), 2025: date(2025, 11, 30),
         2026: date(2026, 11, 29), 2027: date(2027, 11, 28), 2028: date(2028, 12, 3)}
for y, first in KNOWN.items():
    check(f"1. Advent {y} = {first:%d.%m.}", advent.sundays(y)[0] == first)
check("2022: 25.12. ist Sonntag → 4. Advent 18.12.", advent.sundays(2022)[3] == date(2022, 12, 18))
check("2023: 4. Advent = Heiligabend", advent.sundays(2023)[3] == date(2023, 12, 24))
ok = True
for y in range(1990, 2100):
    s = advent.sundays(y)
    ok &= all(d.weekday() == 6 for d in s)
    ok &= all(b - a == timedelta(weeks=1) for a, b in zip(s, s[1:]))
    ok &= date(y, 12, 18) <= s[3] <= date(y, 12, 24)
check("1990–2099: vier Sonntage im Wochenabstand, 4. Advent 18.–24.12.", ok)

# ---------------------------------------------------------------- Kerzen
check("Samstag vor dem 1. Advent: kein Kranz", advent.candles(date(2026, 11, 28)) == 0)
check("1. Advent: 1 Kerze", advent.candles(date(2026, 11, 29)) == 1)
check("Dienstag danach: weiter 1", advent.candles(date(2026, 12, 1)) == 1)
check("2. Advent: 2", advent.candles(date(2026, 12, 6)) == 2)
check("Samstag vor dem 3. Advent: 2", advent.candles(date(2026, 12, 12)) == 2)
check("3. Advent: 3", advent.candles(date(2026, 12, 13)) == 3)
check("4. Advent: 4", advent.candles(date(2026, 12, 20)) == 4)
check("Heiligabend: 4", advent.candles(date(2026, 12, 24)) == 4)
check("1. Weihnachtstag: kein Kranz", advent.candles(date(2026, 12, 25)) == 0)
check("Januar/Sommer: kein Kranz", advent.candles(date(2027, 1, 3)) == 0 and advent.candles(date(2026, 7, 1)) == 0)
check("2023 Heiligabend = 4. Advent: 4", advent.candles(date(2023, 12, 24)) == 4)

# ---------------------------------------------------------------- Cache-Grenzen
b = advent.boundaries(datetime(2026, 11, 28, 22, 0, tzinfo=TZ))
check("Grenze Mitternacht vor dem 1. Advent", b == [datetime(2026, 11, 29, 0, 0, tzinfo=TZ)])
check("keine Grenze mitten in der Woche", advent.boundaries(datetime(2026, 12, 1, 22, 0, tzinfo=TZ)) == [])
check("Grenze nach Heiligabend", datetime(2026, 12, 25, tzinfo=TZ) in advent.boundaries(datetime(2026, 12, 24, 22, tzinfo=TZ)))

# ---------------------------------------------------------------- Zeichnung
for lit in range(0, 5):
    svg = advent.wreath(lit)
    root = ET.fromstring(svg)
    flames = sum(1 for el in root.iter() if el.tag.endswith("path"))
    check(f"SVG mit {lit} Kerzen: gültig, {lit} Flammen", flames == lit and root.get("viewBox") == "0 0 40 36")
check("Farben über CSS-Variablen (Schwarz-Weiß-Modus)", "var(--adv-red" in advent.wreath(2) and "#000" not in advent.wreath(2))


# ---------------------------------------------------------------- freie Abende
def ev(start, end, all_day=False):
    return {"source": {"start": start, "end": end, "all_day": all_day}, "all_day": all_day}


D = date(2026, 12, 2)  # Mittwoch


def at(h, m=0, day=D):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


free = ansichten.free_evening
check("ohne Termine frei", free([], D, TZ))
check("Termin endet 18:00 → frei", free([ev(at(16), at(18))], D, TZ))
check("Termin endet 18:30 → belegt", not free([ev(at(17), at(18, 30))], D, TZ))
check("Termin beginnt 22:00 → frei", free([ev(at(22), at(23))], D, TZ))
check("Termin beginnt 21:59 → belegt", not free([ev(at(21, 59), at(23))], D, TZ))
check("Ratssitzung 17–22 → belegt", not free([ev(at(17), at(22))], D, TZ))
check("Termin ohne Dauer 19:00 → belegt", not free([ev(at(19), at(19))], D, TZ))
check("Termin ohne Dauer 22:00 → frei", free([ev(at(22), at(22))], D, TZ))
check("Nachtzug ab Vortag bis 7:30 → frei", free([ev(at(22, 15, D - timedelta(days=1)), at(7, 30))], D, TZ))
check("Klausur Di 9:00 – Do 17:00 → Mittwoch belegt",
      not free([ev(at(9, 0, D - timedelta(days=1)), at(17, 0, D + timedelta(days=1)))], D, TZ))
check("ganztägig eintägig (Müllabfuhr) → frei",
      free([ev(datetime(2026, 12, 2, tzinfo=TZ), datetime(2026, 12, 3, tzinfo=TZ), True)], D, TZ))
check("ganztägig mehrtägig (Reise) → belegt",
      not free([ev(datetime(2026, 12, 1, tzinfo=TZ), datetime(2026, 12, 4, tzinfo=TZ), True)], D, TZ))
check("Eintrag ohne Rohdaten wird übersprungen", free([{"all_day": False}], D, TZ))

# eigenes Abendfenster (seit cfgVersion 22: freeFrom/freeTo)
from datetime import time  # noqa: E402
late = (time(19), time(0, 30))
check("Fenster 19–0:30: Termin 18–19 → frei", free([ev(at(18), at(19))], D, TZ, late))
check("Fenster 19–0:30: Termin 23:30–1:00 → belegt", not free([ev(at(23, 30), at(1, 0, D + timedelta(days=1)))], D, TZ, late))
check("Fenster 19–0:30: Termin ab 0:30 nachts → frei", free([ev(at(0, 30, D + timedelta(days=1)), at(2, 0, D + timedelta(days=1)))], D, TZ, late))
check("Fenster 17–20: Termin 20:15 → frei", free([ev(at(20, 15), at(21))], D, TZ, (time(17), time(20))))

# ---------------------------------------------------------------- Texte
check("Liste einzeln", ansichten.day_list(["Di", "Sa"]) == "Di, Sa")
check("Liste zwei Nachbarn bleiben einzeln", ansichten.day_list(["Mo", "Di"]) == "Mo, Di")
check("Liste Spanne ab drei", ansichten.day_list(["Mo", "Di", "Mi", "Sa"]) == "Mo–Mi, Sa")
check("Liste Reihenfolge egal", ansichten.day_list(["Sa", "Mo"]) == "Mo, Sa")
check("Text normal", ansichten.free_text(["Mi", "Sa"]) == "Freie Abende: Mi, Sa")
check("Text keine", ansichten.free_text([]) == "keine freien Abende")
check("Text alle", ansichten.free_text(ansichten.KURZ) == "alle Abende frei")


# ---------------------------------------------------------------- Wochenvorschau
def items_for(day):
    if day.weekday() == 1:  # Dienstag Abendtermin
        return [ev(at(19, 0, day), at(21, 0, day))]
    return []


now = datetime(2026, 11, 29, 19, 0, tzinfo=TZ)
wk = ansichten.week(now, [], items_for, None, None, None, None)
check("Zusammenfassung: freie Abende statt Terminzahl", wk["summary"] == ["Freie Abende: Mo, Mi–So"])
check("Zeitraum lang und kurz über zwei Monate", wk["span"] == "30. November – 6. Dezember" and wk["span_short"] == "30.11.–6.12.")
wk2 = ansichten.week(datetime(2026, 11, 15, 19, 0, tzinfo=TZ), [], items_for, None, None, None, None)
check("Kurzform im selben Monat", wk2["span"] == "16.–22. November" and wk2["span_short"] == "16.–22.11.")
wk3 = ansichten.week(now, [], items_for, None, None, None, None, has_calendar=False)
check("ohne Kalender keine Aussage", wk3["summary"] == [] and wk3["free"] is None)
wk4 = ansichten.week(now, [], items_for, None, None, None, None, evening=None)
check("Schalter aus: keine Aussage", wk4["summary"] == [] and wk4["free"] is None)
wk5 = ansichten.week(now, [], items_for, None, None, None, None, evening=(time(21, 30), time(23)))
check("eigenes Fenster wirkt (Di 19–21 Uhr liegt davor)", wk5["summary"] == ["alle Abende frei"])

print()
if FAILED:
    print(f"{len(FAILED)} Fehler:", *FAILED, sep="\n  ")
    sys.exit(1)
print("Alles in Ordnung.")
