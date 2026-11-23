"""Klimaeinordnung und Wetter-Meilensteine (tagesdashboard/klima.py) ohne Rendern (seit 1.41).

  python dev/test_klima.py

Prüft: Stationsliste und Stationswahl (Entfernung, Höhe, Zeitraum, zu weit), Dateinamen im Verzeichnis,
Produktdatei (fehlende Werte), Normalwerte (Fenster, 29. Februar, zu wenig Werte, Grenzen 5/95 %), Karte bei
Ausreißern (beide Grenzen nötig, Wörter je Jahreszeit, „Morgen“, „zuletzt“/Rekord), Kopfzeile der Kurve,
Tagesgang der üblichen Temperatur, alle Meilensteine (Abstand 90 Tage, Lücken in der Reihe, Vorrang, Nacht nur
Frost/Tropennacht, Sonne nach grauen Tagen, Serien erst ab Mitte Februar und nur als Jahresrekord), Laden gegen
dev/mock_klima.py (Abrufe zählen, Datei, erneutes Laden nur bei Bedarf, Ortswechsel, Ausfall mit Wartezeit,
Statusmeldungen, keine Station).
"""
import json
import math
import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import requests  # noqa: E402

import klima  # noqa: E402
import mock_klima  # noqa: E402
import status  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 24, 10, 20, tzinfo=TZ)


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def hours(d, tn, tx, rain=0.0, sun=0.0, snow=False, n=24):
    """Stündliche Werte wie Bright Sky: Tiefstwert um 6 Uhr, Höchstwert um 15 Uhr."""
    out = []
    for h in range(n):
        f = (1 - math.cos(math.pi * (h - 6) / 9)) / 2 if 6 <= h <= 15 else (1 + math.cos(math.pi * ((h - 15) % 24) / 15)) / 2
        out.append({"dt": datetime.combine(d, time(h), TZ), "temperature": tn + (tx - tn) * f,
                    "precipitation": rain / 24, "sunshine": sun * 60 / 10 if 7 <= h <= 16 else 0,
                    "icon": "snow" if snow and rain else ("rain" if rain else "cloudy")})
    return out


def kl(days, normals=None, tx_by_day=None, first_year=1957):
    """Klima-Objekt aus erfundenen Tageswerten {date: (tn, tx, rsk, sdk[, rskf, shk])}."""
    rec = {d.isoformat(): [v[0], v[1], v[2], v[4] if len(v) > 4 else 0, v[3], v[5] if len(v) > 5 else 0]
           for d, v in days.items()}
    return klima.Klima({"normals": normals or {}, "tx_by_day": tx_by_day or {}, "first_year": first_year,
                        "recent": {"days": rec}})


def mild_days(today, n=400, tn=5.0, tx=10.0, rsk=0.4, sdk=3.0):
    """Unauffällige Reihe bis gestern: nichts davon ist ein Meilenstein."""
    days = {}
    for i in range(1, n + 1):
        d = today - timedelta(days=i)
        days[d] = (tn, tx, rsk if i % 2 else 2.0, sdk)
    return days


# ---- Stationsliste und Wahl ------------------------------------------------
text = mock_klima.stations_text(NOW.date(), "normal").decode("latin-1")
st = klima.parse_stations(text)
check("Stationsliste: vier Stationen gelesen", [s["id"] for s in st] == [598, 603, 2667, 1048])
check("Name mit Leerzeichen/Schrägstrich", st[2]["name"] == "Köln/Bonn" and st[1]["name"] == "Bonn-Roleber")
best = klima.choose_station(st, 50.7333, 7.1000, NOW.date())
check("nächste noch messende Station mit Reihe ab 1991: Bonn-Roleber (Bonn endete 2007)", best["id"] == 603)
mid = (50.80, 7.174)  # etwa gleich weit von Bonn-Roleber (159 m) und Köln/Bonn (92 m)
check("Höhe zählt: Ort auf 90 m → Köln/Bonn", klima.choose_station(st, *mid, NOW.date(), height=90)["id"] == 2667)
check("Höhe zählt: Ort auf 160 m → Bonn-Roleber", klima.choose_station(st, *mid, NOW.date(), height=160)["id"] == 603)
check("zu weit (Hamburg): keine Station", klima.choose_station(st, 53.55, 9.99, NOW.date()) is None)
young = [dict(s, von="19950101") if s["id"] in (603, 2667) else s for s in st]
check("Reihe erst ab 1995: zählt nicht", klima.choose_station(young, 50.7333, 7.1, NOW.date()) is None)

