"""Simulierte Antworten von sensor.community und der Luftdaten-API des Umweltbundesamts.

Szenarien (--air in dev/render.py):
  gut           Sensoren und Station gut – keine Karte (Standard, damit andere Renders gleich bleiben)
  maessig       Feinstaub mäßig (PM2,5 ≈ 22)
  schlecht      Feinstaub schlecht (PM2,5 ≈ 41)
  sehrschlecht  Neujahrsnacht: PM2,5 ≈ 120
  nebel         Sensoren zeigen „schlecht“, die Station „gut“ – bei Feuchte ≥ 80 % gilt die Station
  ozon          Feinstaub gut, Ozon schlecht (nur mit airGases=true sichtbar)
  ohnestation   wie schlecht, aber die Station antwortet nicht
  ausfall       beide Dienste antworten nicht
  wenige        nur zwei Außensensoren (zu wenige für einen Median) und die Station gut

Jedes Szenario enthält zusätzlich Störer, die das Modul ignorieren muss: einen Innensensor mit hohem
Wert, einen Sensor mit Fehlwert 999,9, eine veraltete Messung und einen BME280 ohne Feinstaub.
"""
from datetime import timedelta, timezone

import requests

# Mittelwerte der Bürgersensoren (PM10, PM2,5) und Stundenwerte der Station (PM10, PM2,5, NO2, O3)
SCENARIOS = {
    "gut": ((14, 8), (12, 7, 22, 30)),
    "maessig": ((38, 22), (33, 19, 28, 20)),
    "schlecht": ((70, 41), (63, 38, 45, 10)),
    "sehrschlecht": ((160, 120), (140, 110, 55, 8)),
    "nebel": ((48, 34), (16, 9, 24, 18)),
    "ozon": ((15, 8), (14, 8, 18, 168)),
    "ohnestation": ((70, 41), None),
    "ausfall": (None, None),
    "wenige": ((70, 41), (12, 7, 22, 30)),
}
SPREAD = [-0.18, -0.1, -0.05, 0, 0.04, 0.09, 0.15, 0.22, -0.12]  # Streuung der einzelnen Sensoren


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def community(now, kind):
    base = SCENARIOS[kind][0]
    if base is None:
        return None
    utc = now.astimezone(timezone.utc)
    n = 2 if kind == "wenige" else len(SPREAD)
    out = []

    def entry(sid, minutes_ago, p1, p2, indoor=0, typ="SDS011"):
        ts = (utc - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
        vals = [{"value_type": "P1", "value": f"{p1:.2f}"}, {"value_type": "P2", "value": f"{p2:.2f}"}]
        if typ == "BME280":
            vals = [{"value_type": "temperature", "value": "10.4"}, {"value_type": "humidity", "value": "81.2"}]
        out.append({"id": 9000 + len(out), "timestamp": ts,
                    "location": {"id": sid, "latitude": "50.73", "longitude": "7.10", "indoor": indoor, "country": "DE"},
                    "sensor": {"id": sid, "pin": "1", "sensor_type": {"id": 14, "name": typ}},
                    "sensordatavalues": vals})

    for i in range(n):
        f = 1 + SPREAD[i]
        entry(1000 + i, 1 + i % 4, base[0] * f, base[1] * f)
        entry(1000 + i, 4 + i % 4, base[0] * f * 1.03, base[1] * f * 1.03)  # zweite Messung im 5-Minuten-Fenster
    entry(2001, 2, 300, 250, indoor=1)          # Innensensor (z. B. Küche): zählt nicht
    entry(2002, 2, 999.9, 999.9)                 # Fehlwert des SDS011
    entry(2003, 45, 400, 300)                    # veraltet
    entry(2004, 1, 0, 0, typ="BME280")           # Temperatur/Feuchte, kein Feinstaub
    return out


def uba(now, kind):
    vals = SCENARIOS[kind][1]
    if vals is None:
        return None
    cet = now.astimezone(timezone(timedelta(hours=1)))
    end = cet.replace(minute=0, second=0, microsecond=0)
    data = {}
    for back in (2, 1, 0):  # die letzten drei Stunden; die neueste zählt
        e = end - timedelta(hours=back)
        s = e - timedelta(hours=1)
        k = 1 + back * 0.1
        pm10, pm25, no2, o3 = vals
        data[s.strftime("%Y-%m-%d %H:%M:%S")] = [
            e.strftime("%Y-%m-%d %H:%M:%S"), 2, 0,
            [5, round(no2 * k), 2, "0.5"], [9, round(pm25 * k), 2, "0.5"],
            [1, round(pm10 * k), 2, "0.5"], [3, round(o3 * k), 1, "0.5"],
        ]
    return {"request": {"station": "DENW062"}, "indices": {}, "data": {"1311": data}, "count": 1}


def install(now, kind="gut"):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "data.sensor.community" in url:
            data = community(now, kind)
            if data is None:
                raise requests.ConnectionError("simulierter Ausfall sensor.community")
            return _Resp(data)
        if "umweltbundesamt.de" in url:
            data = uba(now, kind)
            return _Resp({}, 503) if data is None else _Resp(data)
        return previous(session, url, params=params, timeout=timeout, **kw)
    requests.Session.get = fake_get
