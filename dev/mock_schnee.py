"""Simulierte Antwort von Open-Meteo /v1/dwd-icon (Schnee-Radar, seit 1.42) für dev/render.py --schnee.

Damit Schnee-Karte und Tageskurve zueinander passen, wird der Wetter-Ort aus denselben Stundenwerten gebaut,
die dev/mock_brightsky.py für das Szenario liefert: Schnee fällt dort, wo Bright Sky Schnee meldet
(0,7 cm je mm wie Open-Meteo), die Schneehöhe wächst bei Frost und taut darüber langsam weg. Die Umlandorte
sind kälter (0,65 °C je 100 m) und bekommen 30 % mehr Niederschlag; geschneit wird dort bei ≤ 0,5 °C.

Szenarien:
  normal       wie oben (Standard; im Szenario „herbst“ liegt nirgends Schnee → Bild wie bisher)
  umland       zusätzlich Schnee im Bergland: Winterberg 18 cm, Hohe Acht 4 cm (und was in der Woche fällt)
  liegt        in Bonn liegen 3 cm (Schneekappen im Nachtbild), im Umland mehr
  schneeregen  Schneefallgrenze 350 m: in Bonn eher Schneeregen
  taut         Schnee fällt, bleibt aber nicht liegen (Boden warm)
  weihnachten  wie liegt, und am 24.–26.12. morgens 2 cm in Bonn
  down         HTTP 503
Höhen: Bonn 60 m, Ölberg 460 m, Hohe Acht 747 m, Winterberg (Kahler Asten) 842 m.
"""
from datetime import datetime

import requests

ELEV = {"Winterberg": 842, "Hohe Acht": 747, "Ölberg": 460}
HOME_ELEV = 60
BASE = {"umland": {"Winterberg": 18, "Hohe Acht": 4}, "liegt": {"Winterberg": 25, "Hohe Acht": 9, "Ölberg": 4},
        "weihnachten": {"Winterberg": 25, "Hohe Acht": 9, "Ölberg": 4}}
HOME_BASE = {"liegt": 3.0, "weihnachten": 3.0}


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def series(records, elev, kind, base=0.0, home=True):
    """Stundenwerte eines Ortes aus den Bright-Sky-Testdaten."""
    dz = (elev - HOME_ELEV) * 0.0065
    out = {k: [] for k in ("time", "snowfall", "snow_depth", "snowfall_height", "temperature_2m", "precipitation")}
    depth = base
    for r in records:
        dt = datetime.fromisoformat(r["timestamp"])
        temp = r["temperature"] - dz
        precip = (r.get("precipitation") or 0) * (1.0 if home else 1.0 + elev / 1500)  # Staulagen: mehr Niederschlag
        if home:
            snowy = precip >= 0.05 and r.get("condition") == "snow"
        else:
            snowy = precip >= 0.05 and temp <= 0.5
        if kind == "schneeregen" and home:
            snowy = False  # in Bonn Regen/Schneeregen, Schnee erst weiter oben
        sf = round(precip * 0.7, 2) if snowy else 0.0
        if kind == "taut" and home:
            depth = 0.0
        else:
            depth += sf
            if temp > 1:
                depth = max(0.0, depth - 0.15 * (temp - 1))
            if kind in ("liegt", "weihnachten") or (kind == "umland" and not home):
                depth = max(depth, base)
        if kind == "weihnachten" and home and dt.month == 12 and dt.day in (24, 25, 26):
            depth = max(depth, 2.0)
        line = (350 if kind == "schneeregen" else 100) if precip >= 0.05 and temp < 4 else 1400
        out["time"].append(int(dt.timestamp()))
        out["snowfall"].append(sf)
        out["snow_depth"].append(round(depth / 100, 3))
        out["snowfall_height"].append(line)
        out["temperature_2m"].append(round(temp, 1))
        out["precipitation"].append(round(precip, 1))
    return out


def payload(now, kind, scenario, params):
    import mock_brightsky
    records = mock_brightsky.hourly(now, scenario)["weather"]
    lats = params["latitude"].split(",")
    items = []
    names = list(ELEV) + ["home"]
    for i, _ in enumerate(lats):
        name = names[i] if i < len(names) else "home"
        if i == len(lats) - 1:
            items.append({"elevation": HOME_ELEV,
                          "hourly": series(records, HOME_ELEV, kind, HOME_BASE.get(kind, 0.0), home=True)})
        else:
            items.append({"elevation": ELEV[name],
                          "hourly": series(records, ELEV[name], kind, BASE.get(kind, {}).get(name, 0.0), home=False)})
    return items


def install(now, kind="normal", scenario="herbst"):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "api.open-meteo.com/v1/dwd-icon" in url:
            if kind == "down":
                return _Resp(None, 503)
            return _Resp(payload(now, kind, scenario, params or {}))
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
