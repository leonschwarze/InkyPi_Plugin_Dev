"""Rhein auf echtem Pegel (tagesdashboard/pegel.py, nachtgrafik.py) ohne Rendern.

  python dev/test_pegel.py

Prüft: Abruf gegen dev/mock_pegel.py (Szenarien, Trend, zu alte Werte, Ausfall, Zwischenspeicher,
Statusmeldungen), Antwort mit kaputten Einträgen, Zahl mit Komma, Lage der Wasserlinie (Reihenfolge,
Schwellen der Stadt Bonn), Zeichnung (pixelgleich ohne Pegel, Latte nur über Wasser, Pfeil, Brücke
bei Hochwasser, hochkant).
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import mock_pegel  # noqa: E402
import nachtgrafik  # noqa: E402
import pegel  # noqa: E402
import status  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 16, 23, 40, tzinfo=TZ)


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def run(kind, now=NOW):
    pegel.reset()
    status.reset()
    status.begin()
    mock_pegel.install(now, kind)
    info = pegel.load(now)
    status.commit(now)
    return info


# ---------------------------------------------------------------- Abruf und Trend
info = run("niedrig")
check("niedrig: 116 cm", info and round(info["cm"]) == 116)
check("niedrig: −4 cm seit gestern", info and round(info["diff"]) == -4)
check("niedrig: unter 5 cm kein Pfeil", info and info["trend"] == 0)
check("niedrig: Zahl mit Komma", info and info["label"] == "1,16 m")
check("Status: Pegel erreichbar", "Pegel" not in status.snapshot())
check("fällt: Pfeil nach unten", run("faellt")["trend"] == -1)
check("hoch: Pfeil nach oben", run("hoch")["trend"] == 1)
check("hoch: 7,60 m", run("hoch")["label"] == "7,60 m")
check("sehr hoch: 10,10 m", run("sehrhoch")["label"] == "10,10 m")
check("zu alter Wert (8 h): None", run("alt") is None)
check("ohne Daten (404): None", run("keine") is None)
check("Ausfall (503): None", run("down") is None)
check("Ausfall wird in der Statusanzeige gezählt", "Pegel" in status.snapshot())

# Zwischenspeicher: zweiter Abruf innerhalb von 30 Minuten fragt nicht neu
pegel.reset()
calls = []
mock_pegel.install(NOW, "normal")
inner = __import__("requests").Session.get


def counting(session, url, **kw):
    calls.append(url)
    return inner(session, url, **kw)


__import__("requests").Session.get = counting
pegel.load(NOW)
pegel.load(NOW + timedelta(minutes=10))
check("Zwischenspeicher: ein Abruf für zwei Runden", len(calls) == 1)

# Kaputte Einträge werden übersprungen, Reihenfolge egal
values = [(NOW - timedelta(hours=24), 300.0), (NOW, 320.0)]
summ = pegel.summarize(values, NOW)
check("Trend aus dem Wert von vor 24 Stunden", summ["diff"] == 20 and summ["trend"] == 1)
summ = pegel.summarize([(NOW - timedelta(hours=6), 300.0), (NOW, 320.0)], NOW)
check("ohne Wert von gestern (±3 h): kein Trend", summ["diff"] is None and summ["trend"] == 0)


class Resp:
    status_code = 200

    def json(self):
        return [{"timestamp": NOW.isoformat(), "value": 250}, {"timestamp": "kaputt", "value": 1},
                {"value": 3}, {"timestamp": (NOW - timedelta(hours=1)).isoformat(), "value": None}]


class Sess:
    def get(self, *a, **kw):
        return Resp()


vals = pegel.fetch(session=Sess())
check("kaputte Einträge übersprungen", vals == [(NOW, 250.0)])

# ---------------------------------------------------------------- Wasserlinie
ys = [nachtgrafik.pegel_y(cm) for cm in (0, 63, 116, 300, 380, 700, 950, 1013, 1300, 1600)]
check("Wasserlinie steigt mit dem Pegel (y fällt)", all(a >= b for a, b in zip(ys, ys[1:])))
check("ab 700 cm (Stadt Bonn: Ufer überschwemmt) an der Uferkante", nachtgrafik.pegel_y(700) == nachtgrafik.WATER)
check("unter 700 cm unter der Uferkante", nachtgrafik.pegel_y(690) > nachtgrafik.WATER)
check("Niedrig- und Mittelwasser deutlich verschieden (≥ 7 Einheiten)",
      nachtgrafik.pegel_y(116) - nachtgrafik.pegel_y(380) >= 7)
check("Wasserlinie bleibt im Band", 0 < nachtgrafik.pegel_y(5000) and nachtgrafik.pegel_y(-50) < nachtgrafik.H)

# ---------------------------------------------------------------- Zeichnung
wx = {"cloud": 40, "wet": False, "snowy": False, "fog": False}
plain = nachtgrafik.svg(NOW, wx)
check("ohne Pegel wie bisher (kein Pegel-Element)", "<polyline" not in plain and "<text" not in plain)
check("ohne Pegel: pegel=None ändert nichts", nachtgrafik.svg(NOW, wx, pegel=None) == plain)
for width in (800, 480):
    for cm, trend in ((116, 0), (116, -1), (760, 1), (1010, 1)):
        art = nachtgrafik.svg(NOW, wx, width=width, pegel={"cm": cm, "label": pegel.label(cm), "trend": trend})
        y = nachtgrafik.pegel_y(cm)
        tag = f"{width} {cm} cm"
        check(f"{tag}: Zahl an der Latte", f">{pegel.label(cm)}</text>" in art)
        check(f"{tag}: Pfeil nur bei Trend", ("<polygon" in art) == bool(trend))
        lat = [m for m in re.finditer(r'<rect x="[\d.]+" y="([\d.]+)" width="9" height="([\d.]+)"', art)]
        check(f"{tag}: Latte nur über Wasser", lat and all(float(m.group(1)) + float(m.group(2)) <= y + 0.05 for m in lat))
        if y < nachtgrafik.WATER - 3:
            deck = art.rfind(f'y="{nachtgrafik.WATER - 6}" width=')
            check(f"{tag}: Brücke über der Welle gezeichnet", deck > art.find("<polyline"))

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
