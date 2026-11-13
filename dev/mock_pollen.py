"""Simulierte Antwort des DWD-Pollenflug-Gefahrenindex (s31fg.json).

Szenarien (--pollen in dev/render.py):
  gut       keine Art über „gering“ – keine Karte (Standard, damit andere Renders gleich bleiben)
  gering    Gräser gering (Wert "1")
  mittel    Birke mittel (Wert "2"), Erle gering – Karte zeigt beide
  hoch      Gräser hoch (Wert "3"), Birke mittel, Esche gering – Karte zeigt die drei stärksten
  uebergang Ambrosia im Übergang „2-3“ (gilt als hoch, der höhere Wert zählt)
  ausfall   die Datei ist nicht erreichbar

Die Teilregion ist immer 41 (Bonn, Rhein.-Westf. Tiefland), Region 40 (Nordrhein-Westfalen).
Eine zweite, nicht passende Teilregion steht zusätzlich in der Antwort, damit find_region() sie
übergehen muss.
"""
import requests

SCENARIOS = {
    "gut": {},
    "gering": {"Graeser": "1"},
    "mittel": {"Birke": "2", "Erle": "1"},
    "hoch": {"Graeser": "3", "Birke": "2", "Esche": "1"},
    "uebergang": {"Ambrosia": "2-3"},
    "ausfall": None,
}
ALL_TYPES = ("Hasel", "Erle", "Esche", "Birke", "Graeser", "Roggen", "Beifuss", "Ambrosia")


class _Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, ""

    def json(self):
        return self._data


def payload(kind):
    values = SCENARIOS[kind]
    if values is None:
        return None

    def region(region_id, partregion_id, region_name, partregion_name, today):
        return {
            "region_id": region_id, "partregion_id": partregion_id,
            "region_name": region_name, "partregion_name": partregion_name,
            "Pollen": {t: {"today": today.get(t, "0"), "tomorrow": today.get(t, "0"), "dayafter_to": "-1"}
                       for t in ALL_TYPES},
        }
    return {
        "content": [
            region(30, 32, "Niedersachsen und Bremen", "Östl. Niedersachsen", {}),  # falsche Teilregion
            region(40, 41, "Nordrhein-Westfalen", "Rhein.-Westf. Tiefland", values),
        ]
    }


def install(now, kind="gut"):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "s31fg.json" in url:
            data = payload(kind)
            if data is None:
                raise requests.ConnectionError("simulierter Ausfall DWD-Pollenflug")
            return _Resp(data)
        return previous(session, url, params=params, timeout=timeout, **kw)
    requests.Session.get = fake_get