listing = mock_klima.listing().decode()
check("Verzeichnis: Dateiname der Station gefunden", klima.hist_names(listing, 603) == ["tageswerte_KL_00603_19860801_20251231_hist.zip"])
check("Verzeichnis: andere Nummer nicht", klima.hist_names(listing, 60) == [])

raw = mock_klima.product_zip(603, {date(2026, 1, 1): {"tx": 3.0, "tn": -999, "rsk": 0.0, "rskf": 0, "sdk": 1.0, "shk": 0}})
p = klima.parse_product(raw)
check("Produktdatei: -999 = fehlt", p[date(2026, 1, 1)]["tn"] is None and p[date(2026, 1, 1)]["tx"] == 3.0)

# ---- Normalwerte ----------------------------------------------------------
days = {}
d = date(1991, 1, 1)
while d <= date(2020, 12, 31):
    days[d] = {"tn": 2.0, "tx": 10.0 + (d.year % 10), "rsk": 0, "rskf": 0, "sdk": 0, "shk": 0}
    d += timedelta(days=1)
days[date(1985, 6, 1)] = {"tn": 50.0, "tx": 60.0, "rsk": 0, "rskf": 0, "sdk": 0, "shk": 0}
norm = klima.build_normals(days)
check("Normalwerte für alle 365 Kalendertage", len(norm) == 365)
check("nur 1991–2020 (1985 zählt nicht)", norm["06-01"][1] == 14.5 and norm["06-01"][0] == 2.0)
check("5-/95-%-Grenze aus den Werten des Fensters", norm["06-01"][2] == 10.0 and norm["06-01"][3] == 19.0)
check("29. Februar nimmt den 28.", kl({}, normals=norm).normal(date(2024, 2, 29)) == tuple(norm["02-28"]))
few = {k: v for k, v in days.items() if k.year <= 1995}
check("zu wenige Werte (5 Jahre): keine Normalwerte", klima.build_normals(few) == {})
check("Perzentil wie numpy", klima.percentile([1, 2, 3, 4, 5], 95) == 4.8 and klima.percentile([7], 5) == 7)

# ---- Karte bei Ausreißern ---------------------------------------------------
today = NOW.date()
N = {klima.day_key(today): [3.0, 8.0, 3.5, 11.0], klima.day_key(today + timedelta(days=1)): [3.0, 8.0, 3.5, 11.0],
     klima.day_key(date(2026, 7, 15)): [14.0, 24.0, 18.0, 30.0]}
TXD = {klima.day_key(today): [[2015, 12.4], [2019, 11.0], [2003, 13.5]]}
k = kl(mild_days(today), normals=N, tx_by_day=TXD)
c = klima.card(k, hours(today, 4, 12.0), today, today)
check("12° bei üblich 8° (95 % = 11°): Karte „Ungewöhnlich mild“", c and c["top"] == "Ungewöhnlich mild" and c["dir"] == "warm")
check("Text: Werte und letztes Jahr, das mindestens so warm war", c and c["sub"] == "12° statt 8° · so mild zuletzt 2015")
check("Abzeichen +4°", c and c["badge"] == "+4°")
c = klima.card(k, hours(today, 4, 14.0), today, today)
check("noch nie so warm: „Rekord seit 1957“", c and c["sub"].endswith("Rekord seit 1957"))
check("über 95 %, aber nur +2,5°: keine Karte",
      klima.card(kl({}, normals={klima.day_key(today): [3.0, 8.0, 3.5, 10.0]}), hours(today, 4, 10.5), today, today) is None)
