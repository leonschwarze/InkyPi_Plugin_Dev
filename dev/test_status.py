"""Statusanzeige im Kopf (tagesdashboard/status.py) ohne Rendern.

  python dev/test_status.py

Prüft: zwei Stufen (sofort Punkt + Name, nach etwa 2 Stunden „seit … nicht erreichbar“, eine Minute
Toleranz); Erfolg beendet den Ausfall; Teilausfall in einer Runde zählt als Ausfall; nur Quellen,
die in dieser Runde gebraucht werden, erscheinen; ein Ausfall nach langer Pause (Zug nur dienstags)
beginnt neu; Uhrzeiten über Mitternacht; Grenzen für den Bild-Cache; höchstens drei Einträge.
Dazu der echte Weg durch die Module (Radar, Luft, Pollen, Nachrichten, Strecke, Zug, Anfahrt) mit
einer Sitzung, die nie antwortet bzw. HTTP 503 liefert – und dass Zwischenspeicher, die auch
Fehlschläge halten (Strecke, Luft, Pollen), den Ausfall weiter anzeigen.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import requests  # noqa: E402

import anfahrt  # noqa: E402
import bahn  # noqa: E402
import luft  # noqa: E402
import nachrichten  # noqa: E402
import pollen  # noqa: E402
import radar  # noqa: E402
import status  # noqa: E402
import strecke  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FEHLER {name}: {got!r} != {want!r}")
    else:
        print(f"ok     {name}")


def at(hhmm, day=12):
    h, m = map(int, hhmm.split(":"))
    return datetime(2026, 11, day, h, m, tzinfo=TZ)


def runde(now, *events):
    """Eine Aktualisierung: events = ("ok"|"fail"|"use", quelle)."""
    status.begin()
    for kind, src in events:
        getattr(status, kind)(src) if kind != "fail" else status.fail(src, "kaputt")
    status.commit(now)
    return status.report(now)


def kurz(rep):
    return [(e["name"], e["since"], e["long"]) for e in rep]


# ---------------------------------------------------------------- Stufen
status.reset()
check("ohne Fehler nichts", runde(at("9:00"), ("ok", "Kalender"), ("ok", "Wetter")), [])
check("erster Fehler: sofort Punkt + Name", kurz(runde(at("9:10"), ("fail", "Kalender"), ("ok", "Wetter"))),
      [("Kalender", "9:10", False)])
check("1:45 später noch kurz", kurz(runde(at("10:55"), ("fail", "Kalender"))), [("Kalender", "9:10", False)])
check("1:59 später schon lang (1 min Toleranz)", kurz(runde(at("11:09"), ("fail", "Kalender"))),
      [("Kalender", "9:10", True)])
check("Zwischenspeicher antwortet (nur use): bleibt", kurz(runde(at("11:25"), ("use", "Kalender"))),
      [("Kalender", "9:10", True)])
check("Erfolg beendet den Ausfall", runde(at("11:40"), ("ok", "Kalender")), [])
check("neuer Fehler beginnt neu", kurz(runde(at("11:55"), ("fail", "Kalender"))), [("Kalender", "11:55", False)])

# ---------------------------------------------------------------- Teilausfall, Reihenfolge, Grenze
status.reset()
check("ok + fail in einer Runde = Ausfall", kurz(runde(at("8:00"), ("ok", "Anfahrt"), ("fail", "Anfahrt"))),
      [("Anfahrt", "8:00", False)])
check("fail + ok in einer Runde = Ausfall", kurz(runde(at("8:15"), ("fail", "Anfahrt"), ("ok", "Anfahrt"))),
      [("Anfahrt", "8:00", False)])
rep = runde(at("8:30"), ("fail", "Radar"), ("fail", "Anfahrt"), ("fail", "GA"), ("fail", "WDR"))
check("älteste zuerst, höchstens drei", [e["name"] for e in rep][0], "Anfahrt")
check("höchstens drei", len(rep), 3)
check("Grenze für den Bild-Cache", sorted(status.boundaries(at("8:30")))[0], at("10:00"))

# ---------------------------------------------------------------- nur gebrauchte Quellen
status.reset()
runde(at("7:40", day=10), ("fail", "Zug"), ("ok", "Wetter"))
check("Zug außerhalb des Fensters nicht im Kopf", runde(at("8:30", day=10), ("ok", "Wetter")), [])
check("…aber noch gemerkt", "Zug" in status._state, True)
check("eine Woche später: neuer Ausfall statt „seit Di“",
      kurz(runde(at("7:40", day=17), ("fail", "Zug"))), [("Zug", "7:40", False)])
status.reset()
runde(at("22:00", day=11), ("fail", "Radar"))
check("über Nacht ohne Radar (>6 h): neu", kurz(runde(at("6:15"), ("fail", "Radar"))), [("Radar", "6:15", False)])
status.reset()
runde(at("22:40", day=11), ("fail", "Kalender"))
runde(at("2:40"), ("fail", "Kalender"))
check("über Mitternacht: „gestern“", kurz(runde(at("6:00"), ("fail", "Kalender"))),
      [("Kalender", "gestern 22:40", True)])
check("Wochentag", status.since_text(at("9:10", day=9), at("9:10")), "Mo 9:10")
check("älter als eine Woche: Datum", status.since_text(at("9:10", day=2), at("9:10")), "2.11.")


# ---------------------------------------------------------------- echte Module
class Down(requests.Session):
    """Antwortet nie (wie ohne Netz)."""
    def get(self, *a, **k):
        raise requests.ConnectionError("kein Netz")


class Resp:
    status_code = 503
    content = b"Service Unavailable"

    def json(self):
        raise ValueError("kein JSON")


class Busy(requests.Session):
    """Antwortet mit HTTP 503."""
    def get(self, *a, **k):
        return Resp()


def namen(now):
    status.commit(now)
    return [e["name"] for e in status.report(now)]


now = at("10:00")
opt = lambda d: (lambda k: d.get(k, ""))  # noqa: E731
flag = lambda d: (lambda k: d.get(k, "false") == "true")  # noqa: E731

for session, label in ((Down(), "ohne Netz"), (Busy(), "HTTP 503")):
    status.reset()
    for mod in (radar, luft, pollen, nachrichten, strecke):
        mod._cache.clear()
    status.begin()
    try:
        radar.fetch(50.73, 7.10, now, session)
    except Exception:
        pass
    s = {"airEnabled": "true", "airRadius": "3", "airLevel": "3", "airStation": "DENW062"}
    luft.load(luft.read_config(opt(s), flag(s), 50.73, 7.10), now, [], session)
    ps = {"pollenEnabled": "true", "pollenLevel": "1", **{f"pollen{t}": "true" for t in pollen.TYPES}}
    pollen.load(pollen.read_config(opt(ps), flag(ps)), now, session)
    s = {"newsEnabled": "true", "newsFrEnabled": "true", "newsFrom": "06:00", "newsTo": "09:30",
         "newsWeekendFrom": "08:00", "newsWeekendTo": "10:30"}
    nachrichten.load(nachrichten.read_config(opt(s), flag(s), bahn.parse_hhmm), now, session)
    strecke.fetch(session, strecke.line_key("RE", "5"))
    check(f"{label}: alle Quellen gemeldet", namen(now),
          ["Radar", "Luftsensoren", "UBA-Station"])  # nur drei im Kopf; die anderen stehen im Zustand
    check(f"{label}: Zustand vollständig", sorted(status._state),
          sorted(["Radar", "Luftsensoren", "UBA-Station", "Pollen", "GA", "WDR", "tagesschau", "franceinfo",
                  "Strecke"]))
    # Nächste Runde: Strecke, Luft und Pollen antworten aus dem Zwischenspeicher (auch Fehlschläge)
    status.begin()
    strecke.fetch(session, strecke.line_key("RE", "5"))
    pollen.load(pollen.read_config(opt(ps), flag(ps)), at("10:05"), session)
    check(f"{label}: Zwischenspeicher hält den Ausfall sichtbar (gleicher Beginn: Reihenfolge der Abrufe)",
          namen(at("10:05")), ["Strecke", "Pollen"])

# Zug: Bahn nicht erreichbar -> „Zug“
status.reset()
s = {"trainEnabled": "true", "trainLine": "RE 5", "trainTime": "08:04", "trainFrom": "06:30", "trainTo": "08:15",
     "trainDi": "true", "trainStation": "Bonn Hbf", "trainTarget": "Düsseldorf Hbf", "trainAlerts": "true",
     "trainRoute": "true"}
status.begin()
card = bahn.load(bahn.read_config(opt(s), flag(s)), at("7:40", day=10), TZ, session=Down())
check("Zug: Karte sagt „Bahn nicht erreichbar“", card["note"], "Bahn nicht erreichbar")
check("Zug: Statusanzeige", namen(at("7:40", day=10)), ["Zug"])

# Anfahrt: Transitous nicht erreichbar -> „Anfahrt“ (Schätzung läuft weiter)
status.reset()
anfahrt._GEO.clear()
anfahrt._BIKE.clear()
cfg = anfahrt.read_config(opt({"tripEnabled": "true"}), flag({"tripEnabled": "true"}), 50.73, 7.10)
status.begin()
check("Anfahrt: Ort ohne Netz = None", anfahrt.resolve(Down(), "Stadthaus Bonn", cfg), None)
mins, est = anfahrt.bike_minutes(Down(), (50.73, 7.10), (50.74, 7.09), at("16:00"), TZ)
check("Anfahrt: Radzeit geschätzt", est, True)
check("Anfahrt: Statusanzeige", namen(now), ["Anfahrt"])

print("ALLE TESTS OK" if not fails else f"{fails} FEHLER")
sys.exit(1 if fails else 0)
