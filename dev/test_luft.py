"""Logik der Luftqualitäts-Karte (tagesdashboard/luft.py) ohne Rendern.

  python dev/test_luft.py

Prüft: Einstufung an den Klassengrenzen, Filter der Bürgersensoren (innen, Fehlwert, veraltet, zu wenige),
Wahl der Quelle (Feuchte, Ausfall), Ozon/NO2 nur mit Schalter, Schwelle „ab schlecht“, Zeitangaben
des Umweltbundesamts (MEZ, „24:00“) und die Glättung über eine Stunde.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import luft  # noqa: E402
import mock_luft  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 11, 13, 15, 7, tzinfo=TZ)
CFG = {"lat": 50.7374, "lon": 7.0982, "radius": 3, "level": 3, "station": "DENW062", "gases": False}
fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(("ok   " if ok else "FEHLER ") + name + ("" if ok else f": {got!r} statt {want!r}"))


class FakeSession:
    """Liefert die Mock-Antworten, zählt Abrufe."""

    def __init__(self, kind, now=NOW):
        self.kind, self.now, self.calls = kind, now, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(url)
        if "sensor.community" in url:
            check("User-Agent wird gesendet", bool(headers and headers.get("User-Agent")), True)
            data = mock_luft.community(self.now, self.kind)
            if data is None:
                raise ConnectionError("aus")
            return mock_luft._Resp(data)
        data = mock_luft.uba(self.now, self.kind)
        return mock_luft._Resp({}, 503) if data is None else mock_luft._Resp(data)


def records(rh):
    return [{"dt": NOW.replace(minute=0) + timedelta(hours=h), "relative_humidity": rh} for h in (-1, 0, 1)]


def run(kind, rh, **cfg):
    luft._cache.clear()
    luft._history.clear()
    return luft.load(dict(CFG, **cfg), NOW, records(rh), session=FakeSession(kind))


# ---- Einstufung (neuer LQI, Stundenwerte) ----
check("PM2,5 5 = sehr gut", luft.classify("pm25", 5), 1)
check("PM2,5 15 = gut", luft.classify("pm25", 15), 2)
check("PM2,5 16 = mäßig", luft.classify("pm25", 16), 3)
check("PM2,5 15,4 rundet auf 15 = gut", luft.classify("pm25", 15.4), 2)
check("PM10 54 = mäßig", luft.classify("pm10", 54), 3)
check("PM10 55 = schlecht", luft.classify("pm10", 55), 4)
check("PM10 91 = sehr schlecht", luft.classify("pm10", 91), 5)
check("Ozon 145 = schlecht", luft.classify("o3", 145), 4)
check("NO2 31 = mäßig", luft.classify("no2", 31), 3)

# ---- Bürgersensoren: Filter und Median ----
agg = luft.aggregate(mock_luft.community(NOW, "schlecht"), NOW)
check("9 Außensensoren (innen, 999,9, veraltet, BME280 weg)", (agg["n10"], agg["n25"]), (9, 9))
check("Median PM2,5 nahe 41", round(agg["pm25"]), 42)
agg = luft.aggregate(mock_luft.community(NOW, "wenige"), NOW)
check("zwei Sensoren reichen nicht", (agg["pm10"], agg["pm25"]), (None, None))
check("leere Antwort", luft.aggregate([], NOW)["pm25"], None)

# ---- Umweltbundesamt: Zeiten ----
check("MEZ 24:00 = nächster Tag 0 Uhr",
      luft._parse_cet("2026-11-13 24:00:00"), datetime(2026, 11, 14, 0, 0, tzinfo=luft.CET))
st = luft.parse_uba(mock_luft.uba(NOW, "maessig"), NOW)
check("Station: neueste Stunde", (st["pm10"], st["pm25"], st["no2"], st["o3"]), (33, 19, 28, 20))
check("Station veraltet → None", luft.parse_uba(mock_luft.uba(NOW - timedelta(hours=5), "maessig"), NOW), None)
check("Station ohne Daten → None", luft.parse_uba({"data": {}}, NOW), None)

# ---- Entscheidung ----
check("gut: keine Karte", run("gut", 60), None)
c = run("schlecht", 60)
check("trocken + schlecht: Karte aus den Sensoren", (c["badge"], c["source"], c["where"]), ("schlecht", "sensors", "9 Sensoren"))
check("Text oben", c["top"], "Feinstaub hoch")
check("Messwertzeile", c["reading"], "PM2,5 42 · PM10 71")
c = run("maessig", 60)
check("mäßig: gelbe Karte", (c["state"], c["advice"]), ("maessig", luft.ADVICE[3]))
check("ab schlecht: mäßig bleibt still", run("maessig", 60, level=4), None)
check("Nebel (Feuchte 90 %): Station gut → keine Karte", run("nebel", 90), None)
c = run("nebel", 60)
check("Nebel-Werte bei trockener Luft: Karte aus Sensoren", (c["badge"], c["source"]), ("schlecht", "sensors"))
c = run("ohnestation", 90)
check("feucht und ohne Station: Sensorwert, aber unsicher", (c["source"], c["unsure"]), ("sensors", True))
check("unsicher: Hinweis statt Rat", c["advice"], "Feucht: Sensoren zeigen oft zu viel")
check("beide aus: keine Karte", run("ausfall", 60), None)
check("zu wenige Sensoren, Station gut: keine Karte", run("wenige", 60), None)
check("Ozon ohne Schalter: keine Karte", run("ozon", 60), None)
c = run("ozon", 60, gases=True)
check("Ozon mit Schalter", (c["top"], c["reading"], c["where"]), ("Ozon hoch", "Ozon 168 µg/m³", "Station"))
c = run("sehrschlecht", 60)
check("sehr schlecht", (c["state"], c["top"]), ("sehr-schlecht", "Feinstaub sehr hoch"))

# ---- Abrufe sparen: Station nur, wenn sie etwas ändern kann ----
luft._cache.clear()
s = FakeSession("gut")
luft.load(dict(CFG), NOW, records(60), session=s)
check("trocken, Sensoren da: Station nicht abgefragt", [u for u in s.calls if "umweltbundesamt" in u], [])
luft.load(dict(CFG), NOW + timedelta(minutes=5), records(60), session=s)
check("Zwischenspeicher: kein zweiter Abruf nach 5 min", len(s.calls), 1)

# ---- Glättung: Ausreißer eines Abrufs kippt die Stunde nicht ----
luft._cache.clear()
luft._history.clear()
key = ("com", round(CFG["lat"], 3), round(CFG["lon"], 3), CFG["radius"])
luft._history[key] = [(NOW - timedelta(minutes=m), 14, 8) for m in (45, 30, 15)]
c = luft.load(dict(CFG), NOW, records(60), session=FakeSession("maessig"))
check("ein Abruf „mäßig“ nach drei guten: Mittel noch gut", c, None)
check("Verlauf hat vier Einträge", len(luft._history[key]), 4)

# ---- Einstellungen ----
opt = {"airRadius": "15", "airLevel": "4", "airStation": " denw062 "}.get
check("Radius begrenzt, Station groß", luft.read_config(opt, lambda k: k == "airEnabled", 50.7, 7.1)["radius"], 10)
check("aus → None", luft.read_config(opt, lambda k: False, 50.7, 7.1), None)
cfg = luft.read_config({"airRadius": "abc"}.get, lambda k: k == "airEnabled", 50.7, 7.1)
check("Unsinn im Radius → Standard", (cfg["radius"], cfg["level"], cfg["station"]), (3, 3, "DENW062"))

print("\nAlles ok." if not fails else f"\n{fails} Fehler.")
sys.exit(1 if fails else 0)