check("+3,5°, aber unter 95 %: keine Karte", klima.card(k, hours(today, 4, 10.9), today, today) is None)
c = klima.card(k, hours(today, -6, 1.0), today, today)
check("Kälte: „Ungewöhnlich kalt“, −7°", c and c["top"] == "Ungewöhnlich kalt" and c["badge"] == "-7°" and c["dir"] == "kalt")
c = klima.card(k, hours(today + timedelta(days=1), 4, 12.0), today + timedelta(days=1), today)
check("abends für morgen: „Morgen ungewöhnlich mild“", c and c["top"] == "Morgen ungewöhnlich mild")
c = klima.card(k, hours(date(2026, 7, 15), 18, 33.0), date(2026, 7, 15), date(2026, 7, 15))
check("33° im Juli: „warm“ statt „mild“", c and c["top"] == "Ungewöhnlich warm")
c = klima.card(k, hours(date(2026, 7, 15), 10, 17.0), date(2026, 7, 15), date(2026, 7, 15))
check("17° im Juli: „kühl“", c and c["top"] == "Ungewöhnlich kühl")
c = klima.card(k, hours(today, 12, 21.0), today, today)
check("21° im November: „warm“, nicht „mild“", c and c["top"] == "Ungewöhnlich warm")
check("ohne Normalwerte: keine Karte", klima.card(kl({}), hours(today, 4, 20.0), today, today) is None)
check("ohne volle Stunden: keine Karte", klima.card(k, hours(today, 4, 14.0, n=10), today, today) is None)
k2 = kl({date(2025, 11, 24): (5, 13.0, 0, 0)}, normals=N, tx_by_day={klima.day_key(today): [[2015, 12.4]]})
c = klima.card(k2, hours(today, 4, 12.0), today, today)
check("letztes Jahr aus den aktuellen Tageswerten (2025)", c and c["sub"].endswith("zuletzt 2025"))

# ---- Kopfzeile der Kurve ------------------------------------------------------
cv = klima.curve(k, hours(today, 4, 12.0), today, "Kein Regen mehr erwartet")
check("Kurve: Normalwerte und „Tagsüber 4° wärmer als üblich“", cv and (cv["tn"], cv["tx"]) == (3.0, 8.0)
      and cv["head"] == "Tagsüber 4° wärmer als üblich")
check("mit Regen bleibt die Regenzeile (head None)", klima.curve(k, hours(today, 4, 12.0), today, "Regen 17–23 Uhr · 6,8 mm")["head"] is None)
check("„Kaum Regen“ bleibt auch", klima.curve(k, hours(today, 4, 12.0), today, "Kaum Regen · Risiko bis 40 %")["head"] is None)
check("gleich: „so warm wie üblich“", klima.curve(k, hours(today, 4, 8.3), today, "Kein Regen erwartet")["head"]
      == "Tagsüber so warm wie üblich")
check("kälter", klima.curve(k, hours(today, -2, 3.0), today, "Kein Regen erwartet")["head"] == "Tagsüber 5° kälter als üblich")

# ---- Tagesgang der üblichen Temperatur (tagesdashboard.Tagesdashboard.normal_course) ----
sys.path.insert(0, str(ROOT.parent / "InkyPi" / "src"))
try:
    import importlib
    td = importlib.import_module("plugins.tagesdashboard.tagesdashboard")
    rise = datetime.combine(today, time(8, 0), TZ)
    pts = hours(today, 0, 1)
    course = td.Tagesdashboard.normal_course(pts, (3.0, 9.0), lambda dd: (rise, rise + timedelta(hours=8)))
    check("Tagesgang: Tiefstwert zum Sonnenaufgang (8 Uhr)", abs(course[8] - 3.0) < 0.01 and min(course) >= 3.0 - 1e-9)
    check("Tagesgang: Höchstwert um 14 Uhr (Normalzeit)", abs(course[14] - 9.0) < 0.01 and max(course) <= 9.0 + 1e-9)
    summer = [dict(r, dt=r["dt"].replace(month=7, day=15)) for r in pts]
    course = td.Tagesdashboard.normal_course(summer, (14.0, 24.0), lambda dd: (rise.replace(month=7, day=15, hour=5), None))
    check("Sommerzeit: Höchstwert um 15 Uhr", abs(course[15] - 24.0) < 0.01 and course[14] < 24.0)
