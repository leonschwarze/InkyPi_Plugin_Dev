"""Zustand des Pi für die Wochenvorschau (tagesdashboard/pizustand.py) ohne Rendern.

  python dev/test_pizustand.py

Prüft: Ausfälle aus der Statusanzeige werden zu Abschnitten (Beginn, Ende, Dauer, nach Neustart von
InkyPi), gleichzeitige Ausfälle zusammengefasst, Neustarts, Unterspannung (gerade/seit dem Start,
nicht doppelt), Tageshöchsttemperatur, nur die letzten 7 Tage, Datei wird nur bei Änderungen
geschrieben, kaputte Datei, Texte (Dauer, Uhrzeit, online, Speicher), Rundlauf mit der echten
status.py, Werte auf diesem Rechner ohne Fehler.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import pizustand as pz  # noqa: E402
import status  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
SUN = datetime(2026, 11, 15, 19, 10, tzinfo=TZ)  # Sonntag
DAY = 86400


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def fresh():
    return os.path.join(tempfile.mkdtemp(prefix="pi-test-"), pz.STATE_FILE)


def system(uptime=23 * DAY, temp=40.0, free=9.8e9, volt=None):
    return {"uptime": uptime, "temp": temp, "free": free, "volt": volt or {"now": False, "since_boot": False}}


def line(now, path, sys_=None):
    pz._last_system = sys_ or system()
    return pz.line(now, path)


# ---------------------------------------------------------------- ruhige Woche
p = fresh()
check("erste Runde schreibt die Datei", pz.record(SUN, {}, p, system()))
check("gleiche Runde schreibt nicht noch einmal", not pz.record(SUN + timedelta(minutes=15), {}, p, system(uptime=23 * DAY + 900)))
check("ruhig: Text", line(SUN, p) == "23 Tage online · bis 40 °C · 9,8 GB frei · Woche ohne Ausfälle")
check("Temperatur unter +1 °C wird nicht gespeichert", not pz.record(SUN, {}, p, system(temp=40.6)))
check("neue Höchsttemperatur ab +1 °C", pz.record(SUN, {}, p, system(temp=52.2)))
check("bis 52 °C (gerundet)", "bis 52 °C" in line(SUN, p, system(temp=41)))

# ---------------------------------------------------------------- Ausfälle
p = fresh()
t0 = SUN - timedelta(days=3, hours=16)      # Do 3:10
pz.record(t0, {"Kalender": (t0, t0)}, p, system())
pz.record(t0 + timedelta(minutes=15), {"Kalender": (t0, t0 + timedelta(minutes=15))}, p, system())
pz.record(t0 + timedelta(minutes=30), {}, p, system())  # wieder da
st = pz.load(p)
check("ein Abschnitt", len(st["episodes"]) == 1)
check("Ende = Runde, in der die Quelle wieder antwortete", st["episodes"][0]["end"] == pz._iso(t0 + timedelta(minutes=30)))
txt = line(SUN, p)
check("ein Ausfall: Uhrzeit und Dauer", txt.startswith("Kalender 1× weg (Do 3:10, 30 min)"), )
check("mit Ausfall kein „Woche ohne Ausfälle“", "ohne Ausfälle" not in txt)
t1 = SUN - timedelta(days=4, hours=-2, minutes=70)  # Mi 20:00
pz.record(t1, {"Kalender": (t1, t1)}, p, system())
pz.record(t1 + timedelta(minutes=10), {}, p, system())
txt = line(SUN, p)
check("zwei Ausfälle: Summe und zuletzt", txt.startswith("Kalender 2× weg (40 min, zuletzt Do 3:10)"), )

# Neustart von InkyPi mitten im Ausfall: Status vergisst ihn, Abschnitt endet beim letzten Fehlschlag
p = fresh()
pz.record(t0, {"Wetter": (t0, t0 + timedelta(minutes=45))}, p, system())
pz.record(t0 + timedelta(hours=2), {}, p, system())
st = pz.load(p)
check("lange Lücke: Ende = letzter Fehlschlag", st["episodes"][0]["end"] == pz._iso(t0 + timedelta(minutes=45)))

# laufender Ausfall: Dauer bis zum letzten Fehlschlag
p = fresh()
pz.record(SUN - timedelta(hours=1), {"Radar": (SUN - timedelta(hours=1), SUN)}, p, system())
check("laufender Ausfall: heute und Dauer", line(SUN, p).startswith("Radar 1× weg (heute 18:10, 1 Std.)"))

# gleichzeitige Ausfälle (WLAN weg) zusammenfassen, verschiedene nicht
p = fresh()
tw = SUN - timedelta(days=5, hours=17)       # Di 2:10
for k in range(3):  # 2:10, 2:25, 2:40 gescheitert, 2:50 wieder da
    tk = tw + timedelta(minutes=15 * k)
    pz.record(tk, {"Kalender": (tw, tk), "Wetter": (tw, tk)}, p, system())
pz.record(tw + timedelta(minutes=40), {}, p, system())
tr = SUN - timedelta(days=1, hours=5)        # Sa 14:10
pz.record(tr, {"Radar": (tr, tr)}, p, system())
pz.record(tr + timedelta(minutes=15), {}, p, system())
txt = line(SUN, p)
check("gleichzeitig: „Kalender und Wetter“ in einem Eintrag", "Kalender und Wetter 1× weg (Di 2:10, 40 min)" in txt)
check("anderer Ausfall extra, längster zuerst", txt.index("Kalender und Wetter") < txt.index("Radar 1× weg (gestern 14:10, 15 min)"))
check("Namen: drei Quellen", pz._names(["Wetter", "Kalender", "Radar"]) == "Wetter, Kalender und Radar")

# nur die letzten 7 Tage; älter als 9 Tage fällt aus der Datei
p = fresh()
old = SUN - timedelta(days=8)
pz.record(old, {"Zug": (old, old)}, p, system())
pz.record(old + timedelta(minutes=15), {}, p, system())
check("Ausfall vor 8 Tagen zählt nicht mehr", "Zug" not in line(SUN, p))
pz.record(SUN + timedelta(days=2), {}, p, system())
check("nach 9 Tagen aus der Datei", not pz.load(p)["episodes"])

# ---------------------------------------------------------------- Neustarts
p = fresh()
boot = SUN - timedelta(days=4, hours=5, minutes=8)   # Mi 14:02
pz.record(SUN - timedelta(days=1), {}, p, system(uptime=(SUN - timedelta(days=1) - boot).total_seconds()))
pz.record(SUN, {}, p, system(uptime=(SUN - boot).total_seconds() + 30))  # Uhr wackelt um Sekunden
check("ein Neustart, nicht doppelt", len(pz.load(p)["boots"]) == 1)
txt = line(SUN, p, system(uptime=(SUN - boot).total_seconds()))
check("Neustart Mi 14:02", "Neustart Mi 14:02" in txt and "4 Tage online" in txt)
boot2 = SUN - timedelta(hours=2)
pz.record(SUN, {}, p, system(uptime=2 * 3600))
check("zwei Neustarts", "2 Neustarts, zuletzt heute 17:10" in line(SUN, p, system(uptime=2 * 3600)))
check("online in Stunden", "2 Std. online" in line(SUN, p, system(uptime=2 * 3600)))
p = fresh()
pz.record(SUN, {}, p, system(uptime=23 * DAY))
check("Start vor 23 Tagen ist kein Neustart der Woche", "Neustart" not in line(SUN, p))

# ---------------------------------------------------------------- Unterspannung
p = fresh()
pz.record(SUN - timedelta(days=2), {}, p, system(volt={"now": False, "since_boot": True}))
pz.record(SUN - timedelta(days=1), {}, p, system(volt={"now": False, "since_boot": True}))
check("seit dem Start: nur einmal notiert", len(pz.load(p)["volt"]) == 1)
check("Text mit Rat", line(SUN, p).startswith("Unterspannung (Netzteil prüfen)"))
pz.record(SUN - timedelta(hours=3), {}, p, system(volt={"now": True, "since_boot": True}))
pz.record(SUN - timedelta(hours=1), {}, p, system(volt={"now": True, "since_boot": True}))
check("gerade jetzt: höchstens alle 6 Stunden", len(pz.load(p)["volt"]) == 2)
check("mehrmals: Anzahl", line(SUN, p).startswith("Unterspannung 2× (Netzteil prüfen)"))
check("Probleme vor den ruhigen Werten", line(SUN, p).index("Unterspannung") < line(SUN, p).index("online"))

# ---------------------------------------------------------------- Datei
p = fresh()
with open(p, "w") as f:
    f.write("{kaputt")
check("kaputte Datei: neu anfangen", pz.load(p) == pz.empty())
check("kaputte Datei wird ersetzt", pz.record(SUN, {}, p, system()) and json.load(open(p))["v"] == 1)
check("kein .tmp liegen geblieben", not os.path.exists(p + ".tmp"))


class Cfg:
    config_file = "/usr/local/inkypi/src/config/device.json"


check("Datei neben device.json", pz.state_path(Cfg()) == "/usr/local/inkypi/src/config/tagesdashboard_pi.json")
check("ohne InkyPi-Konfiguration im Temp-Ordner", pz.state_path(object()).startswith(tempfile.gettempdir()))

# ---------------------------------------------------------------- Texte
check("Dauer: kurz", pz.duration_text(timedelta(seconds=20)) == "kurz")
check("Dauer: Minuten", pz.duration_text(timedelta(minutes=40)) == "40 min")
check("Dauer: 2 Std. 10 min", pz.duration_text(timedelta(minutes=130)) == "2 Std. 10 min")
check("Dauer: ab 3 Std. ohne Minuten", pz.duration_text(timedelta(minutes=200)) == "3 Std.")
check("Dauer: Tage", pz.duration_text(timedelta(hours=50)) == "2 Tage")
check("Speicher unter 10 GB mit Komma", pz.free_text(1.24e9) == "1,2 GB frei")
check("Speicher ab 10 GB ganzzahlig", pz.free_text(23.6e9) == "24 GB frei")
check("online: 1 Tag", pz.online_text(DAY + 5) == "1 Tag online")
check("online: Minuten", pz.online_text(600) == "10 min online")
pz._last_system = {}
check("ohne Messwerte nur die Bilanz", pz.line(SUN, fresh()) == "Woche ohne Ausfälle")

# ---------------------------------------------------------------- Rundlauf mit status.py
p = fresh()
status.reset()
for k in range(4):  # Kalender fällt 30 min aus, dann wieder da
    t = SUN - timedelta(hours=2) + timedelta(minutes=15 * k)
    status.begin()
    status.ok("Wetter")
    if k < 2:
        status.fail("Kalender", "HTTP 503")
    else:
        status.ok("Kalender")
    status.commit(t)
    pz.record(t, status.snapshot(), p, system())
check("Rundlauf: Kalender 1× weg (30 min)", line(SUN, p).startswith("Kalender 1× weg (heute 17:10, 30 min)"))

# ---------------------------------------------------------------- dieser Rechner
real = pz.read_system()
check("echte Messwerte lesen ohne Fehler", isinstance(real, dict))
check("Laufzeit lesbar (Linux)", real.get("uptime", 0) > 0)

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
