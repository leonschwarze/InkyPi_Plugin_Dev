"""
Simulierte Antworten der VRR-Fahrplanauskunft (XML_ADDINFO_REQUEST, rapidJSON) für strecke.py.

Aufbau wie die echte Antwort vom 13.11.2026 (Leons addinfo.json), stark gekürzt.

Szenarien (render.py --strecke ...):
  ruhig      nur Meldungen, die NICHT erscheinen dürfen (Standard; das Bild bleibt wie ohne Strecke)
  stoerung   Signalstörung Köln-Mülheim–Leverkusen Mitte seit 6:40 (Orte nicht im Laufweg -> über die Stadt Köln)
  gesperrt   Strecke Remagen–Bonn-Bad Godesberg gesperrt (vor dem Einstieg)
  baustelle  Baustelle Düsseldorf–Köln-Mülheim bis 4.12. (echter Text)
  behoben    Reparatur zw. Köln Hbf und Köln Messe/Deutz beendet, vor 20 Minuten
  beides     stoerung + baustelle
  down       Auskunft nicht erreichbar

Immer dabei (dürfen nie erscheinen): RE 5 in Hessen und Hamburg (DBProd), Großbaustelle
Oberhausen–Emmerich (hinter dem Ausstieg), Strecke Düsseldorf Flughafen–Duisburg (hinter dem
Ausstieg, gleiche Stadt wie der Ausstieg), Werl–Soest (andere Linie), eine abgelaufene RE-5-Störung
bei Köln und eine Vorankündigung.
"""

import json
from datetime import timedelta, timezone

import requests

SCENARIOS = ["ruhig", "stoerung", "gesperrt", "baustelle", "behoben", "beides", "down"]

RRX = [{"id": "ddb:90RE5: :H:", "name": "Regionalzug RE5", "number": "RE5",
        "operator": {"id": "X1", "name": "National Express"}, "destination": {"name": "Koblenz Hauptbahnhof"},
        "product": {"id": 1, "class": 0}},
       {"id": "ddb:90RE5: :R:", "name": "Regionalzug RE5", "number": "RE5",
        "operator": {"id": "X1", "name": "National Express"}, "destination": {"name": "Wesel Bahnhof"},
        "product": {"id": 1, "class": 0}}]


class _Resp:
    def __init__(self, data, status=200):
        self.text = json.dumps(data, ensure_ascii=False)
        self.content = self.text.encode("utf-8")
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _info(mid, provider, title, content, created, validity, lines):
    return {
        "type": "tripMessage", "id": mid, "version": 1, "priority": "normal",
        "timestamps": {"creation": _iso(created),
                       "validity": [{"from": _iso(a), "to": _iso(b)} for a, b in validity]},
        "infoLinks": [{"urlText": "", "url": "", "title": title, "subtitle": title, "content": content}],
        "properties": {"source": {"id": provider, "name": "VRR-EMS-LIVE", "type": "EMS"}, "providerCode": provider},
        "affected": {"lines": lines},
    }


def _line(number, dest):
    return {"id": f"ddb:90{number}: :H:", "name": f"Regionalzug {number}", "number": number,
            "destination": {"name": dest}, "product": {"id": 1, "class": 0}}