except ImportError as exc:
    print(f"(Tagesgang übersprungen, InkyPi fehlt: {exc})")


# ---- Meilensteine -------------------------------------------------------------
def frosty(days, when, tn=-1.0):
    days[when] = (tn,) + days[when][1:]
    return days


base = mild_days(today)
m = klima.milestone(kl(frosty(dict(base), date(2026, 3, 12))), hours(today, -4, 4), today)
check("Erster Frost seit 12. März", m and m["text"] == "Erster Frost seit 12. März" and m["short"] == "Erster Frost seit 12.3."
      and m["color"] == "kalt")
check("Frost vor 20 Tagen: nichts", klima.milestone(kl(frosty(dict(base), today - timedelta(days=20))),
                                                     hours(today, -4, 4), today) is None)
check("Frost genau 90 Tage her: nichts (mehr als 90 nötig)",
      klima.milestone(kl(frosty(dict(base), today - timedelta(days=90))), hours(today, -4, 4), today) is None)
gap = frosty(dict(base), date(2026, 3, 12))
for i in range(30, 35):
    gap.pop(today - timedelta(days=i))
check("fünf fehlende Tage seitdem: lieber nichts", klima.milestone(kl(gap), hours(today, -4, 4), today) is None)
check("gar kein Frost in 400 Tagen: „seit über einem Jahr“",
      klima.milestone(kl(base), hours(today, -4, 4), today)["text"] == "Erster Frost seit über einem Jahr")
check("kurze Reihe ohne Frost: nichts", klima.milestone(kl(mild_days(today, n=200)), hours(today, -4, 4), today) is None)
eis = frosty(dict(base), date(2026, 3, 12))
eis[date(2026, 2, 3)] = (-6.0, -1.0, 0, 0)
m = klima.milestone(kl(eis), hours(today, -6, -1), today)
check("Eistag geht dem Frost vor: „Erster Eistag seit 3. Februar“", m and m["kind"] == "eistag" and m["text"].endswith("3. Februar"))
sn = frosty(dict(base), today - timedelta(days=10))
sn[date(2026, 2, 3)] = (-2.0, 1.0, 3.0, 0, 7, 4)
m = klima.milestone(kl(sn), hours(today, -2, 1, rain=5.0, snow=True), today)
check("Schnee: „Erster Schnee seit 3. Februar“", m and m["kind"] == "schnee" and m["text"] == "Erster Schnee seit 3. Februar")
day = date(2026, 6, 20)
hot = mild_days(day, tn=12, tx=22)
hot[date(2025, 9, 18)] = (14, 26.0, 0, 8)
hot[date(2025, 8, 2)] = (19, 31.0, 0, 10)
m = klima.milestone(kl(hot), hours(day, 15, 27), day)
check("Erster Sommertag seit 18. September", m and m["text"] == "Erster Sommertag seit 18. September" and m["color"] == "warm")
m = klima.milestone(kl(hot), hours(day, 18, 31), day)
check("30° geht dem Sommertag vor: „Erstmals 30° seit 2. August“", m and m["text"] == "Erstmals 30° seit 2. August")
hot[date(2025, 8, 3)] = (21.0, 30.0, 0, 9)
hot[day - timedelta(days=10)] = (15.0, 27.0, 0, 9)   # Sommertag vor 10 Tagen: der ist nicht mehr neu
trop = hours(day, 19, 29) + hours(day + timedelta(days=1), 21, 30)
for r in trop:
    if r["dt"].date() == day + timedelta(days=1) and r["dt"].hour < 9:
        r["temperature"] = max(r["temperature"], 21.0)
    if r["dt"].date() == day and r["dt"].hour >= 18:
        r["temperature"] = max(r["temperature"], 22.0)
