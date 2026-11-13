"""
Simuliertes Regenradar (Bright Sky /radar, format=compressed) für das Tagesdashboard.

Regenzellen ziehen mit 30 km/h von Südwest nach Nordost; geliefert wird der angefragte Ausschnitt
(distance → (2·distance/1000 + 1)² Bildpunkte, Ort in der Mitte).
Szenarien (render.py --radar ...):
  schauer   ein Schauer erreicht den Ort in ~25 min, dauert ~25 min; ab ~90 min eine Regenfront
  jetzt     es regnet gerade, Ende in ~35 min, danach trocken
  dauer     Landregen, hält über zwei Stunden an
  trocken   Zellen ziehen vorbei, der Ort bleibt trocken
  down      Radar nicht erreichbar
"""

import base64
import math
import zlib
from array import array
from datetime import datetime, timedelta

import requests

SCENARIOS = ["schauer", "jetzt", "dauer", "trocken", "down"]
V = (21.2, 21.2)  # km/h nach Osten, Norden (30 km/h aus Südwest)


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def _cells(scenario):
    """(km entlang der Zugbahn bis zum Ort bei t=0, km quer dazu, sigma längs, sigma quer, Spitze mm/h)."""
    if scenario == "schauer":
        return [(-17, 0.5, 2.6, 3.2, 2.2),       # Schauer: trifft in ~25 min
                (-8, 9, 2.5, 2.5, 3.0),          # zieht nördlich vorbei
                (-60, 0, 6, 60, 2.6),            # Front: ab ~90 min
                (6, -10, 2.0, 2.0, 1.5)]         # schon durchgezogen, im Südosten
    if scenario == "jetzt":
        return [(-4, 0, 6, 9, 1.6), (-3, -11, 2.5, 2.5, 4.5)]
    if scenario == "dauer":
        return [(0, 0, 40, 80, 1.2)]
    if scenario == "trocken":
        return [(-15, 10, 2.5, 2.5, 2.5), (5, -11, 3, 2.5, 1.8)]
    return []


def field(t_min, scenario, N=31):
    sp = math.hypot(*V)
    ax, ay = V[0] / sp, V[1] / sp      # Einheitsvektor längs der Zugbahn
    qx, qy = -ay, ax                    # quer dazu
    shift = sp * t_min / 60
    out = array("h", [0] * (N * N))
    c = N // 2
    for row in range(N):
        for col in range(N):
            x, y = col - c, c - row     # km Ost, Nord
            along, across = x * ax + y * ay, x * qx + y * qy
            v = 0.0
            for d, q, sl, sq, peak in _cells(scenario):
                a = along - (d + shift)
                v += peak * math.exp(-(a * a) / (2 * sl * sl) - ((across - q) ** 2) / (2 * sq * sq))
            if scenario == "dauer":
                v = 1.2 + 0.5 * math.sin((along + shift) / 4) if v > 0.6 else v
            out[row * N + col] = int(round(v / 0.12)) if v >= 0.05 else 0
    return base64.b64encode(zlib.compress(out.tobytes())).decode()


def install(now, scenario):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "api.brightsky.dev/radar" in url:
            if scenario == "down":
                raise requests.ConnectionError("simulierter Ausfall Radar")
            start = datetime.fromisoformat(params["date"])
            end = datetime.fromisoformat(params["last_date"])
            frames, t = [], start
            while t <= end:
                t_min = (t - now).total_seconds() / 60
                n = 2 * int(params.get("distance", 200000)) // 1000 + 1
                frames.append({"timestamp": t.isoformat(), "source": "RADOLAN::RV::mock",
                               "precipitation_5": field(t_min, scenario, n)})
                t += timedelta(minutes=5)
            return _Resp({"radar": frames, "latlon_position": {"x": 15.5, "y": 15.5}})
        return previous(session, url, params=params, timeout=timeout, **kw)
    requests.Session.get = fake_get
