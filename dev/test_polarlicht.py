"""Polarlicht im Nachtbild (tagesdashboard/polarlicht.py, nachtgrafik.py) ohne Rendern (seit 1.37).

  python dev/test_polarlicht.py

Prüft: Abruf gegen dev/mock_polar.py (beide Antwortformate, Schwelle Kp 7, „7−“ zählt, Kp 8 = stark, Ausfall,
Zwischenspeicher, Statusmeldungen), dunkle Stunden (abends, nach Mitternacht, Ende des Nachtfensters), Wolken
(Text ja, Zeichnung nein), Zeichnung (pixelgleich ohne Polarlicht, Sterne und Mond unverändert, nur Displayfarben,
Lücke an der Pegellatte, Rot nur ab Kp 8, alle Breiten).
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import mock_polar  # noqa: E402
import nachtgrafik  # noqa: E402
import polarlicht  # noqa: E402
import status  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 24, 23, 5, tzinfo=TZ)
CLEAR = {"cloud": 20, "wet": False}
CLOUDY = {"cloud": 90, "wet": False}


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def run(kind, now=NOW, wx=CLEAR, night_end=None):
    polarlicht.reset()
    status.reset()
    status.begin()
    mock_polar.install(now, kind)
    values = polarlicht.load_values()
    status.commit(now)
    return polarlicht.night_info(values, now, wx, night_end)


# ---- Schwelle und Formate --------------------------------------------
check("ruhig (Kp 2,67): nichts", run("ruhig") is None)
check("Kp 6: für Bonn zu schwach", run("kp6") is None)
info = run("kp7")
check("Kp 7: möglich und gezeichnet", bool(info) and info["draw"] and not info["strong"])
check("Kp 7: Text nennt Kp und Stunde", info and info["text"] == "Polarlicht möglich: Kp 7 ab 23 Uhr · tief im Norden")
info8 = run("kp8")
check("Kp 8,33: stark (rote Spitzen)", bool(info8) and info8["strong"])
check("alte Fassung (Liste von Listen mit Kopfzeile) wird gelesen", bool(run("alt")))
check("„7−“ (6,67) zählt als 7", polarlicht.summarize([(NOW.astimezone(polarlicht.timezone.utc), 6.67, "predicted")],
                                                     NOW, CLEAR) is not None)
check("6,33 zählt nicht", polarlicht.summarize([(NOW.astimezone(polarlicht.timezone.utc), 6.33, "predicted")],
                                              NOW, CLEAR) is None)
check("kaputte Einträge werden übersprungen",
      len(polarlicht.parse([{"time_tag": "x", "kp": 7}, {"kp": 3}, ["2026-11-24 21:00:00", "7.00", "predicted", None],
                            {"time_tag": "2026-11-24T21:00:00", "kp": "abc"}])) == 1)

# ---- Wolken, Ausfall, Status, Zwischenspeicher ------------------------
cl = run("kp7", wx=CLOUDY)
check("bewölkt: Text ja, Zeichnung nein", bool(cl) and not cl["draw"] and "bewölkt" in cl["text"])
check("Regen: nicht gezeichnet", not run("kp7", wx={"cloud": 40, "wet": True})["draw"])
check("ohne Nachtwetter: nicht gezeichnet", not run("kp7", wx=None)["draw"])
check("NOAA 503: None", run("down") is None)
check("Statusanzeige kennt den Ausfall", any(s["name"] == "Polarlicht" for s in status.report(NOW + timedelta(hours=3))))
check("keine Daten (404): None, Nachtbild wie bisher", run("keine") is None)
polarlicht.reset()
mock_polar.install(NOW, "kp7")
calls = []
import requests  # noqa: E402
inner = requests.Session.get


def counting(session, url, **kw):
    calls.append(url)
    return inner(session, url, **kw)


requests.Session.get = counting
polarlicht.load_values()
polarlicht.load_values()
check("Zwischenspeicher: ein Abruf für zwei Bilder", len(calls) == 1)
requests.Session.get = inner

# ---- dunkle Stunden ----------------------------------------------------
s, e = polarlicht.dark_hours(datetime(2026, 11, 24, 15, 0, tzinfo=TZ))
check("nachmittags: ab 18 Uhr bis morgen 6 Uhr", (s.hour, e.hour, e.day) == (18, 6, 25))
s, e = polarlicht.dark_hours(datetime(2026, 11, 25, 2, 30, tzinfo=TZ))
check("nach Mitternacht: jetzt bis 6 Uhr", (s.hour, s.minute, e.hour, e.day) == (2, 30, 6, 25))
s, e = polarlicht.dark_hours(NOW, night_end=datetime(2026, 11, 25, 5, 0, tzinfo=TZ))
check("Ende des Nachtfensters begrenzt", e.hour == 5)
# Peak am Nachmittag zählt nicht
utc = polarlicht.timezone.utc
vals = [(datetime(2026, 11, 24, 12, 0, tzinfo=utc), 8.0, "observed"), (datetime(2026, 11, 24, 21, 0, tzinfo=utc), 3.0, "p")]
check("Sturm am Nachmittag: nachts nichts", polarlicht.summarize(vals, NOW, CLEAR) is None)

# ---- Zeichnung ----------------------------------------------------------
base = nachtgrafik.svg(NOW, CLEAR, width=756, seed=5)
with_a = nachtgrafik.svg(NOW, CLEAR, width=756, seed=5, aurora=info)
check("ohne Polarlicht pixelgleich (SVG unverändert)", nachtgrafik.svg(NOW, CLEAR, width=756, seed=5, aurora=None) == base)
check("Sterne, Mond und Stadt liegen gleich (nur Strahlen davor eingefügt)",
      re.sub(r'<rect x="[\d.]+" y="[\d.]+" width="3" height="[\d.]+" fill="#2E9E3F"/>', "", with_a) == base)
colors = set(re.findall(r'fill="(#[0-9A-F]{6})"', polarlicht.svg(756, 104, __import__("random").Random(1), strong=True)))
check("nur Displayfarben Grün und Rot", colors == {"#2E9E3F", "#E3001B"})
check("Rot nur ab Kp 8", "#E3001B" not in polarlicht.svg(756, 104, __import__("random").Random(1), strong=False))
rays = polarlicht.svg(756, 104, __import__("random").Random(2), x0=0, x1=756, gap_at=300)
xs = [float(x) for x in re.findall(r'<rect x="([\d.]+)"', rays)]
check("Lücke an der Pegellatte (±34)", xs and not any(abs(x - 300) < 34 for x in xs))
tops = [float(y) for y in re.findall(r' y="([\d.]+)"', rays)]
check("Strahlen bleiben am Himmel (oben ≥ 0, Fuß über dem Wasser)", tops and min(tops) >= 0)
for w in (756, 467, 516, 1600):
    out = nachtgrafik.svg(NOW, CLEAR, width=w, seed=3, aurora=info8)
    check(f"Breite {w}: gezeichnet", out.count("#2E9E3F") > 20)

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
