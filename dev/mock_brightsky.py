"""Simulierte Antworten der Bright-Sky-API (DWD-Daten) für Tests ohne Internet.

Die Daten sind relativ zu einem festen Zeitpunkt `now` aufgebaut:
  Tag 0 (heute):  wechselhaft, ab 17 Uhr Regen (im Szenario "sommer" mit Starkregen)
  Tag 1:          sonnig
  Tag 2:          bedeckt
  Tag 3:          Regen am Tag
  Tag 4:          Gewitter am Nachmittag
  Tag 5:          Nebel am Morgen
  Tag 6:          freundlich

Szenarien: "herbst" (Standard), "winter" (Schnee statt Regen, Frost),
"sommer" (Hitze, Unwetterwarnung), "ruhig" (wie herbst, aber ohne Warnungen),
"klar" (abends trocken, klare feuchte Nacht mit Tau und Bewölkung < 30 % – auch fürs Nachtbild
"sternklar"), "trocken" (abends trocken, trockene windige Nacht).
Die beiden letzten sind für die Wäsche-Karte; sie haben keine Warnungen.
"reif" (seit 1.37): klare, feuchte Frostnacht bis heute Abend trocken – morgens Reif (Glätte-Hinweis), mittags
Lauf-Fenster.
"nebel" und "bedeckt" (wie herbst, aber die kommende Nacht neblig bzw. bedeckt) für das Nachtbild.
"regennacht" (seit 1.43): Regen und volle Bewölkung von 17 bis 9 Uhr – Mond verdeckt, Dachkatze im Nachtbild.
"""
import math
from datetime import datetime, timedelta

import requests

_real_get = requests.Session.get


def hourly(now, scenario="herbst", shift=None):
    """shift = {Tag: Grad}, verschiebt die Temperatur eines Tages (für „4° kälter als gestern“, seit 1.22)."""
    tz = now.tzinfo
    # ab gestern 0 Uhr: das Tagesdashboard vergleicht seit 1.22 mit dem Vortag (Tag -1 = Beobachtungen)
    start = datetime.combine(now.date() - timedelta(days=1), datetime.min.time(), tz)
    shift = shift or {}
    recs = []
    for h in range(8 * 24 + 27):  # Ende wie bisher (Tag 7, 3 Uhr)
        dt = start + timedelta(hours=h)
        day = (dt.date() - now.date()).days
        hour = dt.hour
        if scenario == "winter":
            base, amp = -3 + day * 0.4, 3
        elif scenario == "sommer":
            base, amp = 24 + (day % 3), 7
        elif scenario == "reif" and day <= 1:  # seit 1.37: klare Frostnacht, morgens Reif (Glätte-Hinweis)
            base, amp = 0.5, 4
        else:
            base, amp = 8 - day * 0.3, 3.5
        temp = base + amp * math.sin((hour - 9) / 24 * 2 * math.pi) + shift.get(day, 0)
        is_day = 7 <= hour < 17
        cloud, precip, prob, sunshine = 60, 0, 10, 0
        icon = "partly-cloudy-day" if is_day else "partly-cloudy-night"
        if day == 0 and 17 <= hour <= 23 and scenario not in ("klar", "trocken"):
            cloud, icon, precip, prob = 100, "rain", [0.2, 0.8, 1.6, 2.4, 1.1, 0.5, 0.2][hour - 17], 85
            if scenario == "sommer":  # Gewitter mit Starkregen am Abend
                precip = round(precip * 2.5, 1)
        elif day == 1:
            cloud = 15 if is_day else 30
            icon = "clear-day" if is_day else "clear-night"
            sunshine, prob = (55 if is_day else 0), 5
        elif day == 2:
            cloud, icon, prob = 95, "cloudy", 20
        elif day == 3 and 10 <= hour <= 18:
            cloud, icon, precip, prob = 65, "rain", 0.6, 60
        elif day == 4 and 12 <= hour <= 16:
            icon, precip, prob, cloud = "thunderstorm", 3.5, 70, 90
        elif day == 5:
            icon, cloud, prob = ("fog" if hour < 11 else "cloudy"), 100, 10
        elif day == 6:
            cloud, sunshine = 40, (30 if is_day else 0)
        if scenario == "nebel" and day == 1 and hour < 9:
            icon, cloud, precip, prob = "fog", 100, 0, 10
        if scenario == "gewitter" and day == 0 and 12 <= hour <= 18:  # seit 1.35: Katze bei Gewitter
            icon, precip, prob, cloud = "thunderstorm", 4.0, 80, 95
        if scenario == "nebeltag" and day == 0 and hour < 12:  # seit 1.35: Katze bei Nebel (tagsüber)
            icon, cloud, precip, prob = "fog", 100, 0, 10
        if scenario == "bedeckt" and day == 1:
            icon, cloud = "cloudy", 95
        # seit 1.43: verregnete Nacht (Mond verdeckt → Dachkatze), auch für Uhrzeiten nach Mitternacht
        if scenario == "regennacht" and (day == 0 and (hour >= 17 or hour < 9) or day == 1 and hour < 9):
            icon, cloud, precip, prob = "rain", 100, 0.6, 90
        if scenario == "regenbogen" and day == 0 and 14 <= hour <= 16:  # Schauer bei Sonne (Ostereier: Regenbogen)
            icon, cloud, precip, prob, sunshine = "rain", 60, 0.4, 60, 25
        if scenario == "reif" and day <= 0:  # klar und trocken bis heute Abend (danach wie herbst)
            precip, prob = 0, 5
            cloud = 15 if not (day == 0 and hour >= 17) else 60
            icon = ("clear-day" if is_day else "clear-night") if cloud < 30 else icon
            sunshine = 50 if is_day else 0
        if scenario == "winter" and icon == "rain":
            icon = "snow"
        if is_day and cloud < 80 and day != 1:
            sunshine = sunshine or 20
        night = hour >= 18 or hour < 9
        rh, spread, wind = 82, 3, 16
        if scenario == "klar" and night:
            rh, spread, wind = 96, 0.8, 6
        elif scenario == "trocken":
            rh, spread, wind = 62, 8, 14
        elif scenario == "reif":
            rh, spread, wind = (95, 0.5, 4) if night else (70, 4, 8)
        if scenario == "klar" and day in (0, 1) and (hour >= 17 or hour < 7):
            cloud = 20  # heute Nacht sternklar (< 30 %), für das Nachtbild (nachtgrafik.describe);
                        # day 0 und 1, weil die Nacht über Mitternacht in den nächsten Kalendertag fällt
        recs.append({
            "timestamp": dt.isoformat(),
            "source_id": 1234 if dt < now else 5678,
            "cloud_cover": cloud,
            "condition": ("snow" if icon == "snow" else "rain") if precip else "dry",
            "dew_point": round(temp - spread, 1),
            "icon": icon,
            "precipitation": precip,
            "precipitation_probability": None if dt < now else prob,  # Beobachtungen haben keine
            "pressure_msl": 1018 - h * 0.08,
            "relative_humidity": rh,
            "sunshine": sunshine,
            "temperature": round(temp, 1),
            "visibility": 24000,
            "wind_direction": 230,
            "wind_gust_speed": 38 if not (day == 0 and hour >= 17) else 45,
            "wind_speed": wind,
        })
    return {"weather": recs, "sources": [
        {"id": 1234, "station_name": "BONN-ROLEBER", "distance": 7800, "observation_type": "current"},
        {"id": 5678, "station_name": "BONN-ROLEBER", "distance": 7800, "observation_type": "forecast"},
    ]}


