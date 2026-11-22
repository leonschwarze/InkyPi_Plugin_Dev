"""Simulierte NINA-Schnittstelle (warnung.bund.de/api31) für dev/render.py --nina.

Szenarien:
  keine        leere Liste (Standard, damit andere Renders gleich bleiben)
  bombe        Bombenentschärfung, Sperrgebiet um den Wetter-Ort (gilt hier), MoWaS, Severe
  fern         Bombenentschärfung in Beuel, Wetter-Ort liegt außerhalb (anderswo in Bonn)
  trinkwasser  Trinkwasserverunreinigung, Minor, ohne Gebiet (gilt als „hier“)
  zwei         bombe + trinkwasser
  dwd          nur eine DWD-Warnung (wird weggelassen, Bild wie ohne)
  entwarnung   Bombenentschärfung als msgType „Cancel“ (wird weggelassen)
  down         HTTP 503
Der Wetter-Ort der Testdaten ist 50.7374, 7.0982 (dev/render.py BASE_SETTINGS).
"""
import math

import requests

HOME = (50.7374, 7.0982)
BEUEL = (50.7395, 7.1290)


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def circle(lat, lon, r_m, n=24):
    ring = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        ring.append([round(lon + r_m / (111320 * math.cos(math.radians(lat))) * math.cos(a), 5),
                     round(lat + r_m / 110540 * math.sin(a), 5)])
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "0", "geometry": {"type": "Polygon", "coordinates": [ring]},
         "properties": {"warnId": "x"}}]}


def warnings(now):
    sent = now.replace(hour=max(0, now.hour - 1), minute=40, second=0, microsecond=0).isoformat()
    return {
        "bombe": {
            "id": "mow.DE-NW-BN-SE030-20261124-30-000", "provider": "MOWAS", "severity": "Severe",
            "msgType": "Alert", "title": "Bombenentschärfung in Bonn-Weststadt",
            "instruction": "Verlassen Sie das Sperrgebiet bis 9:00 Uhr. Folgen Sie den Anweisungen der Einsatzkräfte.<br/>",
            "area": circle(*HOME, 900), "sent": sent},
        "fern": {
            "id": "mow.DE-NW-BN-SE031-20261124-31-000", "provider": "MOWAS", "severity": "Severe",
            "msgType": "Alert", "title": "Bombenentschärfung in Bonn-Beuel",
            "instruction": "Verlassen Sie das Sperrgebiet bis 9:00 Uhr.",
            "area": circle(*BEUEL, 700), "sent": sent},
        "trinkwasser": {
            "id": "mow.DE-NW-BN-W012-20261124-000", "provider": "MOWAS", "severity": "Minor",
            "msgType": "Update", "title": "Trinkwasser abkochen in Bonn-Poppelsdorf und Kessenich",
            "instruction": "Kochen Sie Leitungswasser vor dem Trinken ab. Nutzen Sie ggf. Mineralwasser.",
            "area": None, "sent": sent},
        "dwd": {
            "id": "dwdmap.2.49.0.0.276.0.DWD.PVW.1", "provider": "DWD", "severity": "Moderate",
            "msgType": "Alert", "title": "Amtliche WARNUNG vor STURMBÖEN", "instruction": "", "area": None,
            "sent": sent},
    }


def dashboard_item(w):
    return {"id": w["id"], "payload": {"version": 2, "type": "ALERT", "id": w["id"], "hash": "0" * 64, "data": {
        "headline": w["title"], "provider": w["provider"], "severity": w["severity"], "urgency": "Immediate",
        "msgType": w["msgType"], "transKeys": {"event": "BBK-EVC-001"}, "area": {"type": "ZGEM", "data": "053140000000"},
        "valid": True}}, "i18nTitle": {"de": w["title"], "en": "Warning"}, "sent": w["sent"]}


def install(now, kind="keine"):
    previous = requests.Session.get
    all_w = warnings(now)
    picked = {"keine": [], "bombe": ["bombe"], "fern": ["fern"], "trinkwasser": ["trinkwasser"],
              "zwei": ["bombe", "trinkwasser"], "dwd": ["dwd"], "entwarnung": ["bombe"], "down": []}.get(kind, [])

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "warnung.bund.de/api31" in url:
            if kind == "down":
                return _Resp(None, 503)
            if "/dashboard/" in url:
                items = [dashboard_item(all_w[k]) for k in picked]
                if kind == "entwarnung":
                    for it in items:
                        it["payload"]["data"]["msgType"] = "Cancel"
                return _Resp(items)
            for w in all_w.values():
                if w["id"] in url:
                    if url.endswith(".geojson"):
                        return _Resp(w["area"]) if w["area"] else _Resp(None, 404)
                    return _Resp({"identifier": w["id"], "msgType": w["msgType"], "info": [
                        {"language": "DE", "headline": w["title"], "description": "…", "instruction": w["instruction"]}]})
            return _Resp(None, 404)
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
