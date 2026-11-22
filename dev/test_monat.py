"""Monatsbild (tagesdashboard/monat.py) ohne Rendern.

  python dev/test_monat.py

Prüft: Feiertage NRW (2026, 2027, bewegliche über Ostern), Raster (Wochen Mo–So, Tage außerhalb des
Monats, heute, Wochenende), Punkte je Termin (ganztägige zuerst), mehrtägige als Band (Anfang/Ende,
am Monatsrand abgeschnitten), Geburtstage, Liste nach Datum, Zusammenfassung (Einzahl/Mehrzahl, freie
Abende), Tage für die Kalenderabfrage, Grenzen für den Bild-Cache – und mit dem echten generate_image,
wann das Monatsbild kommt (am Ersten im Fenster; Nachtbild davor, Wochenvorschau am Abend, Schalter aus).
"""
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import monat  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


# ---------------------------------------------------------------- Feiertage
h26, h27 = monat.holidays(2026), monat.holidays(2027)
check("2026: elf Feiertage in NRW", len(h26) == 11)
check("2026: Karfreitag 3.4., Ostermontag 6.4.", h26.get(date(2026, 4, 3)) == "Karfreitag" and date(2026, 4, 6) in h26)
check("2026: Fronleichnam 4.6.", h26.get(date(2026, 6, 4)) == "Fronleichnam")
check("2027: Himmelfahrt 6.5., Pfingstmontag 17.5.", date(2027, 5, 6) in h27 and date(2027, 5, 17) in h27)
check("2027: Allerheiligen, 1./2. Weihnachtstag", all(d in h27 for d in (date(2027, 11, 1), date(2027, 12, 25), date(2027, 12, 26))))
check("Rosenmontag ist kein Feiertag", date(2027, 2, 8) not in h27)


# ---------------------------------------------------------------- Raster
def ev(d, h1, h2, color="#E3001B", all_day=False, days=1):
    if all_day:
        return {"start": datetime.combine(d, time.min, TZ), "end": datetime.combine(d + timedelta(days=days), time.min, TZ),
                "all_day": True, "title": "Reise", "color": color}
    return {"start": datetime.combine(d, time(h1), TZ), "end": datetime.combine(d, time(h2), TZ),
            "all_day": False, "title": "Termin", "color": color}


events = [ev(date(2026, 12, 1), 10, 11, "#0082C9"), ev(date(2026, 12, 1), 17, 20),
          ev(date(2026, 12, 1), 0, 0, "#2E9E3F", all_day=True),
          ev(date(2026, 12, 23), 0, 0, "#2E9E3F", all_day=True, days=5),       # 23.–27.12.
          ev(date(2026, 12, 30), 0, 0, "#0082C9", all_day=True, days=4)]       # 30.12.–2.1.
bdays = [{"name": "Mia", "day": 12, "month": 12, "year": None}, {"name": "Papa", "day": 20, "month": 12, "year": 1961}]
M = monat.grid(2026, 12, events, TZ, birthdays=bdays, today=date(2026, 12, 1),
               free_evening=lambda items, d: not any(it["source"]["start"].hour >= 17 for it in items
                                                     if not it["source"]["all_day"]))
weeks = M["weeks"]
check("Dezember 2026: fünf Wochen ab Mo 30.11.", len(weeks) == 5 and weeks[0]["days"][0]["date"] == date(2026, 11, 30))
check("30.11. liegt außerhalb", not weeks[0]["days"][0]["inside"])
day1 = weeks[0]["days"][1]
check("1.12. ist heute", day1["today"] and day1["num"] == 1)
check("1.12.: ganztägig zuerst, dann nach Beginn", day1["dots"] == ["#2E9E3F", "#0082C9", "#E3001B"])
check("Wochenende markiert (5.12. Sa)", weeks[0]["days"][5]["weekend"])
cells = {c["date"]: c for w in weeks for c in w["days"]}
check("Band 23.12.: Anfang", cells[date(2026, 12, 23)]["band"][0]["start"] and not cells[date(2026, 12, 23)]["band"][0]["end"])
check("Band 27.12.: Ende", cells[date(2026, 12, 27)]["band"][0]["end"])
check("Band 31.12.: kein Ende im Dezember (läuft bis 2.1.)", not cells[date(2026, 12, 31)]["band"][-1]["end"])
check("Reise belegt keinen Punkt", cells[date(2026, 12, 24)]["dots"] == [])
check("Feiertag 25.12.", cells[date(2026, 12, 25)]["holiday"] == "1. Weihnachtstag")
check("Geburtstag Mia am 12.12.", [b["name"] for b in cells[date(2026, 12, 12)]["bdays"]] == ["Mia"])
check("Liste nach Datum", [e["day"] for e in M["entries"]] ==
      ["12.12.", "20.12.", "23.–27.12.", "25.12.", "26.12.", "30.–31.12."])
