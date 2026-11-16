"""Simulierte Antwort von PEGELONLINE (Pegel Bonn, W/measurements.json?start=P1D) für dev/render.py --pegel.

Szenarien:
  keine     HTTP 404 – kein Pegel, der Rhein bleibt wie bisher (Standard, damit andere Renders gleich bleiben)
  niedrig   1,16 m, seit gestern −4 cm (ohne Pfeil, Schwelle 5 cm) – so stand der Rhein im November 2026
  faellt    1,16 m, seit gestern −12 cm (Pfeil nach unten)
  normal    3,80 m, +2 cm
  hoch      7,60 m, +35 cm (Ufer überflutet, Pfeil nach oben)
  sehrhoch  10,10 m, +20 cm (großes Hochwasser, Wasser an der Brücke)
  alt       letzter Wert 8 Stunden alt – zählt nicht, Rhein wie bisher
  down      HTTP 503
Werte alle 15 Minuten über 24 Stunden, gleichmäßig vom Stand gestern zum Stand jetzt.
"""
from datetime import timedelta

import requests

SCENARIOS = {
    "niedrig": (116, -4), "faellt": (116, -12), "normal": (380, 2), "hoch": (760, 35), "sehrhoch": (1010, 20),
    "alt": (116, -4),
}


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def payload(now, kind):
    cm, diff = SCENARIOS[kind]
    end = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    if kind == "alt":
        end -= timedelta(hours=8)
    steps = 24 * 4
    return [{"timestamp": (end - timedelta(minutes=15 * (steps - i))).isoformat(),
             "value": round(cm - diff + diff * i / steps, 1)} for i in range(steps + 1)]


def install(now, kind="keine"):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "pegelonline.wsv.de" in url:
            if kind == "keine":
                return _Resp(None, 404)
            if kind == "down":
                return _Resp(None, 503)
            return _Resp(payload(now, kind))
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
