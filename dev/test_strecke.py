"""Streckenmeldungen der VRR-Auskunft (tagesdashboard/strecke.py) ohne Rendern.

  python dev/test_strecke.py

Prüft: echte Antwort vom 13.11.2026 (Auszug in dev/vrr_addinfo_2026-11-13.json) – nur die Baustelle
Düsseldorf–Köln-Mülheim darf durchkommen; Ortsregeln (vor dem Einstieg, über die Stadt, hinter dem
Ausstieg, gleichnamige Linien anderswo); Zeiten (abgelaufen, erst nach der Ankunft, „beendet“ nur eine
Stunde); Texte; Zwischenspeicher und Ausfall; Reihenfolge zusammen mit den Meldungen am Zug (bahn.py)
und der ganze Weg über bahn.load mit den Mocks.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import requests  # noqa: E402

import bahn  # noqa: E402
import strecke  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
fails = 0

BEFORE = ["Koblenz Hbf", "Andernach", "Remagen", "Bonn-Bad Godesberg", "Bonn UN Campus"]
AFTER = ["Brühl", "Köln Süd", "Köln Hbf", "Köln Messe/Deutz", "Düsseldorf Hbf", "Düsseldorf Flughafen",
         "Duisburg Hbf", "Oberhausen Hbf", "Wesel"]
ROUTE, TI = strecke.route_of({"before": BEFORE, "path": AFTER}, "Bonn Hbf", "Düsseldorf Hbf")


def plain(x):
    """Geschützte Leerzeichen (strecke.NB) für den Vergleich wie normale behandeln."""
    if isinstance(x, str):
        return x.replace("\u00a0", " ")
    if isinstance(x, (list, tuple)):
        return type(x)(plain(i) for i in x)
    return x


def check(name, got, want):
    global fails
    got = plain(got)
    ok = got == want
    fails += not ok
    print(("ok   " if ok else "FEHLER ") + name + ("" if ok else f": {got!r} statt {want!r}"))


def msg(title, text="", created=None, validity=None, lines=("RE5",), provider="ZTP-PROD"):
    return {"id": title[:20], "provider": provider, "title": title, "text": text, "created": created,
            "validity": validity or [], "lines": list(lines)}


# ---------------------------------------------------------------- echte Antwort
real = json.load(open(ROOT / "dev" / "vrr_addinfo_2026-11-13.json"))
msgs = strecke.select(real, "RE5")
check("echte Daten: Bahn-eigene Meldungen (DBProd) fallen weg", sorted(m["id"] for m in msgs),
      ["ZTP-PROD-137395", "ZTP-PROD-139703"])
for when in ("2026-11-13 10:31", "2026-11-17 07:30"):
    now = datetime.fromisoformat(when).replace(tzinfo=TZ)
    got = strecke.alerts(msgs, ROUTE, TI, now, now.replace(hour=9, minute=0) if now.hour < 9 else now, TZ)
    check(f"echte Daten {when}: nur die Baustelle auf dem Abschnitt", [a["text"] for a in got],
          ["Baustelle Düsseldorf–Köln-Mülheim: Umleitungen und Teilausfälle bis 4.12."])
check("echte Daten: andere Linie (RE 1 gleiche Baustelle) gehört nicht zur RE 5",
      [m["id"] for m in strecke.select(real, "RE1")], ["ZTP-PROD-137391"])

# ---------------------------------------------------------------- Orte
cases = [
    ("Strecke zw. Remagen und Bonn-Bad Godesberg gesperrt - Notarzteinsatz", True, "vor dem Einstieg"),
    ("Strecke zw. Köln-Mülheim und Leverkusen Mitte beeinträchtigt - Signal", True, "über die Stadt Köln"),
    ("Region Düsseldorf Hbf beeinträchtigt - Weichenstörung", True, "nur der Ausstieg"),
    ("Strecke zw. Düsseldorf-Benrath und Düsseldorf Hbf beeinträchtigt", True, "kurz vor dem Ausstieg"),
    ("Strecke zw. Düsseldorf Hbf und Duisburg Hbf beeinträchtigt", False, "ab dem Ausstieg nach Norden"),
    ("Strecke zw. Düsseldorf Flughafen und Duisburg-Rahm beeinträchtigt", False, "hinter dem Ausstieg"),
    ("Strecke zw. Düsseldorf-Derendorf und Düsseldorf Flughafen beeinträchtigt", False,
     "hinter dem Ausstieg, gleiche Stadt"),
    ("Großbaustelle Oberhausen Hbf - Emmerich", False, "Titel entscheidet (Text nennt nichts anderes)"),
    ("Störung.", False, "RE 5 in Hessen (kein Ort der Strecke)"),
]
for title, want, why in cases:
    check(f"Ort: {why}", strecke.on_route(msg(title), ROUTE, TI), want)
check("Ort: ohne Ort im Titel entscheidet der Text",
      strecke.on_route(msg("Maßnahmen und Fahrpläne: RE 5 (RRX)", "… zu Teilausfällen zwischen Köln Hbf und "
                           "Köln Messe/Deutz."), ROUTE, TI), True)
check("Ort: Text in Hessen", strecke.on_route(msg("Störung.", "Busse beginnen in Schlüchtern."), ROUTE, TI), False)
check("Ort: Bonn ist nicht Bonn-Beuel… aber dieselbe Stadt", strecke.on_route(msg("Region Bonn-Beuel beeinträchtigt"),
                                                                        ROUTE, TI), True)
check("Laufweg ohne Ausstieg -> keine Streckenmeldungen",
      strecke.route_of({"before": BEFORE, "path": AFTER}, "Bonn Hbf", "Essen Hbf"), None)

# ---------------------------------------------------------------- Zeit
now = datetime(2026, 11, 17, 7, 12, tzinfo=TZ)
arr = datetime(2026, 11, 17, 8, 58, tzinfo=TZ)
signal = "Strecke zw. Köln Hbf und Köln Messe/Deutz beeinträchtigt - Reparatur an einem Signal"
check("Zeit: abgelaufen", strecke.alerts([msg(signal, validity=[(now - timedelta(hours=3), now - timedelta(minutes=1))])],
                                         ROUTE, TI, now, arr, TZ), [])
check("Zeit: beginnt erst nach der Ankunft",
      strecke.alerts([msg(signal, validity=[(arr + timedelta(minutes=5), arr + timedelta(hours=2))])],
                     ROUTE, TI, now, arr, TZ), [])
got = strecke.alerts([msg(signal, created=now - timedelta(minutes=20),
                          validity=[(now - timedelta(minutes=32), now + timedelta(hours=3))])], ROUTE, TI, now, arr, TZ)
check("Text: akute Störung mit Beginn", [a["text"] for a in got],
      ["Strecke Köln–Köln Messe/Deutz: Reparatur an einem Signal · seit 6:40"])
check("Stufe: Vorwarnung ist immer gelb", [a["level"] for a in got], ["info"])
done = "Reparatur am Signal zw. Köln Hbf und Köln Messe/Deutz beendet"
check("beendet: 20 min alt wird gezeigt", [a["text"] for a in strecke.alerts(
    [msg(done, created=now - timedelta(minutes=20), validity=[(now - timedelta(minutes=20), arr)])],
    ROUTE, TI, now, arr, TZ)], ["Behoben: Signal Köln–Köln Messe/Deutz · Verspätungen möglich"])
check("beendet: nach einer Stunde weg", strecke.alerts(
    [msg(done, created=now - timedelta(minutes=70), validity=[(now - timedelta(minutes=70), arr)])],
    ROUTE, TI, now, arr, TZ), [])
check("Vorankündigung erscheint nicht", strecke.alerts(
    [msg("Vorankündigung Großbaustelle Köln Hbf", validity=[(now - timedelta(days=3), arr)])],
    ROUTE, TI, now, arr, TZ), [])
check("Text: gesperrt", strecke.describe(msg("Strecke zw. Remagen und Bonn-Bad Godesberg gesperrt - Notarzteinsatz am Gleis",
                                             created=now - timedelta(minutes=25)), now, TZ, None)[0],
      "Strecke Remagen–Bonn-Bad Godesberg gesperrt: Notarzteinsatz am Gleis · seit 6:47")
check("Text: nicht befahrbar zählt als gesperrt",
      strecke.describe(msg("Strecke zw. Essen-Steele und Wuppertal-Vohwinkel nicht befahrbar - Unregelmäßigkeiten "
                           "bei Bauarbeiten"), now, TZ, None)[1], "acute")
check("Text: Aufzählung mit bzw.", strecke.describe(msg("Teilausfälle", "kommt es zu Teilausfällen zwischen Paderborn Hbf "
                                                         "und Höxter-Ottbergen bzw. Holzminden."), now, TZ, None)[0],
      "Baustelle Paderborn–Höxter-Ottbergen: Teilausfälle")

# ---------------------------------------------------------------- Abruf und Zwischenspeicher
class Resp:
    def __init__(self, data, status=200):
        self.status_code, self._data = status, data
        self.content = json.dumps(data).encode()

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def get(self, url, params=None, timeout=None, **kw):
        self.calls += 1
        if self.fail:
            raise requests.ConnectionError("aus")
        return Resp(real)


strecke._cache.clear()
s = FakeSession()
strecke.fetch(s, "RE5")
strecke.fetch(s, "RE5")
check("Zwischenspeicher: zweiter Abruf aus dem Speicher", s.calls, 1)
strecke._cache.clear()
s = FakeSession(fail=True)
check("Ausfall: None statt Fehler", strecke.fetch(s, "RE5"), None)
strecke.fetch(s, "RE5")
check("Ausfall: wird auch zwischengespeichert (keine 20 s Wartezeit je Runde)", s.calls, 1)
strecke._cache.clear()

# ---------------------------------------------------------------- Reihenfolge mit den Meldungen am Zug
train = [{"text": "Defekt an einem Signal", "level": "high", "kind": "reason"},
         {"text": "Ein Wagen fehlt", "level": "info", "kind": "quality"},
         {"text": "Zwischen Köln und Leverkusen …", "level": "info", "kind": "notice"}]
route = [{"text": "Baustelle …", "level": "info", "kind": "build"},
         {"text": "Strecke …", "level": "info", "kind": "acute"}]
check("Reihenfolge: rot, Freitext am Zug, Strecke akut, Kleinkram, Baustelle",
      [a["text"] for a in bahn.merge(train, route)],
      ["Defekt an einem Signal", "Zwischen Köln und Leverkusen …", "Strecke …", "Ein Wagen fehlt", "Baustelle …"])

# ---------------------------------------------------------------- ganzer Weg über bahn.load (Mocks)
import mock_bahn  # noqa: E402
import mock_vrr  # noqa: E402

orig = requests.Session.get
now = datetime(2026, 11, 10, 7, 12, tzinfo=TZ)
base = {"trainEnabled": "true", "trainStation": "Bonn Hbf", "trainLine": "RE 5", "trainTime": "08:04",
        "trainFrom": "06:30", "trainTo": "08:15", "trainDi": "true", "trainTarget": "Düsseldorf Hbf",
        "trainAlerts": "true", "trainRoute": "true"}


def run(scenario, settings=base, train="ok"):
    requests.Session.get = orig
    strecke._cache.clear()
    bahn._target_cache.clear()
    mock_bahn.install(now, train)
    mock_vrr.install(now, scenario)
    cfg = bahn.read_config(lambda k: settings.get(k, ""), lambda k: settings.get(k) == "true")
    return [(a["source"], a["text"]) for a in bahn.load(cfg, now, TZ)["alerts"]]


check("load ruhig: nichts von der Strecke", run("ruhig"), [])
check("load stoerung", run("stoerung"),
      [("route", "Strecke Köln-Mülheim–Leverkusen Mitte: Reparatur an einem Signal · seit 6:40")])
check("load beides: akut vor Baustelle", [t for _, t in run("beides")],
      ["Strecke Köln-Mülheim–Leverkusen Mitte: Reparatur an einem Signal · seit 6:40",
       "Baustelle Düsseldorf–Köln-Mülheim: Umleitungen und Teilausfälle bis 4.12."])
check("load down: Zug wie bisher", run("down"), [])
check("load Strecke aus", run("stoerung", {**base, "trainRoute": "false"}), [])
check("load Störungsmonitor aus: auch keine Strecke", run("stoerung", {**base, "trainAlerts": "false"}), [])
check("load ohne Ausstieg: keine Strecke", run("stoerung", {**base, "trainTarget": ""}), [])
requests.Session.get = orig

print("\nalles ok" if not fails else f"\n{fails} Fehler")
sys.exit(1 if fails else 0)
