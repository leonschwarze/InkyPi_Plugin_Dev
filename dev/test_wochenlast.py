"""Wie voll ist die Woche (wochenlast.py) und Laufen der Woche (laufbilanz.py) ohne Rendern.

  python dev/test_wochenlast.py

Wochenlast: Überschneidungen einmal, nur 7–23 Uhr (Nachtzug), ganztägige zählen nicht, Termine über
Mitternacht, Schnitt nur aus Wochen ab 2 h und erst ab 3 Wochen, Wörter an den Grenzen, Texte.
Laufbuch: Zeilenformate, Kommentare, Unsinn, Woche Mo–So, Schnitt der vier Wochen davor, keine Zeile
ohne Läufe, Pfad bereinigen, Abruf über WebDAV gegen den Testserver (Datei fehlt, Ausfall,
Zwischenspeicher, nur an die Nextcloud-Adresse).
"""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))
sys.path.insert(0, str(ROOT / "nextcloud_kalender"))
sys.path.insert(0, str(Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"))  # base_plugin für den Kalender

import laufbilanz  # noqa: E402
import status  # noqa: E402
import wochenlast  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def ev(d, h1, m1, h2, m2, days=0, all_day=False):
    s = datetime(d.year, d.month, d.day, h1, m1, tzinfo=TZ)
    e = datetime(d.year, d.month, d.day, h2, m2, tzinfo=TZ) + timedelta(days=days)
    return {"start": s, "end": e, "all_day": all_day}


MON = date(2026, 11, 23)
# ---------------------------------------------------------------- Stunden eines Tages
check("ein Termin 10–11 → 1 h", wochenlast.day_hours([ev(MON, 10, 0, 11, 0)], MON, TZ) == 1)
check("Überschneidung 17–20 und 18:30–20 → 3 h",
      wochenlast.day_hours([ev(MON, 17, 0, 20, 0), ev(MON, 18, 30, 20, 0)], MON, TZ) == 3)
check("berührend 9–10 und 10–11 → 2 h", wochenlast.day_hours([ev(MON, 9, 0, 10, 0), ev(MON, 10, 0, 11, 0)], MON, TZ) == 2)
night = ev(MON, 22, 15, 7, 30, days=1)
check("Nachtzug 22:15–7:30: Abfahrtstag 0,75 h", wochenlast.day_hours([night], MON, TZ) == 0.75)
check("Nachtzug: Folgetag 0,5 h (7–7:30)", wochenlast.day_hours([night], MON + timedelta(days=1), TZ) == 0.5)
check("ganztägig zählt nicht",
      wochenlast.day_hours([dict(ev(MON, 0, 0, 0, 0, days=1), all_day=True)], MON, TZ) == 0)
check("Termin vor 7 Uhr zählt ab 7", wochenlast.day_hours([ev(MON, 6, 0, 8, 0)], MON, TZ) == 1)
check("Wochenstunden Mo–So", wochenlast.week_hours([ev(MON, 10, 0, 12, 0), ev(MON + timedelta(days=6), 20, 0, 23, 30)], MON, TZ)
      == [2, 0, 0, 0, 0, 0, 3])

# ---------------------------------------------------------------- Schnitt
hist = []
for back, hours in ((1, 10), (2, 12), (3, 1), (4, 14)):
    m = MON - timedelta(days=7 * back)
    hist.append(ev(m, 8, 0, 8 + hours, 0) if hours <= 15 else None)
avg = wochenlast.average(hist, MON, TZ)
check("Schnitt ohne die Urlaubswoche (1 h): (10 + 12 + 14) / 3 = 12", avg == 12)
check("weniger als drei gültige Wochen → kein Vergleich", wochenlast.average(hist[:2], MON, TZ) is None)
check("ohne vergangene Termine → None", wochenlast.average([], MON, TZ) is None)

for total, word in ((15.6, "deutlich mehr als sonst"), (15.5, "mehr als sonst"), (13.2, "mehr als sonst"),
                    (13.1, "wie sonst"), (10.8, "wie sonst"), (10.7, "ruhiger als sonst"), (8.4, "ruhiger als sonst"),
                    (8.3, "deutlich ruhiger als sonst"), (0, "deutlich ruhiger als sonst")):
    check(f"{total} h gegen Ø 12 h → „{word}“", wochenlast.compare(total, 12) == word)
check("ohne Schnitt kein Wort", wochenlast.compare(20, None) is None)

s = wochenlast.summary([4, 9, 4, 0, 0, 2, 2.5], 11.6)
check("Text: 21,5 h → „22 h Termine“", s["total_text"] == "22 h Termine")
check("Text: Ø 12 h", s["avg_text"] == "Ø 12 h")
check("Text: vollster Tag Di (9 h)", s["peak_text"] == "vollster Tag Di (9 h)")
check("Stufe „hoch“ bei deutlich mehr (rot)", s["level"] == "hoch")
check("unter 10 h halbe Stunden", wochenlast.fmt_h(4.6) == "4,5 h" and wochenlast.fmt_h(2) == "2 h")
check("leere Woche: kein vollster Tag", wochenlast.summary([0] * 7, None)["peak_text"] == "")

# ---------------------------------------------------------------- Laufbuch lesen
text = """# Laufbuch
2026-11-23;5,2;31
2026-11-25 6.8 km 41 min
24.11.2026;3
2026-11-26;abc
kaputt
2026-11-27;0
2026-11-28;250
2026-02-30;5
"""
runs = laufbilanz.parse(text)
check("parse: drei gültige Läufe", [(d.isoformat(), km) for d, km, _ in runs] ==
      [("2026-11-23", 5.2), ("2026-11-25", 6.8), ("2026-11-24", 3.0)])
check("parse: Minuten optional", runs[2][2] is None and runs[0][2] == 31)

SUN = date(2026, 11, 29)
log = laufbilanz.parse("\n".join(
    [f"{(SUN - timedelta(days=d)).isoformat()};{km}" for d, km in ((0, 5), (2, 6), (4, 4))]     # diese Woche 15
    + [f"{(SUN - timedelta(days=7 + d)).isoformat()};{km}" for d, km in ((1, 10), (3, 2))]      # Woche -1: 12
    + [f"{(SUN - timedelta(days=21)).isoformat()};8"]                                            # Woche -3: 8
    + [f"{(SUN - timedelta(days=42)).isoformat()};30"]                                           # zu alt
    + [f"{(SUN + timedelta(days=1)).isoformat()};9"]))                                           # Zukunft
s = laufbilanz.summary(log, SUN)
check("Woche: 15 km in 3 Läufen", s and s["km"] == 15 and s["count_text"] == "3 Läufe")
check("Schnitt der vier Wochen davor (12 + 0 + 8 + 0) / 4 = 5 km", s and s["avg_text"] == "Ø 5 km")
check("Texte: „15 km“", s and s["km_text"] == "15 km")
s = laufbilanz.summary(log, SUN + timedelta(days=7))
check("Lauf am Montag nach der Vorschau zählt in die nächste Woche", s and s["count_text"] == "1 Lauf" and s["km"] == 9)
s = laufbilanz.summary(log, SUN + timedelta(days=14))
check("Woche ohne Lauf, aber vorher gelaufen: „kein Lauf“", s and s["count_text"] == "kein Lauf" and s["km"] == 0)
check("fünf Wochen ohne Lauf → keine Zeile", laufbilanz.summary(log, SUN + timedelta(days=70)) is None)
check("leeres Laufbuch → keine Zeile", laufbilanz.summary([], SUN) is None)
check("1 Lauf (Einzahl)", laufbilanz.summary(laufbilanz.parse("2026-11-29;5,25"), SUN)["count_text"] == "1 Lauf")
check("km mit einer Nachkommastelle", laufbilanz.fmt_km(17.5) == "17,5 km" and laufbilanz.fmt_km(5.25) == "5,2 km")

check("Pfad: führender / weg", laufbilanz.clean_path("/Sport/laufen.txt") == "Sport/laufen.txt")
check("Pfad: .. → Standard", laufbilanz.clean_path("../../etc/passwd") == laufbilanz.DEFAULT_PATH)
check("Pfad: leer → Standard", laufbilanz.clean_path("") == laufbilanz.DEFAULT_PATH)
check("Pfad: Adresse → Standard", laufbilanz.clean_path("https://evil.example/x") == laufbilanz.DEFAULT_PATH)
check("Pfad: Umlaute erlaubt", laufbilanz.clean_path("Läufe/2026.txt") == "Läufe/2026.txt")

# ---------------------------------------------------------------- Abruf über WebDAV (Testserver)
import caldav_server  # noqa: E402
import nextcloud_kalender as nc  # noqa: E402

base = date(2026, 11, 22)
url, user, password = caldav_server.start(base)
client = nc.CalDavClient(nc.dav_root(url), user, password)
seen = []
orig = client.session.get


def spy(u, **kw):
    seen.append(u)
    return orig(u, **kw)


client.session.get = spy
for kind, want in (("normal", 17.5), ("viel", 26.0), ("leer", None)):
    os.environ["DEV_LAUF"] = kind
    laufbilanz.reset()
    s = laufbilanz.summary(laufbilanz.load(client, user, "InkyPi/laufen.txt"), base)
    check(f"WebDAV {kind}: {want} km", (s["km"] if s and s["count"] else None) == want)
check("WebDAV: Adresse unter /remote.php/dav/files/<user>/",
      seen and all(u.startswith(url + "/remote.php/dav/files/" + user + "/InkyPi/laufen.txt") for u in seen))
os.environ["DEV_LAUF"] = "fehlt"
laufbilanz.reset()
status.reset()
status.begin()
check("Datei fehlt → None", laufbilanz.load(client, user, "InkyPi/laufen.txt") is None)
status.commit(datetime(2026, 11, 22, 19, 0, tzinfo=TZ))
check("Datei fehlt ist kein Ausfall", status.report(datetime(2026, 11, 22, 19, 0, tzinfo=TZ)) == [])
os.environ["DEV_LAUF"] = "down"
laufbilanz.reset()
status.begin()
check("Ausfall → None", laufbilanz.load(client, user, "InkyPi/laufen.txt") is None)
status.commit(datetime(2026, 11, 22, 19, 0, tzinfo=TZ))
check("Ausfall → Statusanzeige „Laufbuch“", [x["name"] for x in status.report(datetime(2026, 11, 22, 19, 0, tzinfo=TZ))] == ["Laufbuch"])
os.environ["DEV_LAUF"] = "normal"
n = len(seen)
laufbilanz.load(client, user, "InkyPi/laufen.txt")
check("Zwischenspeicher: auch Ausfälle 30 min", len(seen) == n)

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
