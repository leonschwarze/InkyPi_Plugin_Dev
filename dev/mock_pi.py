"""Simulierter Zustand des Pi für dev/render.py --pi (Fußzeile der Wochenvorschau, pizustand.py).

Ersetzt pizustand.read_system (sonst stünden Laufzeit und Speicher des Entwicklungsrechners im Bild)
und legt die Zustandsdatei in einen frischen Temp-Ordner, vorbelegt mit einer Woche Geschichte.

Szenarien (Zeiten relativ zur Renderzeit, z. B. So 15.11. 19:10):
  ok       23 Tage online, Woche bis 52 °C, 9,8 GB frei, keine Ausfälle (Standard)
  ausfall  wie ok, dazu Kalender 2× weg (zusammen 40 min, zuletzt Do 3:10)
  warn     Neustart Mi 14:02, Unterspannung, Internet weg Di 2:10–2:50 (Wetter und Kalender), bis 71 °C, 1,2 GB frei
  leer     keine Messwerte (wie auf einem Rechner ohne Pi), keine Geschichte
"""
import os
import tempfile
from datetime import timedelta


def _at(now, days_back, hh, mm):
    return (now - timedelta(days=days_back)).replace(hour=hh, minute=mm, second=0, microsecond=0)


def install(now, kind, pizustand):
    folder = tempfile.mkdtemp(prefix="inkypi-pi-")
    path = os.path.join(folder, pizustand.STATE_FILE)
    state = pizustand.empty()
    iso = pizustand._iso
    system = {"uptime": 23 * 86400 + 5 * 3600, "temp": 41.3, "free": 9.8e9, "volt": {"now": False, "since_boot": False}}
    state["temp"] = {(now - timedelta(days=k)).date().isoformat(): t
                     for k, t in enumerate([41.3, 44.0, 52.2, 47.5, 45.1, 43.0, 42.2])}
    if kind == "ausfall":
        for start, end in ((_at(now, 4, 22, 0), _at(now, 4, 22, 15)), (_at(now, 3, 3, 10), _at(now, 3, 3, 35))):
            state["episodes"].append({"src": "Kalender", "start": iso(start), "last": iso(end - timedelta(minutes=15)),
                                      "end": iso(end)})
    elif kind == "warn":
        boot = _at(now, 4, 14, 2)
        system = {"uptime": (now - boot).total_seconds(), "temp": 58.0, "free": 1.2e9,
                  "volt": {"now": False, "since_boot": True}}
        state["temp"][(now - timedelta(days=2)).date().isoformat()] = 71.4
        for src in ("Wetter", "Kalender"):
            state["episodes"].append({"src": src, "start": iso(_at(now, 5, 2, 10)), "last": iso(_at(now, 5, 2, 40)),
                                      "end": iso(_at(now, 5, 2, 50))})
    elif kind == "leer":
        system, state = {}, pizustand.empty()
    pizustand.save(path, state)
    pizustand.read_system = lambda: dict(system)
    pizustand.state_path = lambda device_config: path
    return path
