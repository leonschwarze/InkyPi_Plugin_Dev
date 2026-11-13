"""
Simulierte Antworten der Timetables-API der Bahn (IRIS) für Bonn Hbf.

Szenarien (render.py --train ...):
  ok       pünktlich
  leicht   +3 Minuten
  spaet    +7 Minuten
  ausfall  fällt aus
  gleis    Gleiswechsel 1 -> 3, +2 Minuten
  kurz     endet vorzeitig in Köln Hbf, +12 Minuten (Düsseldorf entfällt)
  stoerung +9, Signalstörung (Freitext) und Grund, in Düsseldorf +13 mit Gleishinweis
  sev      Streckensperrung hinter Köln, Ersatzverkehr, Düsseldorf entfällt (drei Meldungen)
  ohnelive Sollfahrplan da, Änderungen nicht abrufbar
  down     Bahn-API gar nicht erreichbar

Im Sollfahrplan stehen um 8:04 bewusst zwei Züge (RE 5 und RB 48), damit die Suche
nach Linie geprüft wird, und der RE 5 der Gegenrichtung um 8:57. In Düsseldorf Hbf kommt
derselbe Zug um 8:58 an (gleiche Fahrt-ID); um 8:58 steht dort auch ein RE 5 der Gegenrichtung.
Meldungen: ein alter Verspätungsgrund hängt immer am Zug (darf nur bei Verspätung erscheinen),
dazu eine abgelaufene und eine inhaltsleere Meldung, die nie erscheinen dürfen.
"""

import requests

SCENARIOS = ["ok", "leicht", "spaet", "ausfall", "gleis", "kurz", "stoerung", "sev", "ohnelive", "down"]

NORD = "Brühl|Köln Süd|Köln Hbf|Köln Messe/Deutz|Düsseldorf Hbf|Düsseldorf Flughafen|Duisburg Hbf|Oberhausen Hbf|Wesel"


class _Resp:
    def __init__(self, text, status=200):
        self.content = text.encode("utf-8")
        self.text = text
        self.status_code = status


def _plan(day):
    d = day.strftime("%y%m%d")
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<timetable station='Bonn Hbf'>
<s id="-5551-{d}0804-6"><tl f="N" t="p" o="X1" c="RE" n="10418"/>
 <ar pt="{d}0802" pp="1" l="5" ppth="Koblenz Hbf|Andernach|Remagen|Bonn-Bad Godesberg|Bonn UN Campus"/>
 <dp pt="{d}0804" pp="1" l="5" ppth="{NORD}"/></s>
<s id="-7771-{d}0804-9"><tl f="N" t="p" o="800337" c="RB" n="11433"/>
 <dp pt="{d}0804" pp="2" l="48" ppth="Roisdorf|Brühl|Köln Hbf|Solingen Hbf|Wuppertal-Oberbarmen"/></s>
<s id="-8881-{d}0857-6"><tl f="N" t="p" o="X1" c="RE" n="10421"/>
 <dp pt="{d}0857" pp="3" l="5" ppth="Bonn UN Campus|Bonn-Bad Godesberg|Remagen|Andernach|Koblenz Hbf"/></s>
</timetable>"""


def _changes(day, scenario):
    d = day.strftime("%y%m%d")
    dp = {
        "ok": "",
        "leicht": f'ct="{d}0807"',
        "spaet": f'ct="{d}0811"',
        "ausfall": f'cs="c" clt="{d}0640"',
        "gleis": f'ct="{d}0806" cp="3"',
        "kurz": f'ct="{d}0816" cpth="Brühl|Köln Süd|Köln Hbf"',
        "stoerung": f'ct="{d}0813"',
        "sev": f'cpth="Brühl|Köln Süd|Köln Hbf"',
    }.get(scenario, "")
    extra = {
        "stoerung": f'''<m id="r10" t="d" c="34" ts="{d}0750"/>
  <m id="r11" t="h" pr="2" cat="Störung" from="{d}0700" to="{d}1200" ts="{d}0745"
     ext="Zwischen Köln Hbf und Leverkusen Mitte kommt es wegen einer Signalstörung zu Verspätungen und einzelnen Teilausfällen. Bitte planen Sie mehr Zeit ein."/>''',
        "sev": f'''<m id="r20" t="h" pr="1" cat="Störung" from="{d}0600" to="{d}1400" ts="{d}0710"
     ext="Nach einem Notarzteinsatz ist die Strecke zwischen Köln Hbf und Düsseldorf Hbf gesperrt. Der RE 5 endet in Köln Hbf."/>
  <m id="r21" t="f" c="78" ts="{d}0712"/>
  <m id="r22" t="d" c="8" ts="{d}0705"/>''',
    }.get(scenario, "")
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<timetable station='Bonn Hbf' eva='8000044'>
<s id="-7771-{d}0804-9" eva="8000044"><dp ct="{d}0809"/></s>
<s id="-5551-{d}0804-6" eva="8000044">
  <m id="r2" t="h" pr="3" cat="Information" ts="{d}0500"/>
  <m id="r3" t="h" pr="2" cat="Bauarbeiten" from="{d}0000" to="{d}0600" ext="Nächtliche Bauarbeiten zwischen Bonn und Köln (abgelaufen)"/>
  <dp {dp}><m id="r1" t="d" c="43" ts="{d}0630"/>{extra}</dp></s>
</timetable>"""


