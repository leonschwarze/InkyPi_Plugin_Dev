"""Hilfsbild und Zustandsdatei im Dashboard (Taste A „neu zeichnen“, Taste D „Hilfsbild“).

  python dev/test_hilfsbild.py

Ruft das echte generate_image auf (render_image ist ersetzt und merkt sich nur die Aufrufe) und prüft:
  * check(): Zähler, Hilfsbild, Ablauf, Nacht, kaputte Datei
  * Ohne Datei ändert sich nichts: zweite Runde in der Ruhezeit kommt aus dem Bild-Cache
  * Gegenprobe (der Fehler, den die Datei behebt): ohne check() bliebe der Tastendruck im Cache hängen
  * Neuer Zähler → beide Caches werden übersprungen, danach wieder Cache
  * Hilfsbild: wird gezeichnet, steht nicht im Bild-Cache, danach einmal frisch gezeichnet
  * Nacht: kein Hilfsbild, Nachtbild bleibt eingefroren, auch bei neuem Zähler
  * pi_lines(): höchstens MAX_ZEILEN Zeilen, Probleme zuerst
  * Nachtfenster-Standardwerte des Dienstes = Standardwerte des Dashboards (kein Auseinanderlaufen)
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(INKYPI))
sys.path.insert(0, str(ROOT / "tasten"))

import render  # noqa: E402

render.link_plugins(INKYPI)
os.chdir(INKYPI)

from PIL import Image  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
START = datetime(2026, 11, 17, 10, 0, tzinfo=TZ)  # Dienstag
fails = 0


def check(cond, msg):
    global fails
    print(("ok    " if cond else "FEHLER") + " " + msg)
    if not cond:
        fails += 1


import mock_brightsky, mock_news, mock_radar, mock_luft, mock_pollen, mock_pegel, mock_bahn, mock_vrr  # noqa: E402,E401
import mock_schnee, mock_nina  # noqa: E402,E401
mock_brightsky.install(START, "herbst")
mock_news.install(START, "normal")
mock_radar.install(START, "trocken")
mock_luft.install(START, "gut")
mock_pollen.install(START, "gut")
mock_pegel.install(START, "keine")
mock_schnee.install(START, "normal")
mock_nina.install(START, "keine")
mock_bahn.install(START, "ok")
mock_vrr.install(START, "ruhig")
import caldav_server  # noqa: E402
url, user, password = caldav_server.start(START.date())

module = __import__("plugins.tagesdashboard.tagesdashboard", fromlist=["x"])
hb = __import__("plugins.tagesdashboard.hilfsbild", fromlist=["x"])
import mock_ziel, mock_pi  # noqa: E402,E401  (erst nach den anderen Mocks: mock_ziel merkt sich beim Import das bisherige get)
mock_ziel.install(START)
mock_pi.install(START, "ok", __import__("plugins.tagesdashboard.pizustand", fromlist=["x"]))

clock = {"now": START}
module.Tagesdashboard.current_time = lambda self, tz: clock["now"].astimezone(tz)
plugin = module.Tagesdashboard({"id": "tagesdashboard", "version": "9.99"})
calls = []   # (Zeit, params) je Zeichnen


def fake_render(dimensions, html, css, params):
    calls.append((clock["now"], params))
    return Image.new("RGB", tuple(dimensions), "white")


plugin.render_image = fake_render
TMP = Path(tempfile.mkdtemp(prefix="hilfsbild-"))
STATE = TMP / "tasten_zustand.json"
hb.state_path = lambda device_config: str(STATE)

BASE = dict(render.BASE_SETTINGS, nextcloudUrl=url, username=user, cfgVersion=str(module.CFG_VERSION),
            einkSnap="true", trainEnabled="false", quietMinutes="30")


def cfg():
    c = render.DevConfig((800, 480), "horizontal", {"NEXTCLOUD_APP_PASSWORD": password})
    c.values["plugin_cycle_interval_seconds"] = 5 * 60
    return c


def state(**kw):
    import json
    STATE.write_text(json.dumps(dict({"v": 1}, **kw)))


def fresh():
    module._IMAGE_CACHE.clear()
    module._NIGHT_CACHE.clear()
    hb.reset()
    calls.clear()
    if STATE.exists():
        STATE.unlink()


def go(minutes=0, extra=None):
    clock["now"] = clock["now"] + timedelta(minutes=minutes)
    n = len(calls)
    plugin.generate_image(dict(BASE, **(extra or {})), cfg())
    if len(calls) == n:
        return "cache"
    return "hilfe" if "hilfe" in calls[-1][1] else "neu"


# ---------------------------------------------------------------- check() einzeln
now = START
hb.reset()
check(hb.check(str(TMP / "gibtsnicht.json"), now) == (False, False), "check: ohne Datei weder Hilfsbild noch frisch")
state(neu=1)
check(hb.check(str(STATE), now) == (False, True), "check: erster Blick auf einen Zähler → frisch (Neustart des Prozesses)")
check(hb.check(str(STATE), now) == (False, False), "check: derselbe Zähler → nicht noch einmal")
state(neu=2)
check(hb.check(str(STATE), now) == (False, True), "check: Zähler +1 → frisch")
state(neu=2, hilfe_bis=now.timestamp() + 60)
check(hb.check(str(STATE), now) == (True, False), "check: hilfe_bis in der Zukunft → Hilfsbild")
check(hb.check(str(STATE), now + timedelta(seconds=61)) == (False, True), "check: abgelaufen → aus und einmal frisch")
check(hb.check(str(STATE), now + timedelta(seconds=62)) == (False, False), "check: danach wieder normal")
state(neu=3, hilfe_bis=now.timestamp() + 60)
check(hb.check(str(STATE), now, night=True) == (False, False), "check: nachts weder Hilfsbild noch frisch")
state(neu=4)
check(hb.check(str(STATE), now) == (False, True), "check: nachts verpasster Zähler 3 wird nicht nachgeholt, 4 gilt am Tag")
for bad in ("{kaputt", "[1]", '{"hilfe_bis": "bald", "neu": "x"}', '{"hilfe_bis": true}'):
    STATE.write_text(bad)
    hb.reset()
    r = hb.check(str(STATE), now)
    check(r[0] is False, f"check: Unsinn in der Datei ({bad[:18]}) → kein Hilfsbild")

# ---------------------------------------------------------------- Cache ohne Datei
fresh()
check([go(), go(5), go(5), go(5)] == ["neu", "cache", "cache", "cache"], "ohne Zustandsdatei: Ruhetakt wie bisher (Bild-Cache)")

# Gegenprobe: Ohne die Datei bliebe ein Tastendruck unsichtbar
fresh()
orig = hb.check
go()
hb.check = lambda *a, **k: (False, False)
state(neu=1)
check(go(5) == "cache", "Gegenprobe: ohne check() bliebe der Druck von A im Bild-Cache hängen (der Fehler aus der Recherche)")
hb.check = orig

# ---------------------------------------------------------------- Taste A
fresh()
go()
check(go(5) == "cache", "vor dem Druck: Cache")
state(neu=1)
check(go(1) == "neu", "A: Zähler geändert → neu gezeichnet, obwohl der Cache noch gültig wäre")
check(go(1) == "cache", "danach wieder Cache (kein Dauerfeuer)")
state(neu=2)
check(go(1) == "neu", "A ein zweites Mal → wieder neu")

# ---------------------------------------------------------------- Taste D
fresh()
go()
state(neu=1, hilfe_bis=clock["now"].timestamp() + 180)
check(go(1) == "hilfe", "D: Hilfsbild gezeichnet")
hp = calls[-1][1]["hilfe"]
check(hp["version"] == "9.99" and [t["key"] if "key" in t else t for t in hp["tasten"]] and len(hp["tasten"]) == 4,
      "D: Version und vier Tasten im Hilfsbild")
check(go(1) == "hilfe", "D: weitere Runde im Hilfsbild zeichnet wieder (kein Cache – der Pi-Zustand ändert sich)")
state(neu=2, hilfe_bis=0)
check(go(1) == "neu", "D schließt: Dashboard frisch, nicht das Hilfsbild aus dem Cache")
check("hilfe" not in calls[-1][1], "nach dem Schließen ist es das Dashboard")
check(go(1) == "cache", "danach wieder Cache")

# Hilfsbild läuft ab, ohne dass der Dienst den Zähler anhebt (Dienst gestorben)
fresh()
go()
state(hilfe_bis=clock["now"].timestamp() + 60)
go(0.5)
check(go(2) == "neu" and "hilfe" not in calls[-1][1], "Ablauf ohne Dienst: Dashboard wieder da, einmal frisch")

# Hilfsbild landet nie im Cache
fresh()
state(hilfe_bis=clock["now"].timestamp() + 600)
go()
state(hilfe_bis=0)
check(go(1) == "neu" and "hilfe" not in calls[-1][1], "Hilfsbild als erste Runde: danach kommt nicht das Hilfsbild aus dem Cache")

# ---------------------------------------------------------------- Nacht
NACHT = dict(nightEnabled="true", nightFrom="23:00", nightTo="06:00", nightFreeze="true", cfgVersion=str(module.CFG_VERSION))
fresh()
clock["now"] = START.replace(hour=0, minute=30)
check(go(0, NACHT) == "neu", "Nacht: erstes Nachtbild")
state(neu=1, hilfe_bis=clock["now"].timestamp() + 180)
check(go(15, NACHT) == "cache", "Nacht: weder Hilfsbild noch neues Bild, der Cache bleibt")
check(all("hilfe" not in p for _, p in calls), "Nacht: Hilfsbild nie gezeichnet")
clock["now"] = START.replace(hour=6, minute=5)
state(neu=1, hilfe_bis=0)
check(go(0, NACHT) == "neu", "Morgens ist alles normal")

# ---------------------------------------------------------------- pi_lines
many = [{"text": f"Problem {i}", "kind": "warn"} for i in range(8)] if False else None
try:
    import pizustand
except ImportError:
    pizustand = __import__("plugins.tagesdashboard.pizustand", fromlist=["x"])
parts = pizustand.parts(START, str(TMP / "pi.json"))
lines = hb.pi_lines(parts)
check(len(lines) <= hb.MAX_ZEILEN + 1, f"pi_lines: höchstens {hb.MAX_ZEILEN} (+1 „weitere“) Zeilen, hier {len(lines)}")

# ---------------------------------------------------------------- Standardwerte gleich
import tasten  # noqa: E402
d = module.Tagesdashboard.DEFAULTS if hasattr(module.Tagesdashboard, "DEFAULTS") else getattr(module, "DEFAULTS")
for k, v in tasten.NIGHT_DEFAULTS.items():
    check(d.get(k) == v, f"Dienst und Dashboard: Standard {k} = {v}")

print()
print("Alles ok." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
