"""Simulierte Kp-Vorhersage der NOAA (noaa-planetary-k-index-forecast.json) für dev/render.py --polar (seit 1.37).

Szenarien:
  keine   HTTP 404 – keine Daten, das Nachtbild bleibt wie bisher (Standard, damit andere Renders gleich bleiben)
  ruhig   Kp 1–3 (normaler Tag: kein Polarlicht)
  kp6     Kp 6 am Abend (zu schwach für Bonn: nichts)
  kp7     Kp 7 ab 21 Uhr Ortszeit (Polarlicht möglich)
  kp8     Kp 8,33 ab 21 Uhr (stark: mit roten Spitzen)
  alt     Kp 7 in der Fassung vor 2025 (Liste von Listen mit Kopfzeile)
  down    HTTP 503
Abschnitte alle 3 Stunden in UTC, von gestern bis übermorgen.
"""
from datetime import datetime, timedelta, timezone

import requests

PEAK = {"ruhig": 2.67, "kp6": 6.0, "kp7": 7.0, "kp8": 8.33, "alt": 7.0}


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def payload(now, kind):
    start = datetime.combine(now.date() - timedelta(days=1), datetime.min.time(), timezone.utc)
    peak = PEAK[kind]
    peak_at = (datetime.combine(now.date(), datetime.min.time(), now.tzinfo) + timedelta(hours=21)).astimezone(timezone.utc)
    rows = []
    for i in range(3 * 8):
        t = start + timedelta(hours=3 * i)
        kp = 1.67 + (i % 3) * 0.33
        if peak_at - timedelta(hours=2) <= t <= peak_at + timedelta(hours=4):
            kp = peak
        kind_txt = "observed" if t < now.astimezone(timezone.utc) else "predicted"
        rows.append({"time_tag": t.strftime("%Y-%m-%dT%H:%M:%S"), "kp": round(kp, 2), "observed": kind_txt,
                     "noaa_scale": None if kp < 5 else f"G{min(5, int(kp) - 4)}"})
    if kind == "alt":
        return [["time_tag", "kp", "observed", "noaa_scale"]] + [
            [r["time_tag"].replace("T", " "), f"{r['kp']:.2f}", r["observed"], r["noaa_scale"]] for r in rows]
    return rows


def install(now, kind="keine"):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "services.swpc.noaa.gov" in url:
            if kind == "keine":
                return _Resp(None, 404)
            if kind == "down":
                return _Resp(None, 503)
            return _Resp(payload(now, kind))
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
