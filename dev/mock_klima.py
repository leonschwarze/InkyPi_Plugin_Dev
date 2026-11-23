"""Simulierte DWD-Tageswerte (Climate Data Center, daily/kl) für dev/render.py --klima (seit 1.41).

Erfunden, aber im Bonner Klima: Mittel nach den Normalwerten 1991–2020 von Köln/Bonn (Januar ~3 °C,
Juli ~19 °C), Tagesgang im Winter ~4°, im Sommer ~9°, Abweichungen als AR(1)-Reihe (σ ≈ 3°), dazu Regen
und Sonne. Historische Reihe 1957-07-01 bis 2025-12-31, aktuelle Reihe die letzten 550 Tage bis gestern.

Szenarien (die aktuelle Reihe wird je nach Szenario gesetzt, damit genau ein Meilenstein kommt – oder keiner):
  normal    Standard: kein Meilenstein (Frost, Schnee, Eistag, 30°, Tropennacht vor ein paar Tagen, keine
            langen Serien), Kurve mit „üblich“; Karte nur, wenn das Wetter-Szenario selbst extrem ist
            (winter → „Ungewöhnlich kalt“, sommer → „Ungewöhnlich warm“)
  frost     letzter Frost am 12. März (mit --scenario reif: „Erster Frost seit 12. März“; Nachtbild ebenso)
  sonne     die letzten 9 Tage ohne Sonne (mit --scenario trocken/reif: „Erstmals Sonne seit 9 Tagen“)
  regen     die letzten 7 Tage Regen, längste Serie des Jahres bisher 6 (mit herbst: „Längste Regenserie: 8 Tage“)
  trocken   die letzten 17 Tage trocken, längste bisher 15 (mit --scenario trocken: „… Trockenphase …: 18 Tage“)
  schnee    letzter Schnee am 3. Februar (mit --scenario winter: „Erster Schnee seit 3. Februar“)
  mild      Klima 2° kälter und weniger schwankend, am Kalendertag von heute 2015 besonders warm
            (mit --scenario trocken am 24.11.: Karte „Ungewöhnlich mild · 12° statt 7° · so mild zuletzt …“)
  beispiel  mild + sonne (Screenshots docs/klima_*.png: Karte, Kurve und Meilenstein zugleich)
  fern      keine Station im Umkreis (nur Dresden in der Liste): nichts, kein Ausfall
  keine     HTTP 404 überall (Ausfall „Klimadaten“)
  down      HTTP 503 überall
Die Datei mit den Klimadaten liegt je Lauf in einem eigenen Temp-Ordner (klima.state_path wird ersetzt).
"""
import io
import math
import os
import random
import tempfile
import zipfile
from datetime import date, timedelta

import requests

STATIONS = [  # id, von, bis, Höhe, Breite, Länge, Name
    (598, "18910101", "20070331", 62, 50.7285, 7.0839, "Bonn"),
    (603, "19860801", None, 159, 50.7352, 7.1913, "Bonn-Roleber"),
    (2667, "19570701", None, 92, 50.8645, 7.1575, "Köln/Bonn"),
    (1048, "19340101", None, 228, 51.1278, 13.7543, "Dresden-Klotzsche"),
]
HIST_FROM, HIST_TO = date(1957, 7, 1), date(2025, 12, 31)
HEAD = "STATIONS_ID;MESS_DATUM;QN_3;  FX;  FM;QN_4; RSK;RSKF; SDK;SHK_TAG;  NM; VPM;  PM; TMK; UPM; TXK; TNK; TGK;eor"


class _Resp:
    def __init__(self, content=b"", status=200):
        self.status_code, self.content = status, content
        self.text = content.decode("latin-1") if isinstance(content, bytes) else content


def climate(start, end, seed=7, shift=0.0, sigma=2.2):
    """Erfundene Tageswerte {date: dict} im Bonner Klima."""
    rnd = random.Random(seed)
    out, a, d = {}, 0.0, start
    while d <= end:
        doy = d.timetuple().tm_yday
        c = math.cos(2 * math.pi * (doy - 18) / 365.25)
        mean = 10.9 - 8.1 * c + 0.025 * (d.year - 1990) + shift
        rng = 6.5 + 2.5 * -c
        a = 0.7 * a + rnd.gauss(0, sigma)
        wet = rnd.random() < 0.5
        rsk = round(rnd.expovariate(1 / 3.0), 1) if wet else 0.0
        sdk = round(max(0.0, rnd.gauss(4.2 - 2.8 * c, 2.0)), 1)
        tx, tn = mean + rng / 2 + a, mean - rng / 2 + 0.8 * a
        out[d] = {"tx": round(tx, 1), "tn": round(tn, 1), "rsk": rsk, "rskf": (7 if tn < -1 else 6) if wet else 0,
                  "sdk": sdk, "shk": 0}
        d += timedelta(days=1)
    return out