m = klima.milestone(kl(hot), trop, day)
check("Tropennacht (kommende Nacht nicht unter 20°)", m and m["kind"] == "tropennacht" and m["text"].endswith("3. August"))
# Nachtbild: nur Frost und Tropennacht, und nur wenn die Nacht selbst so ist
night = (datetime.combine(today, time(23, 0), TZ), datetime.combine(today + timedelta(days=1), time(6, 0), TZ))
recs = hours(today, 1, 5) + hours(today + timedelta(days=1), -3, 4)
m = klima.milestone(kl(frosty(dict(base), date(2026, 3, 12))), recs, today, night=night)
check("Nachtbild: Frost in der kommenden Nacht", m and m["kind"] == "frost")
recs_warm = hours(today, -2, 5) + hours(today + timedelta(days=1), 2, 6)
check("Nachtbild: Frost nur am Morgen, Nacht frostfrei: nichts",
      klima.milestone(kl(frosty(dict(base), date(2026, 3, 12))), recs_warm, today, night=night) is None)
sun_days = dict(base)
for i in range(1, 10):
    sun_days[today - timedelta(days=i)] = (5.0, 10.0, 0.4, 0.2)
check("Sonne nach 9 grauen Tagen", klima.milestone(kl(sun_days), hours(today, 4, 10, sun=3), today)["text"]
      == "Erstmals Sonne seit 9 Tagen")
check("nur 1 Stunde Sonne: nichts", klima.milestone(kl(sun_days), hours(today, 4, 10, sun=1), today) is None)
short_grey = dict(base)
for i in range(1, 6):
    short_grey[today - timedelta(days=i)] = (5.0, 10.0, 0.4, 0.2)
check("nur 5 graue Tage: nichts", klima.milestone(kl(short_grey), hours(today, 4, 10, sun=3), today) is None)
wet = dict(base)
for i in range(1, 8):
    wet[today - timedelta(days=i)] = (5.0, 10.0, 3.0, 3.0)
wet[today - timedelta(days=8)] = (5.0, 10.0, 0.0, 3.0)
for i in range(30, 36):
    wet[today - timedelta(days=i)] = (5.0, 10.0, 3.0, 3.0)
m = klima.milestone(kl(wet), hours(today, 4, 10, rain=6), today)
check("8. Regentag in Folge, längste Serie des Jahres", m and m["text"] == "Längste Regenserie 2026: 8 Tage" and m["short"] == "8 Tage Regen")
for i in range(40, 49):
    wet[today - timedelta(days=i)] = (5.0, 10.0, 3.0, 3.0)
check("früher im Jahr schon 9 Tage: nichts", klima.milestone(kl(wet), hours(today, 4, 10, rain=6), today) is None)
dry = {}
for i in range(1, 400):
    dd = today - timedelta(days=i)
    dry[dd] = (5.0, 10.0, 0.0 if i < 18 or 40 <= i < 55 else 2.0, 3.0)
m = klima.milestone(kl(dry), hours(today, 4, 10), today)
check("18 Tage trocken (bisher 15): längste Trockenphase", m and m["text"] == "Längste Trockenphase 2026: 18 Tage")
jan = date(2027, 1, 20)
jw = {jan - timedelta(days=i): (5.0, 10.0, 3.0 if i < 6 else (0.0 if i % 2 else 2.0), 3.0) for i in range(1, 400)}
check("Ende Januar: Serien noch nicht", klima.milestone(kl(jw), hours(jan, 4, 10, rain=6), jan) is None)
check("ohne Klimadaten: nichts", klima.milestone(None, hours(today, -4, 4), today) is None)

# Reihe: fehlt gestern beim DWD, kommt er aus Bright Sky
k3 = kl({today - timedelta(days=i): (5.0, 10.0, 0.4, 3.0) for i in range(2, 30)})
ser = k3.series(hours(today - timedelta(days=1), -3, 2) + hours(today, 1, 5), today)
check("gestern aus Bright Sky ergänzt", ser[today - timedelta(days=1)]["tn"] == -3)
check("heute immer aus der Vorhersage", ser[today]["tx"] == 5)

# ---- Laden gegen den Mock ---------------------------------------------------------
calls = []
folder = tempfile.mkdtemp(prefix="test-klima-")


