"""CalDAV-Testserver (Radicale) unter dem Nextcloud-Pfad /remote.php/dav.

Startet im Hintergrund-Thread mit frischem, temporärem Speicher und legt
Testkalender mit Terminen relativ zu einem Stichtag an.

  from caldav_server import start
  url, user, password = start(date(2026, 11, 10))

Voraussetzung: pip install radicale
"""
import socket
import tempfile
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
    app = DispatcherMiddleware(Response("Nextcloud-Attrappe", 200), {"/remote.php/dav": radicale.Application(conf)})
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
    # Urlaub und Wahlkampftermine (Umgebungsvariable DEV_PROTO=urlaub,wahl, damit die übrigen Bilder gleich bleiben)
    import os
    proto = os.environ.get("DEV_PROTO", "")
    if "urlaub" in proto:
        put("familie", ev("Urlaub in Lyon", d(-2), d(6), allday=True))
    if "rat" in proto:
        put("arbeit", ev("Ratssitzung", f"{d(0)}T170000", f"{d(0)}T220000", "Stadthaus, Ratssaal"))
    if "wahl" in proto:
        put("arbeit", ev("Haustürwahlkampf Beuel", f"{d(0)}T150000", f"{d(0)}T180000", "Beuel-Mitte, Treffpunkt Rathaus"))
        put("arbeit", ev("Infostand Marktplatz", f"{d(1)}T100000", f"{d(1)}T130000", "Bonner Markt"))
