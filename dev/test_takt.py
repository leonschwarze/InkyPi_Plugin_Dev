"""Wann zeichnet das Tagesdashboard wirklich neu? InkyPis Takt nachgespielt, ohne Rendern.

  python dev/test_takt.py          # alle Fälle
  python dev/test_takt.py -v       # zusätzlich jede Runde ausgeben

Ruft das echte generate_image so auf, wie InkyPi es tut: alle `takt` Minuten (plus ein paar
Sekunden Verzug je Runde, InkyPi schläft erst nach getaner Arbeit). render_image ist ersetzt und
zählt nur mit – ein Aufruf = ein neues Bild; sonst kam es aus dem Bild-Cache.

Geprüft (Fehler bis 1.31: ohne Zug bzw. ohne Wochentag zeichnete es bei 5-min-Takt alle 5 min):
  * Zug aus, Takt 5 min                → alle 15 min („Sonst alle 15 min“)
  * Zug an, aber kein Wochentag        → alle 15 min, auch im eingestellten Zeitfenster
  * Zug an, Dienstag, Fenster 6:30–8:15 → im Fenster alle 5 min, davor/danach alle 15 min
  * „Sonst alle 30 min“                → alle 30 min
  * Takt 10, 15, 20 min                → jede Runde neu (der Cache verlängert nie; Fehler aus 1.3)
  * Grenze (Nachrichten ab 6:00)       → erste Runde ab 6:00 zeichnet neu, auch mitten im Ruhetakt
  * Takt unbekannt                     → Verhalten wie bis 1.31 mit Zug (1 min Toleranz)
  * Nachtbild „Nachts ruhig halten“    → einmal pro Nacht; mit „Lebende Stadt“ (seit 1.43) zur ersten Runde jeder
                                         vollen Stunde (dieselben Daten, nur die Stadt geht mit der Uhr)
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
sys.path.insert(0, str(INKYPI))

import render  # noqa: E402  (link_plugins, DevConfig, BASE_SETTINGS)

render.link_plugins(INKYPI)
os.chdir(INKYPI)

from PIL import Image  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
START = datetime(2026, 11, 17, 5, 30, tzinfo=TZ)  # Dienstag
VERBOSE = "-v" in sys.argv
DRIFT = timedelta(seconds=7)  # InkyPi: Takt zählt ab dem Ende der vorigen Runde

import mock_brightsky, mock_news, mock_radar, mock_luft, mock_pollen, mock_pegel, mock_bahn, mock_vrr  # noqa: E402,E401
mock_brightsky.install(START, "herbst")
mock_news.install(START, "normal")
mock_radar.install(START, "trocken")
mock_luft.install(START, "gut")
mock_pollen.install(START, "gut")
mock_pegel.install(START, "keine")
import mock_schnee  # noqa: E402  (Schneedaten: nie echtes Netz)
mock_schnee.install(START, "normal")
import mock_nina  # noqa: E402  (Warnungen aus NINA seit 1.38: nie echtes Netz)
mock_nina.install(START, "keine")
mock_bahn.install(START, "ok")
mock_vrr.install(START, "ruhig")
import caldav_server  # noqa: E402
url, user, password = caldav_server.start(START.date())

module = __import__("plugins.tagesdashboard.tagesdashboard", fromlist=["x"])
import mock_ziel, mock_pi  # noqa: E402,E401
mock_ziel.install(START)
mock_pi.install(START, "ok", __import__("plugins.tagesdashboard.pizustand", fromlist=["x"]))

clock = {"now": START}
module.Tagesdashboard.current_time = lambda self, tz: clock["now"].astimezone(tz)
plugin = module.Tagesdashboard({"id": "tagesdashboard"})
renders = []


def fake_render(dimensions, *args, **kwargs):
    renders.append(clock["now"])
    return Image.new("RGB", tuple(dimensions), "white")


plugin.render_image = fake_render

BASE = dict(render.BASE_SETTINGS, nextcloudUrl=url, username=user, cfgVersion=str(module.CFG_VERSION),
            einkSnap="true", showWear="true", catEnabled="true", newsEnabled="true",
            trainStation="Bonn Hbf", trainLine="RE 5", trainTime="08:04", trainFrom="06:30", trainTo="08:15",
            trainTarget="Düsseldorf Hbf", quietMinutes="15")
fails = 0


def run(name, extra, takt_min, start, end, want):
    """Spielt InkyPi von start bis end; want = erwartete Uhrzeiten (HH:MM) mit neuem Bild."""
    global fails
    module._IMAGE_CACHE.clear()
    module._NIGHT_CACHE.clear()
    settings = dict(BASE, **extra)
    cfg = render.DevConfig((800, 480), "horizontal", {"NEXTCLOUD_APP_PASSWORD": password})
    if takt_min:
        cfg.values["plugin_cycle_interval_seconds"] = takt_min * 60
    renders.clear()
    clock["now"], calls = start, 0
    while clock["now"] <= end:
        before = len(renders)
        plugin.generate_image(dict(settings), cfg)
        calls += 1
        if VERBOSE:
            print(f"    {clock['now']:%H:%M:%S} {'neu' if len(renders) > before else 'Cache'}")
        clock["now"] += timedelta(minutes=takt_min or 5) + DRIFT
    got = [t.strftime("%H:%M") for t in renders]
    if got != want:
        fails += 1
        print(f"FEHLER {name}\n       neu um {got}\n       erwartet {want}")
    else:
        print(f"ok     {name}: {len(got)} von {calls} Runden neu")


def at(h, m):
    return START.replace(hour=h, minute=m)


def schedule(start, takt_min, end):
    """Alle Aufrufzeiten wie in run()."""
    t, out = start, []
    while t <= end:
        out.append(t)
        t += timedelta(minutes=takt_min) + DRIFT
    return out


def pick(start, takt_min, end, rounds):
    """Uhrzeiten (HH:MM) der Runden mit den Nummern `rounds` (0 = erste Runde)."""
    s = schedule(start, takt_min, end)
    return [s[i].strftime("%H:%M") for i in rounds if i < len(s)]


# Vormittag nach dem Nachrichtenfenster (bis 9:30) – keine Grenze im Weg
A, B = at(9, 35), at(11, 40)
every3 = range(0, 100, 3)
run("Zug aus, Takt 5 min → alle 15 min", {"trainEnabled": "false"}, 5, A, B, pick(A, 5, B, every3))
run("Zug an ohne Wochentag, außerhalb des Fensters → alle 15 min", {"trainEnabled": "true"}, 5, A, B,
    pick(A, 5, B, every3))
# Im Zeitfenster 6:30–8:15 (Nachrichtenfenster läuft 6:00–9:30, Grenzen also nicht dazwischen)
C, D = at(6, 35), at(8, 10)
run("Zug an ohne Wochentag, im Zeitfenster → alle 15 min", {"trainEnabled": "true"}, 5, C, D, pick(C, 5, D, every3))
run("Zug an, Dienstag, im Zeitfenster → alle 5 min", {"trainEnabled": "true", "trainDi": "true"}, 5, C, D,
    pick(C, 5, D, range(100)))
run("Zug an, nur Mittwoch (heute nicht) → alle 15 min", {"trainEnabled": "true", "trainMi": "true"}, 5, C, D,
    pick(C, 5, D, every3))
run("Sonst alle 30 min, Zug aus", {"trainEnabled": "false", "quietMinutes": "30"}, 5, A, B,
    pick(A, 5, B, range(0, 100, 6)))
for takt in (10, 15, 20):
    run(f"Takt {takt} min, Zug aus → jede Runde neu (nie verlängert)", {"trainEnabled": "false"}, takt, A, B,
        pick(A, takt, B, range(100)))
run("Takt 15 min, Sonst alle 30 → alle 30 min", {"trainEnabled": "false", "quietMinutes": "30"}, 15, A, B,
    pick(A, 15, B, range(0, 100, 2)))

# Grenzen: Nachrichten ab 6:00, Zugfenster ab 6:30, nach 8:15 wieder Ruhetakt
E, F = at(5, 47), at(6, 50)
s = schedule(E, 5, F)  # 5:47, 5:52:07, 5:57:14, 6:02:21, …
run("Nachrichten ab 6:00: erste Runde danach neu, Zug aus", {"trainEnabled": "false"}, 5, E, F,
    [s[i].strftime("%H:%M") for i in (0, 3, 6, 9, 12) if i < len(s)])
G, H = at(5, 47), at(8, 50)
s = schedule(G, 5, H)
hm = lambda t: t.time().replace(second=0)  # noqa: E731  wie bahn.in_window: auf Minuten abgeschnitten
inside = [i for i, t in enumerate(s) if at(6, 30).time() <= hm(t) <= at(8, 15).time()]
after = inside[-1] + 1
# 5:47 neu, 6:02 Nachrichten, 6:17 nach 15 min, 6:27 Cache (Fenster erst 6:30), im Fenster jede
# Runde, danach erst wieder ein Bild in den Cache (8:20) und von da an alle 15 min
idx = [0, 3, 6] + inside + list(range(after, len(s), 3))
run("Zug Dienstag 6:30–8:15: davor 15 min, im Fenster 5 min, danach 15 min",
    {"trainEnabled": "true", "trainDi": "true"}, 5, G, H, [s[i].strftime("%H:%M") for i in idx])

run("Takt unbekannt: 1 min Toleranz wie bisher", {"trainEnabled": "false"}, None, A, B, pick(A, 5, B, every3))

# Nachtbild (23–6 Uhr): mit „Nachts ruhig halten“ einmal pro Nacht, mit „Lebende Stadt“ (seit 1.43) stündlich
N0, N1 = START.replace(hour=22, minute=50), START.replace(hour=22, minute=50) + timedelta(hours=7, minutes=30)
s = schedule(N0, 15, N1)
first = next(i for i, t in enumerate(s) if t.hour == 23)
hourly = [first] + [next(i for i, t in enumerate(s) if t >= (N0 + timedelta(hours=k)).replace(minute=0))
                    for k in range(2, 8)]
morning = next(i for i, t in enumerate(s) if 6 <= t.hour < 12)  # nach dem Nachtbild wieder alle 15 min
day = list(range(morning, len(s)))
NIGHT = {"trainEnabled": "false", "nightEnabled": "true", "nightArt": "true", "nightFreeze": "true"}
run("Nachtbild ohne Lebende Stadt: einmal pro Nacht", dict(NIGHT, liveCity="false"), 15, N0, N1,
    [s[i].strftime("%H:%M") for i in [0, first] + day])
run("Nachtbild mit Lebender Stadt: stündlich (seit 1.43)", dict(NIGHT, liveCity="true"), 15, N0, N1,
    [s[i].strftime("%H:%M") for i in sorted(set([0] + hourly + day))])

print("alles ok" if not fails else f"{fails} Fehler")
caldav_server.stop() if hasattr(caldav_server, "stop") else None
sys.exit(1 if fails else 0)