def recent(today, kind):
    """Die letzten 550 Tage bis gestern, je nach Szenario mit gesetzten Tagen."""
    start, end = today - timedelta(days=550), today - timedelta(days=1)
    days = climate(start, end, seed=11)
    y = lambda n: today - timedelta(days=n)  # noqa: E731
    if kind == "beispiel":
        kind = "sonne"
    if kind in ("normal", "mild", "sonne", "regen", "trocken"):
        # kurze Serien, regelmäßig Sonne – und alle „ersten“ kurz vorher, damit nichts davon neu ist
        for i, d in enumerate(sorted(days)):
            days[d]["rsk"] = 2.0 if i % 3 == 0 else (0.4 if i % 3 == 1 else 0.0)
            days[d]["sdk"] = 3.0 if i % 2 == 0 else 0.4
        days[y(4)].update(tn=-1.0, tx=-0.5, rskf=7, rsk=1.0, shk=2)
        days[y(5)].update(tx=31.0, tn=21.0)
    if kind == "frost":
        for d in days:
            if d >= date(today.year, 3, 12):
                days[d]["tn"] = max(days[d]["tn"], 0.5)
                days[d]["tx"] = max(days[d]["tx"], days[d]["tn"] + 2)
        days[date(today.year, 3, 12)]["tn"] = -1.4
    if kind == "sonne":
        for n in range(1, 10):
            days[y(n)]["sdk"] = 0.1 * (n % 3)
        days[y(10)]["sdk"] = 2.5
    if kind == "regen":
        for n in range(1, 8):
            days[y(n)]["rsk"] = 2.5 + n % 3
        days[y(8)]["rsk"] = 0.0
        for n in range(30, 36):   # längste bisher: 6 Tage
            days[y(n)]["rsk"] = 3.0
    if kind == "trocken":
        for n in range(1, 18):
            days[y(n)]["rsk"] = 0.0
        days[y(18)]["rsk"] = 4.0
        for n in range(40, 55):   # längste bisher: 15 Tage
            days[y(n)]["rsk"] = 0.0
        days[y(39)]["rsk"] = days[y(55)]["rsk"] = 2.0
    if kind == "schnee":
        for d in days:
            days[d].update(rskf=6 if days[d]["rsk"] else 0, shk=0)
        days[date(today.year, 2, 3)].update(rskf=7, rsk=3.0, shk=4)
    return days


def product_zip(station_id, days):
    rows = [HEAD]
    for d in sorted(days):
        v = days[d]
        rows.append(f"{station_id:>11};{d:%Y%m%d};   10;   8.0;   3.2;    3;{v['rsk']:5.1f};   {v['rskf']};"
                    f"{v['sdk']:5.1f};      {v['shk']};  6.1;  9.0;1002.3;{(v['tx'] + v['tn']) / 2:5.1f};  80.0;"
                    f"{v['tx']:5.1f};{v['tn']:5.1f};-999;eor")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"produkt_klima_tag_{min(days):%Y%m%d}_{max(days):%Y%m%d}_{station_id:05d}.txt",
                    "\n".join(rows).encode("latin-1"))
        zf.writestr(f"Metadaten_Geographie_{station_id:05d}.txt", "erfunden")
    return buf.getvalue()


def stations_text(today, kind):
    lines = ["Stations_id von_datum bis_datum Stationshoehe geoBreite geoLaenge Stationsname Bundesland Abgabe",
             "----------- --------- --------- ------------- --------- --------- ----------------------------------------- ---------- ------"]
    for sid, von, bis, h, lat, lon, name in STATIONS:
        if kind == "fern" and sid != 1048:
            continue
        bis = bis or f"{today - timedelta(days=1):%Y%m%d}"
        land = "Sachsen" if sid == 1048 else "Nordrhein-Westfalen"
        lines.append(f"{sid:05d} {von} {bis} {h:14d} {lat:11.4f} {lon:9.4f} {name:<40} {land:<40} Frei")
    return "\n".join(lines).encode("latin-1")


def listing():
    names = [f"tageswerte_KL_{sid:05d}_{max(von, '19570701')}_{HIST_TO:%Y%m%d}_hist.zip"
             for sid, von, *_ in STATIONS if sid != 598] + ["tageswerte_KL_00598_18910101_20070331_hist.zip"]
    return ("<html><body><pre>" + "".join(f'<a href="{n}">{n}</a>  22-Mar-2026 10:00  304783\n' for n in names)
            + "</pre></body></html>").encode()


def install(now, kind, klima):
    """requests.Session.get für opendata.dwd.de/…/daily/kl/ ersetzen und eine eigene Klimadatei nutzen."""
    today = now.date()
    cache = {}
    folder = tempfile.mkdtemp(prefix="inkypi-klima-")
    klima.state_path = lambda device_config: os.path.join(folder, klima.STATE_FILE)
    previous = requests.Session.get

    def hist():
        if "hist" not in cache:
            mild = kind in ("mild", "beispiel")
            days = climate(HIST_FROM, HIST_TO, shift=-2.0 if mild else 0.0, sigma=1.4 if mild else 2.2)
            if mild:
                days[date(2015, today.month, today.day)]["tx"] = 13.2
            cache["hist"] = product_zip(603, days)
        return cache["hist"]

    def fake_get(session, url, *a, **kw):
        if "climate/daily/kl/" in url:
            if kind in ("keine", "down"):
                return _Resp(b"", 404 if kind == "keine" else 503)
            name = url.rsplit("/", 1)[-1]
            if name.startswith("KL_Tageswerte_Beschreibung_Stationen"):
                return _Resp(stations_text(today, kind))
            if url.endswith("/historical/"):
                return _Resp(listing())
            if name.endswith("_hist.zip"):
                return _Resp(hist())
            if name.endswith("_akt.zip"):
                return _Resp(product_zip(603, recent(today, kind)))
            return _Resp(b"", 404)
        return previous(session, url, *a, **kw)

    requests.Session.get = fake_get