def _plan_dus(day, hour):
    d = day.strftime("%y%m%d")
    if hour != "08":
        return "<timetable station='Düsseldorf Hbf'/>"
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<timetable station='Düsseldorf Hbf'>
<s id="-9991-{d}0745-3"><tl f="N" t="p" o="X1" c="RE" n="10417"/>
 <ar pt="{d}0858" pp="15" l="5" ppth="Wesel|Duisburg Hbf|Düsseldorf Flughafen"/>
 <dp pt="{d}0900" pp="15" l="5" ppth="Köln Messe/Deutz|Köln Hbf|Bonn Hbf|Koblenz Hbf"/></s>
<s id="-5551-{d}0804-14"><tl f="N" t="p" o="X1" c="RE" n="10418"/>
 <ar pt="{d}0858" pp="16" l="5" ppth="Bonn Hbf|Brühl|Köln Süd|Köln Hbf|Köln Messe/Deutz"/>
 <dp pt="{d}0900" pp="16" l="5" ppth="Duisburg Hbf|Oberhausen Hbf|Wesel"/></s>
</timetable>"""


def _changes_dus(day, scenario):
    d = day.strftime("%y%m%d")
    ar = {
        "leicht": f'ct="{d}0901"', "spaet": f'ct="{d}0906"', "ausfall": 'cs="c"',
        "gleis": f'ct="{d}0900"', "kurz": 'cs="c"', "sev": 'cs="c"',
        "stoerung": f'ct="{d}0911" cp="18"',
    }.get(scenario, "")
    extra = ""
    if scenario == "stoerung":
        extra = f'''<m id="r30" t="h" pr="3" cat="Bauarbeiten" from="{d}0500" to="{d}2300" ts="{d}0400"
     ext="Wegen Bauarbeiten ist Gleis 16 in Düsseldorf Hbf gesperrt. Ankunft heute an Gleis 18."/>'''
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<timetable station='Düsseldorf Hbf' eva='8000085'>
<s id="-9991-{d}0745-3" eva="8000085"><ar ct="{d}0904"/></s>
<s id="-5551-{d}0804-14" eva="8000085"><ar {ar}>{extra}<m id="r1" t="d" c="43" ts="{d}0630"/></ar></s>
</timetable>"""


def install(now, scenario):
    previous = requests.Session.get

    def fake_get(session, url, params=None, timeout=None, **kw):
        if "iris.noncd.db.de" in url or "apis.deutschebahn.com" in url:
            if scenario == "down" or (scenario == "ohnelive" and "/fchg/" in url):
                raise requests.ConnectionError("simulierter Ausfall der Bahn-API")
            dus = "/8000085" in url
            if "/plan/" in url:
                return _Resp(_plan_dus(now.date(), url.rstrip("/").rsplit("/", 1)[1]) if dus else _plan(now.date()))
            if "/fchg/" in url:
                return _Resp(_changes_dus(now.date(), scenario) if dus else _changes(now.date(), scenario))
            if "/station/" in url:
                return _Resp("<stations><station name='Bonn Hbf' eva='8000044' ds100='KB'/></stations>")
            return _Resp("", 404)
        return previous(session, url, params=params, timeout=timeout, **kw)

    requests.Session.get = fake_get