check("Liste: Alter bei Papa", any(e["text"] == "Papa (65)" for e in M["entries"]))
check("Liste: Feiertage als hol", [e["kind"] for e in M["entries"]].count("hol") == 2)
check("Zusammenfassung: 3 Termine (ganztägig eintägig zählt, Reisen nicht)", M["summary"][0] == "3 Termine")
check("Zusammenfassung: 30 freie Abende", M["summary"][1] == "30 freie Abende")
check("Zusammenfassung: Feiertage 25., 26.", M["summary"][2] == "Feiertage 25., 26.")
M1 = monat.grid(2027, 2, [ev(date(2027, 2, 3), 9, 10)], TZ)
check("Einzahl: 1 Termin; ohne Abendfenster keine Aussage", M1["summary"] == ["1 Termin"])
check("Februar 2027: vier Wochen (1.2. ist Montag)", len(M1["weeks"]) == 4)
check("ohne Einträge: leere Liste", M1["entries"] == [])

check("Kalenderabfrage am 1.12.: 31 Tage", monat.days_needed(date(2026, 12, 1)) == 31)
check("Kalenderabfrage am 1.2.2027: 28 Tage", monat.days_needed(date(2027, 2, 1)) == 28)
b = monat.boundaries(datetime(2026, 11, 30, 21, 0, tzinfo=TZ), time(6), time(10))
check("Grenzen am Vorabend: morgen 6 und 10 Uhr",
      b == [datetime(2026, 12, 1, 6, 0, tzinfo=TZ), datetime(2026, 12, 1, 10, 0, tzinfo=TZ)])
check("Grenzen mitten im Monat: keine", monat.boundaries(datetime(2026, 12, 14, 9, 0, tzinfo=TZ), time(6), time(10)) == [])

# ---------------------------------------------------------------- Ende zu Ende: wann kommt das Monatsbild?
sys.path.insert(0, str(INKYPI))
import render  # noqa: E402

render.link_plugins(INKYPI)
os.chdir(INKYPI)
from PIL import Image  # noqa: E402

START = datetime(2026, 11, 1, 7, 0, tzinfo=TZ)  # Sonntag, der Erste
import mock_brightsky, mock_news, mock_radar, mock_luft, mock_pollen, mock_pegel, mock_polar, mock_nina  # noqa: E402,E401
for m, k in ((mock_brightsky, "herbst"), (mock_news, "normal"), (mock_radar, "trocken"), (mock_luft, "gut"),
             (mock_pollen, "gut"), (mock_pegel, "keine"), (mock_polar, "keine"), (mock_nina, "keine")):
    m.install(START, k)
import caldav_server  # noqa: E402
url, user, password = caldav_server.start(START.date())
module = __import__("plugins.tagesdashboard.tagesdashboard", fromlist=["x"])
import mock_ziel, mock_pi  # noqa: E402,E401
mock_ziel.install(START)
mock_pi.install(START, "ok", __import__("plugins.tagesdashboard.pizustand", fromlist=["x"]))
clock = {"now": START}
module.Tagesdashboard.current_time = lambda self, tz: clock["now"].astimezone(tz)
plugin = module.Tagesdashboard({"id": "tagesdashboard"})
views = []


def fake_render(dimensions, html, css, params):
    views.append("monat" if params.get("month") else "nacht" if params.get("night") else
                 "woche" if params.get("week") else "normal")
    return Image.new("RGB", tuple(dimensions), "white")


plugin.render_image = fake_render
cfg = render.DevConfig((800, 480), "horizontal", {"NEXTCLOUD_APP_PASSWORD": password})
base = dict(render.BASE_SETTINGS, nextcloudUrl=url, username=user)


def view(when, **extra):
    clock["now"] = when
    module._IMAGE_CACHE.clear()
    module._NIGHT_CACHE.clear()
    plugin.generate_image(dict(base, **extra), cfg)
    return views[-1]


check("So 1.11. 5:30 → Nachtbild hat Vorrang", view(START.replace(hour=5, minute=30)) == "nacht")
check("So 1.11. 6:00 → Monatsbild", view(START.replace(hour=6)) == "monat")
check("So 1.11. 9:59 → Monatsbild", view(START.replace(hour=9, minute=59)) == "monat")
check("So 1.11. 10:00 → normal", view(START.replace(hour=10)) == "normal")
check("So 1.11. 19:00 → Wochenvorschau", view(START.replace(hour=19)) == "woche")
check("Mo 2.11. 7:00 → normal", view(START + timedelta(days=1)) == "normal")
check("Schalter aus → normal", view(START, monthEnabled="false") == "normal")
check("eigenes Fenster 7–8: 7:30 Monatsbild", view(START.replace(minute=30), monthFrom="07:00", monthTo="08:00") == "monat")

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