def current(now, scenario="herbst"):
    temp = {"winter": -1.8, "sommer": 31.4, "reif": -2.6}.get(scenario, 10.6)
    return {"weather": {
        "source_id": 1234, "timestamp": now.isoformat(), "cloud_cover": 15 if scenario == "reif" else 75,
        "condition": "dry", "dew_point": 6.9,
        "icon": {"winter": "snow", "reif": "clear-day"}.get(scenario, "partly-cloudy-day"),
        "precipitation_60": 0.6 if scenario == "winter" else 0.0, "pressure_msl": 1013.4,
        "relative_humidity": 45 if scenario == "sommer" else 78, "temperature": temp, "visibility": 24000,
        "wind_direction_10": 230, "wind_speed_10": 17.3, "wind_gust_speed_10": 38.9, "sunshine_60": 12,
    }, "sources": [{"id": 1234, "station_name": "BONN-ROLEBER", "distance": 7800}]}


def alerts(now, scenario="herbst"):
    loc = {"warn_cell_id": 105314000, "name": "Stadt Bonn", "name_short": "Bonn",
           "district": "Bonn", "state": "Nordrhein-Westfalen", "state_short": "NW"}
    if scenario in ("ruhig", "klar", "trocken", "nebel", "bedeckt", "reif"):
        return {"alerts": [], "location": loc}
    sev = "severe" if scenario == "sommer" else "moderate"
    ev = {"sommer": "SCHWERES GEWITTER mit ORKANBÖEN", "winter": "GLÄTTE"}.get(scenario, "STURMBÖEN")
    return {"alerts": [
        {"id": 1, "status": "actual", "onset": (now - timedelta(hours=1)).isoformat(),
         "expires": (now + timedelta(hours=15)).isoformat(), "severity": sev,
         "event_de": ev, "headline_de": f"Amtliche WARNUNG vor {ev}"},
        {"id": 2, "status": "actual", "onset": (now + timedelta(hours=9)).isoformat(),
         "expires": (now + timedelta(hours=18)).isoformat(), "severity": "minor",
         "event_de": "FROST", "headline_de": "Amtliche WARNUNG vor FROST"},
    ], "location": loc}


def uvi(now, scenario="herbst"):
    """Nachbildung von opendata.dwd.de/climate_environment/health/alerts/uvi.json"""
    werte = {"sommer": (7, 8, 6), "winter": (0, 0, 1)}.get(scenario, (1, 1, 0))
    def eintrag(city, delta=0):
        t, m, u = (max(v + delta, 0) for v in werte)
        return {"city": city, "forecast": {"today": t, "tomorrow": m, "dayafter_to": u}}
    return {"content": [eintrag("Kahler Asten", 1), eintrag("Bonn"), eintrag("Köln"), eintrag("Frankfurt/Main", 1)],
            "last_update": now.strftime("%Y-%m-%dT10:00:00"), "name": "UV-Gefahrenindex"}


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def install(now, scenario="herbst", fail=False, fail_uv=False, shift=None):
    """Leitet Bright-Sky- und DWD-UV-Anfragen auf die simulierten Daten um."""
    def fake_get(session, url, params=None, timeout=None, **kw):
        if "opendata.dwd.de" in url and url.endswith("uvi.json"):
            return _Resp({}, 404) if (fail or fail_uv) else _Resp(uvi(now, scenario))
        if "api.brightsky.dev" in url:
            if fail:
                raise requests.ConnectionError("simulierter Ausfall")
            if url.endswith("/weather"):
                return _Resp(hourly(now, scenario, shift))
            if url.endswith("/current_weather"):
                return _Resp(current(now, scenario))
            if url.endswith("/alerts"):
                return _Resp(alerts(now, scenario))
            return _Resp({}, 404)
        return _real_get(session, url, params=params, timeout=timeout, **kw)
    requests.Session.get = fake_get
