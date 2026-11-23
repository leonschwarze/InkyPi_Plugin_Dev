"""Warnungen aus NINA (tagesdashboard/nina.py) ohne Rendern.

  python dev/test_nina.py

Prüft: Regionalschlüssel, Punkt im Polygon (Löcher, MultiPolygon, FeatureCollection), erster Satz der
Handlungsempfehlung, Abruf gegen dev/mock_nina.py (gilt hier, anderswo in Bonn → weg, ohne Gebiet → gilt,
DWD und Entwarnung → weg, Ausfall), Reihenfolge, Zwischenspeicher, verspätete Statusmeldung
(report_status), Signatur – und mit dem echten generate_image: Eine neue Warnung zeichnet das Bild sofort
neu, auch wenn Bild-Cache bzw. eingefrorenes Nachtbild noch gelten würden; ohne Warnung bleibt alles wie
bisher (Cache greift).
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import mock_nina  # noqa: E402
import nina  # noqa: E402
import status  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 24, 7, 10, tzinfo=TZ)
HOME = mock_nina.HOME


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


# ---------------------------------------------------------------- Regionalschlüssel
check("ARS: 05314 → 053140000000", nina.read_ars("05314") == "053140000000")
check("ARS: zwölf Stellen werden auf den Kreis gekürzt", nina.read_ars("053140003003") == "053140000000")
check("ARS: Leerzeichen egal", nina.read_ars("05 314 000") == "053140000000")
check("ARS: leer/ungültig → Bonn", nina.read_ars("") == nina.read_ars("ab") == "053140000000")

# ---------------------------------------------------------------- Punkt im Polygon
square = [[[7.0, 50.7], [7.2, 50.7], [7.2, 50.8], [7.0, 50.8], [7.0, 50.7]]]
hole = square + [[[7.08, 50.73], [7.12, 50.73], [7.12, 50.75], [7.08, 50.75], [7.08, 50.73]]]
check("Polygon: Punkt innen", nina.contains([square], 50.75, 7.1))
check("Polygon: Punkt außen", not nina.contains([square], 50.9, 7.1))
check("Polygon: Punkt im Loch zählt nicht", not nina.contains([hole], 50.74, 7.1))
check("Polygon: Punkt neben dem Loch zählt", nina.contains([hole], 50.78, 7.1))
fc = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [
        [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]], square]}}]}
check("GeoJSON: MultiPolygon in FeatureCollection", nina.contains(nina._polygons(fc), 50.75, 7.1))
check("GeoJSON: Koordinaten sind [lon, lat]", not nina.contains(nina._polygons(fc), 7.1, 50.75))
check("GeoJSON: Unbekanntes → keine Polygone", nina._polygons({"type": "Point", "coordinates": [7, 50]}) == [])

# ---------------------------------------------------------------- Handlungsempfehlung
check("Empfehlung: erster Satz ohne HTML",
      nina.first_sentence("Verlassen Sie das Gebiet.<br/>Folgen Sie …") == "Verlassen Sie das Gebiet.")
check("Empfehlung: Entities", nina.first_sentence("Fenster &amp; Türen schließen!") == "Fenster & Türen schließen!")
check("Empfehlung: zu lang → None", nina.first_sentence("x" * 120 + ".") is None)
check("Empfehlung: leer → None", nina.first_sentence("") is None and nina.first_sentence(None) is None)


# ---------------------------------------------------------------- Abruf
def run(kind):
    nina.reset()
    status.reset()
    mock_nina.install(NOW, kind)
    out = nina.load("053140000000", *HOME)
    status.begin()
    nina.report_status("053140000000")
    status.commit(NOW)
    return out


w = run("bombe")
check("bombe: eine Warnung, gilt hier", len(w) == 1 and w[0]["here"] is True)
check("bombe: Titel, Stufe rot", w and w[0]["title"] == "Bombenentschärfung in Bonn-Weststadt" and w[0]["level"] == "rot")
check("bombe: erster Satz der Empfehlung", w and w[0]["instruction"] == "Verlassen Sie das Sperrgebiet bis 9:00 Uhr.")
check("bombe: seit 6:40", w and nina.since_text(w[0], TZ) == "seit 6:40")
check("bombe: Status ohne Ausfall", status.report(NOW) == [])
check("fern: Warnung in Beuel fällt weg", run("fern") == [])
w = run("trinkwasser")
check("trinkwasser: ohne Gebiet gilt sie (here None), gelb", len(w) == 1 and w[0]["here"] is None and w[0]["level"] == "gelb")
w = run("zwei")
check("zwei: Bombe (Severe) vor Trinkwasser (Minor)", [x["severity"] for x in w] == ["Severe", "Minor"])
check("dwd: DWD-Warnungen fallen weg", run("dwd") == [])
check("entwarnung: Cancel fällt weg", run("entwarnung") == [])
check("down: keine Warnung", run("down") == [])
check("down: Statusanzeige meldet „Warnungen“", [s["name"] for s in status.report(NOW)] == ["Warnungen"])

# Zwischenspeicher und verspätete Statusmeldung
nina.reset()
status.reset()
calls = []
mock_nina.install(NOW, "bombe")
real_get = __import__("requests").Session.get


def counting(session, url, **kw):
    calls.append(url)
    return real_get(session, url, **kw)


__import__("requests").Session.get = counting
nina.load("053140000000", *HOME)
first = len(calls)
nina.load("053140000000", *HOME)
check("Zwischenspeicher: zweiter Aufruf fragt nicht", len(calls) == first and first == 3)  # Liste, Details, Gebiet
check("Status: Ergebnis wird einmal gemeldet", nina._pending.get("053140000000") == ("ok", ""))
status.begin()
nina.report_status("053140000000")
check("Status: danach nur noch „gebraucht“", "053140000000" not in nina._pending)
__import__("requests").Session.get = real_get

# Signatur
a, b = run("bombe"), run("zwei")
check("Signatur: ändert sich mit einer neuen Warnung", nina.signature(a) != nina.signature(b))
check("Signatur: leer ohne Warnung", nina.signature([]) == "")

# ---------------------------------------------------------------- Ende zu Ende: Caches
sys.path.insert(0, str(INKYPI))
import render  # noqa: E402

render.link_plugins(INKYPI)
os.chdir(INKYPI)
from PIL import Image  # noqa: E402

import mock_brightsky, mock_news, mock_radar, mock_luft, mock_pollen, mock_pegel, mock_polar  # noqa: E402,E401
for m, k in ((mock_brightsky, "herbst"), (mock_news, "normal"), (mock_radar, "trocken"), (mock_luft, "gut"),
             (mock_pollen, "gut"), (mock_pegel, "keine"), (mock_polar, "keine")):
    m.install(NOW, k)
import caldav_server  # noqa: E402
url, user, password = caldav_server.start(NOW.date())
module = __import__("plugins.tagesdashboard.tagesdashboard", fromlist=["x"])
plugnina = __import__("plugins.tagesdashboard.nina", fromlist=["x"])
import mock_ziel, mock_pi  # noqa: E402,E401
mock_ziel.install(NOW)
mock_pi.install(NOW, "ok", __import__("plugins.tagesdashboard.pizustand", fromlist=["x"]))
clock = {"now": NOW}
module.Tagesdashboard.current_time = lambda self, tz: clock["now"].astimezone(tz)
plugin = module.Tagesdashboard({"id": "tagesdashboard"})
seen = []


def fake_render(dimensions, html, css, params):
    seen.append(params.get("warn"))
    return Image.new("RGB", tuple(dimensions), "white")


plugin.render_image = fake_render
cfg = render.DevConfig((800, 480), "horizontal", {"NEXTCLOUD_APP_PASSWORD": password})
cfg.values["plugin_cycle_interval_seconds"] = 300
settings = dict(render.BASE_SETTINGS, nextcloudUrl=url, username=user, liveCity="false")  # Nachtbild bleibt stehen


def step(kind, minutes, refetch=True):
    """Eine Runde nach `minutes`; refetch: der 10-min-Speicher von NINA ist abgelaufen."""
    clock["now"] += timedelta(minutes=minutes)
    if refetch:
        plugnina.reset()
    mock_nina.install(clock["now"], kind)
    before = len(seen)
    plugin.generate_image(dict(settings), cfg)
    return len(seen) > before


module._IMAGE_CACHE.clear()
module._NIGHT_CACHE.clear()
clock["now"] = NOW - timedelta(minutes=5)
check("Tag: erstes Bild wird gezeichnet", step("keine", 5))
check("Tag: ohne Warnung greift der Bild-Cache", not step("keine", 5))
check("Tag: neue Warnung → sofort neu, obwohl der Cache noch gilt", step("bombe", 5))
check("Tag: Band im Bild", seen[-1] and seen[-1]["first"]["title"].startswith("Bombenentschärfung"))
check("Tag: dieselbe Warnung → wieder Cache", not step("bombe", 5))
check("Tag: Warnung weg → sofort neu", step("keine", 5) and seen[-1] is None)
check("Tag: Warnung in Beuel ändert nichts (Cache)", not step("fern", 5))

clock["now"] = datetime(2026, 11, 24, 0, 30, tzinfo=TZ) - timedelta(minutes=5)
module._IMAGE_CACHE.clear()
module._NIGHT_CACHE.clear()
check("Nacht: erstes Nachtbild", step("keine", 5))
check("Nacht: eingefroren bis 6 Uhr", not step("keine", 60))
check("Nacht: Warnung um 1:35 → sofort neu", step("zwei", 5) and seen[-1]["more"] == 1)
check("Nacht: danach wieder eingefroren", not step("zwei", 60))

# Lebende Stadt (seit 1.43): Daten bleiben die der Nacht, gezeichnet wird zur vollen Stunde; eine Warnung kommt
# trotzdem sofort
settings["liveCity"] = "true"
clock["now"] = datetime(2026, 11, 24, 0, 30, tzinfo=TZ) - timedelta(minutes=5)
module._NIGHT_CACHE.clear()
check("Lebende Stadt: erstes Nachtbild (0:30)", step("keine", 5))
check("Lebende Stadt: 0:50 aus dem Speicher", not step("keine", 20))
check("Lebende Stadt: 1:00 neu gezeichnet", step("keine", 10))
check("Lebende Stadt: … mit den Daten der Nacht (kein neuer Abruf der Warnungen nötig)", seen[-1] is None)
check("Lebende Stadt: Warnung um 1:10 → sofort neu", step("zwei", 10) and seen[-1]["more"] == 1)
check("Lebende Stadt: 1:40 aus dem Speicher", not step("zwei", 30))
check("Lebende Stadt: 2:00 neu, Warnung bleibt im Bild", step("zwei", 20) and seen[-1]["more"] == 1)

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