def answer(now, scenario):
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    far = day + timedelta(days=21)
    infos = [
        _info("DBProd-2719244", "DBProd", "Störung.",
              "Die Ersatzverkehrsbusse der RB53 (von / nach Jossa) beginnen und enden in Schlüchtern.",
              day, [(day, far)], [{"id": "ddb:90RE5:H:H:", "number": "RE5", "name": "Regionalzug RE5",
                                   "destination": {"name": "Frankfurt (Main) Hauptbahnhof"}}]),
        _info("DBProd-2712846", "DBProd", "Bauarbeiten.",
              "Bauarbeiten: Die Züge der Linie RE 5 beginnen und enden abweichend in Hamburg-Harburg.",
              day, [(day, far)], [{"id": "ddb:90H05: :R:", "number": "RE5", "name": "Regionalzug RE5",
                                   "destination": {"name": "Stade"}}]),
        _info("ZTP-PROD-139703", "ZTP-PROD", "Großbaustelle Oberhausen Hbf - Emmerich",
              "Aufgrund des dreigleisigen Ausbaus der Strecke kommt es bei den Zügen der Linien RE 5 (RRX), RE 19, "
              "RE 44 und RE 49 zu umfangreichen Fahrplanänderungen im Bereich Oberhausen Hbf/Wesel/Bocholt/"
              "Duisburg Hbf und Bottrop Hbf.", day - timedelta(days=4), [(day - timedelta(days=4), far)],
              RRX + [_line("RE19", "Arnhem Centraal")]),
        _info("ZTP-PROD-900001", "ZTP-PROD",
              "Strecke zw. Düsseldorf Flughafen und Duisburg Hbf beeinträchtigt - Reparatur an einer Weiche",
              "Strecke zw. Düsseldorf Flughafen und Duisburg Hbf beeinträchtigt. Grund: Reparatur an einer Weiche.",
              now - timedelta(minutes=50), [(now - timedelta(minutes=55), now + timedelta(hours=6))],
              RRX + [_line("RE1", "Hamm (Westf)")]),
        _info("ZTP-PROD-141140", "ZTP-PROD", "Strecke zw. Werl und Soest beeinträchtigt - Reparatur an einem Signal",
              "Strecke zw. Werl und Soest beeinträchtigt. Grund: Reparatur an einem Signal.",
              now - timedelta(minutes=30), [(now - timedelta(minutes=30), now + timedelta(hours=4))],
              [_line("RB59", "Soest")]),
        _info("ZTP-PROD-900002", "ZTP-PROD", "Strecke zw. Köln Hbf und Köln Messe/Deutz beeinträchtigt - Polizeieinsatz",
              "Strecke zw. Köln Hbf und Köln Messe/Deutz beeinträchtigt. Grund: Polizeieinsatz.",
              day - timedelta(hours=5), [(day - timedelta(hours=5), day - timedelta(hours=2))], RRX),
        _info("ZTP-PROD-139941", "ZTP-PROD", "Vorankündigung Großbaustelle Köln Hbf",
              "Bauarbeiten vom 13.12. bis zum 9.1. zwischen Köln Hbf und Düsseldorf Hbf.",
              day - timedelta(days=10), [(day - timedelta(days=10), far)], RRX),
    ]
    if scenario in ("stoerung", "beides"):
        start = now.replace(hour=6, minute=40)
        infos.append(_info("ZTP-PROD-900010", "ZTP-PROD",
                           "Strecke zw. Köln-Mülheim und Leverkusen Mitte beeinträchtigt - Reparatur an einem Signal",
                           "Strecke zw. Köln-Mülheim und Leverkusen Mitte beeinträchtigt. Das Ende können wir leider "
                           "noch nicht abschätzen. Grund: Reparatur an einem Signal. Die Züge fahren im betroffenen "
                           "Bereich langsamer. Es kommt zu Verspätungen und Teilausfällen.",
                           start + timedelta(minutes=6), [(start, now + timedelta(hours=5))],
                           RRX + [_line("RE1", "Hamm (Westf)"), _line("S6", "Essen Hbf")]))
    if scenario == "gesperrt":
        start = now - timedelta(minutes=25)
        infos.append(_info("ZTP-PROD-900011", "ZTP-PROD",
                           "Strecke zw. Remagen und Bonn-Bad Godesberg gesperrt - Notarzteinsatz am Gleis",
                           "Strecke zw. Remagen und Bonn-Bad Godesberg gesperrt. Grund: Notarzteinsatz am Gleis.",
                           start, [(start, now + timedelta(hours=2))], RRX + [_line("RB26", "Köln Messe/Deutz")]))
    if scenario in ("baustelle", "beides"):
        infos.append(_info("ZTP-PROD-137395", "ZTP-PROD", "Maßnahmen und Fahrpläne: RE 5 (RRX)",
                           "<p>Aufgrund von Brückenarbeiten, Gleis- und Weichenerneuerungen sowie Bahnsteigarbeiten "
                           "kommt es auf der Linie RE 5 (RRX) vom 21.08.2026 (21:00 Uhr) bis zum 04.12.2026 (21:00 Uhr) "
                           "zu Umleitungen und Teilausfällen zwischen Düsseldorf Hbf und Köln-Mülheim.</p>",
                           day - timedelta(days=80),
                           [(day - timedelta(days=74), now.replace(month=12, day=4, hour=20, minute=0) if now.month < 12 else far)], RRX))
    if scenario == "behoben":
        infos.append(_info("ZTP-PROD-900012", "ZTP-PROD",
                           "Reparatur am Signal zw. Köln Hbf und Köln Messe/Deutz beendet",
                           "Reparatur am Signal zw. Köln Hbf und Köln Messe/Deutz beendet. Vereinzelt kann es noch "
                           "zu Verspätungen kommen.", now - timedelta(minutes=20),
                           [(now - timedelta(minutes=20), now + timedelta(hours=1))], RRX))
    return {"version": "11.0.6.72", "timestamp": _iso(now), "infos": {"current": infos, "affected": {}}}


def install(now, scenario):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "vrr.de" in url:
            if scenario == "down":
                raise requests.ConnectionError("simulierter Ausfall der VRR-Auskunft")
            return _Resp(answer(now, scenario))
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
