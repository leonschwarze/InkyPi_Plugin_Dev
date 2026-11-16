"""Simulierte Antworten für Reiseziel-Wetter (Urlaubsbild) und ISS-Bahndaten (Celestrak).

  * Open-Meteo-Geocoding: ein paar Städte, alles andere „nicht gefunden“.
  * Bright Sky für Orte südlich von 48° N (Lyon, Wien liegt nördlich): wärmer und sonniger als
    zu Hause, damit auf der Tafel zwei verschiedene Spalten zu sehen sind.
  * Celestrak: eine erfundene, aber formal gültige ISS-Bahn (Neigung 51,64°, 15,5 Umläufe pro Tag)
    mit Epoche „gestern“. Die Überflugzeiten sind damit NICHT die echten – sie prüfen nur den Ablauf.
"""
from datetime import datetime, timedelta, timezone

import requests

_prev = requests.Session.get
CITIES = {"lyon": (45.764, 4.836, "Frankreich"), "wien": (48.208, 16.373, "Österreich"),
          "paris": (48.857, 2.352, "Frankreich"), "rom": (41.893, 12.483, "Italien")}


class _Resp:
    def __init__(self, data=None, status=200, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        return self._data


def checksum(line):
    return sum(int(c) if c.isdigit() else 1 if c == "-" else 0 for c in line[:68]) % 10


def tle_text(now, ecc="0006703"):
    ep = (now - timedelta(days=1)).astimezone(timezone.utc)
    day = (ep - datetime(ep.year, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400 + 1
    l1 = f"1 25544U 98067A   {ep.year % 100:02d}{day:012.8f}  .00016717  00000-0  10270-3 0  900"
    l2 = f"2 25544  51.6400 247.4627 {ecc} 130.5360 325.0288 15.50000000 100"
    return f"ISS (ZARYA)\n{l1}{checksum(l1)}\n{l2}{checksum(l2)}\n"


def install(now):
    def fake_get(session, url, params=None, timeout=None, **kw):
        if "geocoding-api.open-meteo.com" in url:
            hit = CITIES.get(((params or {}).get("name") or "").strip().lower())
            if not hit:
                return _Resp({"generationtime_ms": 0.3})
            return _Resp({"results": [{"latitude": hit[0], "longitude": hit[1], "country": hit[2]}]})
        if "celestrak.org" in url:
            return _Resp(text=tle_text(now))
        resp = _prev(session, url, params=params, timeout=timeout, **kw)
        if "api.brightsky.dev" in url and url.endswith("/weather") and params and float(params["lat"]) < 48:
            data = resp.json()
            for rec in data["weather"]:
                rec["temperature"] = (rec.get("temperature") or 0) + 4
                if rec["timestamp"][:10] == now.date().isoformat():
                    rec.update(precipitation=0.0, precipitation_probability=5, cloud_cover=20,
                               icon="clear-day" if "clear" in rec.get("icon", "") or 7 <= int(rec["timestamp"][11:13]) < 17
                               else "clear-night", condition="dry")
            return _Resp(data)
        return resp
    requests.Session.get = fake_get
