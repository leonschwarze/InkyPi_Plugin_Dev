"""CalDAV-Testserver (Radicale) unter dem Nextcloud-Pfad /remote.php/dav.

Startet im Hintergrund-Thread mit frischem, temporärem Speicher und legt
Testkalender mit Terminen relativ zu einem Stichtag an.

  from caldav_server import start
  url, user, password = start(date(2026, 11, 10))

Voraussetzung: pip install radicale
"""
import socket
import tempfile
import os
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

import requests

USER, PASSWORD = "leon", "test-app-passwort"

TZ = """BEGIN:VTIMEZONE
TZID:Europe/Berlin
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


MAILTO = "mailto:leon@example.org"  # eigene Adresse in den Testeinladungen


def with_mailto(app):
    """Radicale nennt unter calendar-user-address-set nur die Principal-Adresse. Nextcloud
    zusätzlich die E-Mail des Kontos – diese Hülle ergänzt sie wie Nextcloud."""
    def wrapped(environ, start_response):
        if environ.get("REQUEST_METHOD") != "PROPFIND":
            return app(environ, start_response)
        environ = dict(environ, HTTP_ACCEPT_ENCODING="identity")  # sonst kommt gzip, die Ersetzung fände nichts
        held = {}

        def keep(status, headers, exc_info=None):
            held["status"], held["headers"] = status, headers
        body = b"".join(app(environ, keep))
        tag = b"calendar-user-address-set>"
        if tag in body:
            body = body.replace(b":" + tag, b":" + tag + b"<href>" + MAILTO.encode() + b"</href>", 1)
        headers = [(k, str(len(body)) if k.lower() == "content-length" else v) for k, v in held["headers"]]
        start_response(held["status"], headers)
        return [body]
    return wrapped


def laufbuch(base, kind):
    """Laufbuch wie vom iPhone-Kurzbefehl (seit 1.38): eine Zeile je Lauf, „Datum;km;Minuten“.

    normal: diese Woche drei Läufe (17,5 km), die vier Wochen davor 12–15,5 km
    viel:   diese Woche 26 km
    leer:   diese Woche noch kein Lauf
    Die Woche ist die, in der base liegt (Mo–So); Läufe nur bis base.
    """
    monday = base - timedelta(days=base.weekday())
    weeks = {0: [(0, 5.2, 31), (2, 6.8, 41), (5, 5.5, 32)],
             1: [(1, 5.0, 30), (3, 4.5, 28), (6, 6.0, 37)],
             2: [(0, 4.8, 30), (4, 5.2, 31), (6, 5.0, 30)],
             3: [(2, 5.0, 31), (5, 5.0, 31)],
             4: [(1, 4.0, 26), (3, 4.5, 28), (6, 6.0, 38)]}
    if kind == "viel":
        weeks[0] = [(0, 6.2, 37), (1, 5.0, 30), (3, 8.3, 50), (5, 6.5, 39)]
    if kind == "leer":
        weeks[0] = []
    lines = ["# Laufbuch – vom Kurzbefehl „Lauf eintragen“ geschrieben"]
    for back in sorted(weeks, reverse=True):
        for day, km, mins in weeks[back]:
            d = monday - timedelta(days=7 * back) + timedelta(days=day)
            if d <= base:
                lines.append(f"{d.isoformat()};{str(km).replace('.', ',')};{mins}")
    return "\n".join(lines) + "\n"


def files_app(base):
    """WebDAV-Dateien der Nextcloud-Attrappe: nur GET auf das Laufbuch (DEV_LAUF, seit 1.38)."""
    from werkzeug.wrappers import Request, Response

    def app(environ, start_response):
        req = Request(environ)
        kind = os.environ.get("DEV_LAUF", "keine")
        auth = req.authorization
        if not auth or auth.username != USER or auth.password != PASSWORD:
            return Response("", 401)(environ, start_response)
        if kind == "down":
            return Response("", 503)(environ, start_response)
        if req.method != "GET" or kind in ("keine", "fehlt") or not req.path.endswith("/laufen.txt"):
            return Response("", 404)(environ, start_response)
        return Response(laufbuch(base, kind), 200, content_type="text/plain; charset=utf-8")(environ, start_response)
    return app


def start(base: date):
    import radicale
    from radicale import config as rconfig
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    from werkzeug.serving import make_server
    from werkzeug.wrappers import Response

    tmp = Path(tempfile.mkdtemp(prefix="caldav-"))
    (tmp / "users").write_text(f"{USER}:{PASSWORD}\n")
    conf = rconfig.load([])
    conf.update({
        "auth": {"type": "htpasswd", "htpasswd_filename": str(tmp / "users"), "htpasswd_encryption": "plain"},
        "storage": {"filesystem_folder": str(tmp / "data")},
        "rights": {"type": "owner_only"},
    }, "test", privileged=True)
    app = DispatcherMiddleware(Response("Nextcloud-Attrappe", 200),
                               {"/remote.php/dav": with_mailto(radicale.Application(conf)),
                                "/remote.php/dav/files": files_app(base)})
    import logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # keine Zeile pro Anfrage
    logging.getLogger("radicale").setLevel(logging.WARNING)  # keine Meldungen zum Speicherort
    port = _free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    seed(url + "/remote.php/dav/" + USER + "/", base)
    return url, USER, PASSWORD


def seed(home, base):
    s = requests.Session()
    s.auth = (USER, PASSWORD)

    def d(offset):
        return (base + timedelta(days=offset)).strftime("%Y%m%d")

    def mkcal(cid, name, color, comps=("VEVENT",)):
        comp = "".join(f'<C:comp name="{c}"/>' for c in comps)
        body = ('<?xml version="1.0"?><C:mkcalendar xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" '
                'xmlns:A="http://apple.com/ns/ical/"><D:set><D:prop>'
                f'<D:displayname>{name}</D:displayname><A:calendar-color>{color}FF</A:calendar-color>'
                f'<C:supported-calendar-component-set>{comp}</C:supported-calendar-component-set>'
                '</D:prop></D:set></C:mkcalendar>')
        s.request("MKCALENDAR", home + cid + "/", data=body).raise_for_status()

    def put(cid, body):
        uid = str(uuid.uuid4())
        ics = f"BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//dev//EN\n{TZ}\n{body}\nEND:VCALENDAR\n"
        ics = ics.replace("UID:X", f"UID:{uid}").replace("\n", "\r\n")
        s.put(home + f"{cid}/{uid}.ics", data=ics.encode(), headers={"Content-Type": "text/calendar"}).raise_for_status()

    def ev(summary, start, end, loc="", extra="", allday=False):
        if allday:
            times = f"DTSTART;VALUE=DATE:{start}\nDTEND;VALUE=DATE:{end}"
        else:
            times = f"DTSTART;TZID=Europe/Berlin:{start}\nDTEND;TZID=Europe/Berlin:{end}"
        loc = f"\nLOCATION:{loc}" if loc else ""
        return f"BEGIN:VEVENT\nUID:X\nDTSTAMP:20260101T000000Z\nSUMMARY:{summary}\n{times}{loc}{extra}\nEND:VEVENT"

    mkcal("personal", "Persönlich", "#0082C9")
    mkcal("arbeit", "Arbeit", "#E9322D")
    mkcal("familie", "Familie", "#2E9E3F")
    mkcal("aufgaben", "Aufgaben", "#999999", comps=("VTODO",))  # muss ignoriert werden

    put("personal", ev("Frühstück mit Anna", f"{d(0)}T080000", f"{d(0)}T090000", "Café Müller"))
    put("personal", ev("Zahnarzt Dr. Weber", f"{d(0)}T163000", f"{d(0)}T171500", "Poppelsdorfer Allee 12"))
    put("arbeit", ev("Ausschusssitzung", f"{d(0)}T180000", f"{d(0)}T203000", "Stadthaus"))
    put("familie", ev("Müllabfuhr: Papiertonne", d(1), d(2), allday=True))
    put("arbeit", ev("Jour fixe Team", f"{d(1)}T100000", f"{d(1)}T110000", "Videokonferenz"))
    put("familie", ev("Laternenumzug Kita", f"{d(1)}T170000", f"{d(1)}T183000", "Kita Sonnenschein"))
    # Wöchentliche Serie ab Tag -20; Ausnahme: Termin in Woche +1 verschoben, Woche +2 fällt aus
    first = base + timedelta(days=1 - 21)
    moved, cancelled = base + timedelta(days=8), base + timedelta(days=15)
    put("personal", ev("Lauftreff Rheinaue", f"{first:%Y%m%d}T183000", f"{first:%Y%m%d}T200000", "Post Tower",
                       extra=f"\nRRULE:FREQ=WEEKLY\nEXDATE;TZID=Europe/Berlin:{cancelled:%Y%m%d}T183000") + "\n"
        + "BEGIN:VEVENT\nUID:X\nDTSTAMP:20260101T000000Z\n"
        + f"RECURRENCE-ID;TZID=Europe/Berlin:{moved:%Y%m%d}T183000\nSUMMARY:Lauftreff Rheinaue (verschoben)\n"
        + f"DTSTART;TZID=Europe/Berlin:{moved + timedelta(days=1):%Y%m%d}T190000\n"
        + f"DTEND;TZID=Europe/Berlin:{moved + timedelta(days=1):%Y%m%d}T203000\nEND:VEVENT")
    put("arbeit", ev("Haushaltsklausur mit ausführlicher Beratung aller Einzelpläne und Investitionsprogramme",
                     f"{d(2)}T090000", f"{d(2)}T170000", "Gustav-Stresemann-Institut"))
    put("personal", ev("Nachtzug nach Wien", f"{d(2)}T221500", f"{d(3)}T073000", "Köln Hbf"))
    put("familie", ev("Wochenende in Wien", d(3), d(6), allday=True))
    put("arbeit", ev("Abgesagt: Planungsrunde", f"{d(1)}T140000", f"{d(1)}T150000", extra="\nSTATUS:CANCELLED"))
    put("arbeit", ev("Bürgersprechstunde", f"{d(6)}T160000", f"{d(6)}T180000", "Bürgerbüro"))
    put("personal", ev("Konzert Beethovenhalle", f"{d(7)}T200000", f"{d(7)}T223000", "Beethovenhalle"))
    bday = base + timedelta(days=4)
    bday = date(bday.year - 80, bday.month, min(bday.day, 28))  # jährliche Serie, vor 80 Jahren begonnen
    put("familie", ev("Oma Geburtstag", f"{bday:%Y%m%d}", f"{bday + timedelta(days=1):%Y%m%d}",
                      allday=True, extra="\nRRULE:FREQ=YEARLY"))
    put("aufgaben", "BEGIN:VTODO\nUID:X\nDTSTAMP:20260101T000000Z\nSUMMARY:Steuer\nEND:VTODO")
    import os
    proto = os.environ.get("DEV_PROTO", "")
    # Einladungen, die Leon abgelehnt hat (eigener ATTENDEE mit PARTSTAT=DECLINED): müssen fehlen,
    # deshalb immer dabei – jedes Bild bleibt so pixelgleich zu dem ohne diese Termine.
    org = "\nORGANIZER;CN=Lisa:mailto:lisa@example.org"
    put("arbeit", ev("Abgelehnt: Kreisvorstand", f"{d(0)}T190000", f"{d(0)}T210000", "Parteibüro",
                     extra=org + f"\nATTENDEE;CN=Leon;PARTSTAT=DECLINED:{MAILTO}"
                     + "\nATTENDEE;CN=Lisa;PARTSTAT=ACCEPTED:mailto:lisa@example.org"))
    put("personal", ev("Abgelehnt: Sommerfest", d(1), d(2), allday=True,  # Groß-/Kleinschreibung egal
                       extra=org + "\nATTENDEE;PARTSTAT=DECLINED:MAILTO:Leon@Example.ORG"))
    if "einladung" in proto:
        # Gegenproben (DEV_PROTO=einladung): Diese Termine müssen erscheinen …
        put("arbeit", ev("Einladung zugesagt: Fraktion", f"{d(0)}T113000", f"{d(0)}T123000", "Rathaus",
                         extra=org + f"\nATTENDEE;PARTSTAT=ACCEPTED:{MAILTO}"
                         + "\nATTENDEE;PARTSTAT=DECLINED:mailto:anna@example.org"))   # nur Anna sagt ab
        put("arbeit", ev("Einladung offen: Stammtisch", f"{d(1)}T193000", f"{d(1)}T210000", "Brauhaus",
                         extra=org + f"\nATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:{MAILTO}"))
        # … und von dieser täglichen Serie fehlt nur der Termin morgen (einzeln abgelehnt)
        first = base + timedelta(days=-1)
        skip = base + timedelta(days=1)
        put("arbeit", ev("Serie: Morgenlage", f"{first:%Y%m%d}T083000", f"{first:%Y%m%d}T090000",
                         extra="\nRRULE:FREQ=DAILY;COUNT=5" + org + f"\nATTENDEE;PARTSTAT=ACCEPTED:{MAILTO}") + "\n"
            + "BEGIN:VEVENT\nUID:X\nDTSTAMP:20260101T000000Z\n"
            + f"RECURRENCE-ID;TZID=Europe/Berlin:{skip:%Y%m%d}T083000\nSUMMARY:Serie: Morgenlage\n"
            + f"DTSTART;TZID=Europe/Berlin:{skip:%Y%m%d}T083000\nDTEND;TZID=Europe/Berlin:{skip:%Y%m%d}T090000\n"
            + org[1:] + f"\nATTENDEE;PARTSTAT=DECLINED:{MAILTO}\nEND:VEVENT")
    # Urlaub und Wahlkampftermine (Umgebungsvariable DEV_PROTO=urlaub,wahl, damit die übrigen Bilder gleich bleiben)
    import os
    proto = os.environ.get("DEV_PROTO", "")
    if "last" in proto:  # Wochenlast (seit 1.38): acht vergangene Wochen mit üblichen Sitzungen
        monday = base - timedelta(days=base.weekday())
        for back in range(1, 9):
            m = monday - timedelta(days=7 * back)
            def at(day, hh, mm=0):
                return (m + timedelta(days=day)).strftime("%Y%m%d") + f"T{hh:02d}{mm:02d}00"
            put("arbeit", ev("Fraktionssitzung", at(0, 17), at(0, 20), "Stadthaus"))
            put("arbeit", ev("Jour fixe Team", at(1, 10), at(1, 11), "Videokonferenz"))
            put("arbeit", ev("Landtag Büro", at(2, 9), at(2, 13 + back % 3), "Düsseldorf"))
            if back % 2:
                put("arbeit", ev("Schulausschuss", at(3, 17), at(3, 20), "Stadthaus"))
            if back in (2, 5):
                put("arbeit", ev("Infostand", at(5, 10), at(5, 13), "Bonner Markt"))
        # kommende Woche (ab Montag nach base) bewusst voll: 19 h statt etwa 12 h
        nxt = monday + timedelta(days=7)
        def at2(day, hh, mm=0):
            return (nxt + timedelta(days=day)).strftime("%Y%m%d") + f"T{hh:02d}{mm:02d}00"
        put("arbeit", ev("Fraktionssitzung", at2(0, 17), at2(0, 20), "Stadthaus"))
        put("arbeit", ev("Finanzausschuss", at2(2, 16), at2(2, 19, 30), "Stadthaus"))
    if "monat" in proto:  # Monatsbild (seit 1.38): ein typischer Monat ab base
        first = base.replace(day=1)
        def at3(day, hh, mm=0):
            return (first + timedelta(days=day - 1)).strftime("%Y%m%d") + f"T{hh:02d}{mm:02d}00"
        def day3(day):
            return (first + timedelta(days=day - 1)).strftime("%Y%m%d")
        nxt_month = (first + timedelta(days=32)).replace(day=1)
        for d0 in range(1, (nxt_month - first).days + 1):
            wd = (first + timedelta(days=d0 - 1)).weekday()
            if wd == 0 and d0 < 22:
                put("arbeit", ev("Fraktionssitzung", at3(d0, 17), at3(d0, 20), "Stadthaus"))
            if wd == 1 and d0 < 22:
                put("arbeit", ev("Jour fixe Team", at3(d0, 10), at3(d0, 11), "Videokonferenz"))
            if wd == 2 and d0 < 20:
                put("arbeit", ev("Landtag Büro", at3(d0, 9), at3(d0, 15), "Düsseldorf"))
        put("arbeit", ev("Schulausschuss", at3(3, 17), at3(3, 20), "Stadthaus"))
        put("arbeit", ev("Ratssitzung", at3(10, 17), at3(10, 22), "Stadthaus, Ratssaal"))
        put("arbeit", ev("Finanzausschuss", at3(15, 16), at3(15, 19), "Stadthaus"))
        put("arbeit", ev("Weihnachtsfeier SPD Bonn", at3(12, 18), at3(12, 23), "Parteibüro"))
        put("personal", ev("Weihnachtsmarkt mit Anna", at3(5, 16), at3(5, 19), "Münsterplatz"))
        put("personal", ev("Friseur", at3(18, 9), at3(18, 10)))
        put("familie", ev("Weihnachten bei den Eltern", day3(23), day3(28), allday=True))
        put("personal", ev("Silvester bei Lisa", at3(31, 20), at3(31, 23, 59), "Beuel"))
        put("familie", ev("Müllabfuhr: Gelbe Tonne", day3(17), day3(18), allday=True))
    if "urlaub" in proto:
        put("familie", ev("Urlaub in Lyon", d(-2), d(6), allday=True))
    if "rat" in proto:  # rat-abgelehnt: dieselbe Sitzung als von Leon abgelehnte Einladung → keine Karte (seit 1.26)
        declined = f"{org}\nATTENDEE;PARTSTAT=DECLINED:{MAILTO}" if "rat-abgelehnt" in proto else ""
        put("arbeit", ev("Ratssitzung", f"{d(0)}T170000", f"{d(0)}T220000", "Stadthaus, Ratssaal", extra=declined))
    if "ziel" in proto:  # Wetter am Zielort (seit 1.30): heute Landtag Düsseldorf, morgen Eschweiler
        put("arbeit", ev("Ausschuss Heimat und Kommunales", f"{d(0)}T130000", f"{d(0)}T163000",
                         r"Landtag NRW\, Platz des Landtags 1\, 40221 Düsseldorf"))
        put("arbeit", ev("Bürgersprechstunde", f"{d(1)}T190000", f"{d(1)}T210000", r"Rathaus\, Eschweiler"))
    if "wahl" in proto:
        put("arbeit", ev("Haustürwahlkampf Beuel", f"{d(0)}T150000", f"{d(0)}T180000", "Beuel-Mitte, Treffpunkt Rathaus"))
        put("arbeit", ev("Infostand Marktplatz", f"{d(1)}T100000", f"{d(1)}T130000", "Bonner Markt"))
