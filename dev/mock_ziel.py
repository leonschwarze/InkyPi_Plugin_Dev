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
# Name -> (lat, lon, Land, Ländercode, GeoNames-Klasse, Einwohner); wie die echte Antwort von Open-Meteo
CITIES = {"lyon": (45.764, 4.836, "Frankreich", "FR", "PPLA", 522_000),
          "wien": (48.208, 16.373, "Österreich", "AT", "PPLC", 1_900_000),
          "paris": (48.857, 2.352, "Frankreich", "FR", "PPLC", 2_100_000),
          "rom": (41.893, 12.483, "Italien", "IT", "PPLC", 2_800_000),
          # Wetter am Zielort (seit 1.30): Termine im Rheinland, dazu Fallen für die Erkennung
          "düsseldorf": (51.2217, 6.7762, "Deutschland", "DE", "PPLA", 620_000),
          "eschweiler": (50.8169, 6.2652, "Deutschland", "DE", "PPLA4", 56_000),
          "köln": (50.9333, 6.95, "Deutschland", "DE", "PPLA2", 1_080_000),
          "bad godesberg": (50.6842, 7.1556, "Deutschland", "DE", "PPLX", 0),
          "siegburg": (50.8015, 7.2044, "Deutschland", "DE", "PPLA4", 41_000),
          "post": (33.1912, -101.3790, "Vereinigte Staaten", "US", "PPLA2", 5_000),   # aus „Post Tower“
          "stadthaus": (52.5, 13.4, "Deutschland", "DE", "BLDG", 0)}                  # ein Gebäude, kein Ort


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
            return _Resp({"results": [{"name": ((params or {}).get("name") or "").strip().title(),
                                       "latitude": hit[0], "longitude": hit[1], "country": hit[2],
                                       "country_code": hit[3], "feature_code": hit[4], "population": hit[5]}]})
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
        if "api.brightsky.dev" in url and url.endswith("/weather") and params and float(params["lat"]) > 51:
            # Düsseldorf (Wetter am Zielort): 2 Grad kälter, heute 14–17 Uhr Regen
            data = resp.json()
            for rec in data["weather"]:
                rec["temperature"] = (rec.get("temperature") or 0) - 2
                h = int(rec["timestamp"][11:13])
                if rec["timestamp"][:10] == now.date().isoformat() and 15 <= h <= 17:
                    rec.update(precipitation=0.9, precipitation_probability=80, cloud_cover=100, icon="rain",
                               condition="rain")
            return _Resp(data)
        if "api.brightsky.dev" in url and url.endswith("/weather") and params and float(params["lon"]) < 6.5:
            # Eschweiler (Wetter am Zielort): 3 Grad kälter, trocken
            data = resp.json()
            for rec in data["weather"]:
                rec["temperature"] = (rec.get("temperature") or 0) - 3
                rec.update(precipitation=0.0, precipitation_probability=10)
                if rec.get("icon") in ("rain", "showers-day", "showers-night", "sleet", "snow"):
                    rec["icon"] = "cloudy"
            return _Resp(data)
        return resp
    requests.Session.get = fake_get