def load(kind, now=NOW, lat=50.7333, lon=7.1, new_file=False):
    global folder
    if new_file:
        folder = tempfile.mkdtemp(prefix="test-klima-")
    mock_klima.install(now, kind, klima)
    inner = requests.Session.get

    def counting(session, url, *a, **kw):
        calls.append(url.rsplit("/", 1)[-1] or "historical/")
        return inner(session, url, *a, **kw)
    requests.Session.get = counting
    status.reset()
    status.begin()
    k = klima.ensure(lat, lon, now, os.path.join(folder, klima.STATE_FILE))
    status.commit(now)
    return k


klima.reset()
calls.clear()
k = load("normal", new_file=True)
check("erster Start: Stationsliste, Verzeichnis, historische und aktuelle Werte (4 Abrufe)", len(calls) == 4)
check("Normalwerte und Tageswerte bis gestern", k.normal(today) and max(k.recent) == today - timedelta(days=1))
saved = json.load(open(os.path.join(folder, klima.STATE_FILE)))
check("Datei geschrieben (Station, Normalwerte, Tageswerte)", saved["station"]["id"] == 603 and len(saved["normals"]) == 365
      and saved["version"] == klima.STATE_VERSION)
check("Status ok", status.report(NOW) == [])
calls.clear()
klima.reset()  # wie nach einem Neustart: aus der Datei
k = load("normal")
check("nach Neustart: nichts neu geladen", calls == [] and k.normal(today))
calls.clear()
k = load("normal", now=NOW + timedelta(days=1))
check("nächster Tag: nur die aktuellen Werte", calls == ["tageswerte_KL_00603_akt.zip"])
calls.clear()
load("normal", lat=50.94, lon=6.96)
check("Ortswechsel nach Köln (25 km): Station und Werte neu", "KL_Tageswerte_Beschreibung_Stationen.txt" in calls and len(calls) == 4)
klima.reset()
calls.clear()
k = load("down", new_file=True)
check("DWD nicht erreichbar: None und „Klimadaten“ im Status", k is None and [s["name"] for s in status.report(NOW)] == ["Klimadaten"])
calls.clear()
k = load("down", now=NOW + timedelta(minutes=20))
check("Fehlschlag: 60 min kein neuer Versuch", calls == [] and k is None)
klima.reset()
k = load("fern", new_file=True)
check("keine Station in der Nähe: None, aber kein Ausfall", k is None and status.report(NOW) == [])
# historische Werte fehlen, aktuelle da: Meilensteine gehen, Karte nicht
klima.reset()
mock_klima.install(NOW, "normal", klima)
real = requests.Session.get


def no_hist(session, url, *a, **kw):
    if url.endswith("_hist.zip"):
        return mock_klima._Resp(b"", 404)
    return real(session, url, *a, **kw)


requests.Session.get = no_hist
status.reset()
status.begin()
k = klima.ensure(50.7333, 7.1, NOW, os.path.join(tempfile.mkdtemp(), klima.STATE_FILE))
status.commit(NOW)
check("ohne historische Werte: Objekt da, ohne Normalwerte, mit Tageswerten", k and not k.normal(today) and k.recent)
check("… und „Klimadaten“ im Status", [s["name"] for s in status.report(NOW)] == ["Klimadaten"])
status.begin()
k = klima.ensure(50.7333, 7.1, NOW + timedelta(minutes=15), klima._state["path"])
status.commit(NOW + timedelta(minutes=15))
check("in der Wartezeit bleibt der Ausfall stehen (kein „ok“ zwischendurch)",
      [s["name"] for s in status.report(NOW + timedelta(minutes=15))] == ["Klimadaten"])

# ---- Symbole ----------------------------------------------------------------------
check("Fahne kalt mit Schneeflocke, warm rot ohne", "#fff" in klima.flag_svg("kalt") and "#E3001B" in klima.flag_svg("warm")
      and "#fff" not in klima.flag_svg("warm"))
check("Thermometer warm rot, kalt blau", "#E3001B" in klima.thermo_svg("warm") and "#0082C9" in klima.thermo_svg("kalt"))

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
