"""Abgelehnte Einladungen (nextcloud_kalender.declined_by) ohne Rendern.

  python dev/test_abgelehnt.py

Prüft: Adressen vergleichen (mailto: in beliebiger Schreibweise, Principal-Adressen relativ/absolut);
nur die eigene Absage zählt (Absagen anderer Gäste nicht); zugesagt, vorläufig, offen und ohne
PARTSTAT bleiben; mit zwei eigenen Adressen fällt der Termin nur weg, wenn beide abgelehnt haben;
ohne bekannte eigene Adresse fällt nichts weg; in einer Serie fehlt nur der einzeln abgelehnte
Termin; abgesagte Termine (STATUS:CANCELLED) fehlen weiter. Dazu der echte Weg über CalDAV gegen
den Testserver (dev/caldav_server.py): Adressen aus calendar-user-address-set, Zählung
declined_hidden – und eine Nextcloud-Antwort, wie sie der echte Server liefert.
"""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi"))
sys.path.insert(0, str(INKYPI / "src"))
sys.path.insert(0, str(ROOT / "dev"))
sys.path.insert(0, str(ROOT))

import icalendar  # noqa: E402

from nextcloud_kalender import nextcloud_kalender as nk  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
fails = 0


def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FEHLER {name}: {got!r} statt {want!r}")
    else:
        print(f"ok     {name}")


ME = {"mailto:leon@example.org"}


def event(*attendees, status=""):
    lines = ["BEGIN:VEVENT", "UID:t", "DTSTAMP:20260101T000000Z", "SUMMARY:Test",
             "DTSTART;TZID=Europe/Berlin:20261110T100000", "DTEND;TZID=Europe/Berlin:20261110T110000",
             "ORGANIZER:mailto:lisa@example.org"]
    lines += [f"ATTENDEE{a}" for a in attendees]
    if status:
        lines.append(f"STATUS:{status}")
    lines.append("END:VEVENT")
    cal = icalendar.Calendar.from_ical("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "\r\n".join(lines) + "\r\nEND:VCALENDAR\r\n")
    return cal.walk("VEVENT")[0]


# --- Adressen -------------------------------------------------------------
check("mailto klein", nk.address_key("MAILTO:Leon@Example.ORG"), "mailto:leon@example.org")
check("mailto mit Leerzeichen", nk.address_key("  mailto:leon@example.org "), "mailto:leon@example.org")
check("mailto kodiert", nk.address_key("mailto:leon%40example.org"), "mailto:leon@example.org")
check("Principal relativ → absolut", nk.address_key("/remote.php/dav/principals/users/leon/", "https://cloud.example.de/remote.php/dav/"),
      "https://cloud.example.de/remote.php/dav/principals/users/leon")
check("Principal ohne Basis", nk.address_key("https://Cloud.example.de/x/"), "https://cloud.example.de/x")

# --- Wer hat abgelehnt? ---------------------------------------------------
check("selbst abgelehnt", nk.declined_by(event(";PARTSTAT=DECLINED:mailto:leon@example.org"), ME), True)
check("selbst abgelehnt, Großschreibung", nk.declined_by(event(";PARTSTAT=declined:MAILTO:LEON@example.org"), ME), True)
check("nur ein anderer Gast abgelehnt", nk.declined_by(event(
    ";PARTSTAT=ACCEPTED:mailto:leon@example.org", ";PARTSTAT=DECLINED:mailto:anna@example.org"), ME), False)
check("anderer Gast abgelehnt, ich nicht eingeladen", nk.declined_by(event(";PARTSTAT=DECLINED:mailto:anna@example.org"), ME), False)
for ps in ("ACCEPTED", "TENTATIVE", "NEEDS-ACTION", "DELEGATED"):
    check(f"selbst {ps}", nk.declined_by(event(f";PARTSTAT={ps}:mailto:leon@example.org"), ME), False)
check("ohne PARTSTAT", nk.declined_by(event(":mailto:leon@example.org"), ME), False)
check("ohne Gäste (eigener Termin)", nk.declined_by(event(), ME), False)
two = ME | {"mailto:leon@spd-bonn.example"}
check("zwei eigene Adressen, beide abgelehnt", nk.declined_by(event(
    ";PARTSTAT=DECLINED:mailto:leon@example.org", ";PARTSTAT=DECLINED:mailto:leon@spd-bonn.example"), two), True)
check("zwei eigene Adressen, eine zugesagt", nk.declined_by(event(
    ";PARTSTAT=DECLINED:mailto:leon@example.org", ";PARTSTAT=ACCEPTED:mailto:leon@spd-bonn.example"), two), False)
check("keine eigene Adresse bekannt", nk.declined_by(event(";PARTSTAT=DECLINED:mailto:leon@example.org"), set()), False)

# --- parse_events: Serie, Absage, Zählung ---------------------------------
SERIES = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:serie
DTSTAMP:20260101T000000Z
SUMMARY:Morgenlage
DTSTART;TZID=Europe/Berlin:20261109T083000
DTEND;TZID=Europe/Berlin:20261109T090000
RRULE:FREQ=DAILY;COUNT=4
ORGANIZER:mailto:lisa@example.org
ATTENDEE;PARTSTAT=ACCEPTED:mailto:leon@example.org
END:VEVENT
BEGIN:VEVENT
UID:serie
DTSTAMP:20260101T000000Z
RECURRENCE-ID;TZID=Europe/Berlin:20261111T083000
SUMMARY:Morgenlage
DTSTART;TZID=Europe/Berlin:20261111T083000
DTEND;TZID=Europe/Berlin:20261111T090000
ORGANIZER:mailto:lisa@example.org
ATTENDEE;PARTSTAT=DECLINED:mailto:leon@example.org
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n")
CAL = {"name": "Arbeit", "color": "#E9322D"}
start, end = datetime(2026, 11, 9, tzinfo=TZ), datetime(2026, 11, 14, tzinfo=TZ)
helper = nk.NextcloudKalender({"id": "nextcloud_kalender"})
days = [e["start"].day for e in helper.parse_events(SERIES, CAL, TZ, start, end, ME)]
check("Serie: nur der abgelehnte Tag fehlt", sorted(days), [9, 10, 12])
check("Serie: gezählt", getattr(helper, "declined_hidden", 0), 1)
days = [e["start"].day for e in nk.NextcloudKalender({"id": "x"}).parse_events(SERIES, CAL, TZ, start, end)]
check("Serie ohne eigene Adressen: alles da (alter Aufruf)", sorted(days), [9, 10, 11, 12])
cancelled = SERIES.replace("ATTENDEE;PARTSTAT=DECLINED", "STATUS:CANCELLED\r\nATTENDEE;PARTSTAT=ACCEPTED")
days = [e["start"].day for e in helper.parse_events(cancelled, CAL, TZ, start, end, ME)]
check("abgesagter Einzeltermin fehlt weiter", sorted(days), [9, 10, 12])

# --- Nextcloud-Antwort auf den Principal (so sieht sie bei Nextcloud aus) ---
NC_XML = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:s="http://sabredav.org/ns" xmlns:cal="urn:ietf:params:xml:ns:caldav">
 <d:response><d:href>/remote.php/dav/principals/users/leon/</d:href>
  <d:propstat><d:prop>
   <cal:calendar-home-set><d:href>/remote.php/dav/calendars/leon/</d:href></cal:calendar-home-set>
   <cal:calendar-user-address-set>
    <d:href>mailto:Leon@Example.org</d:href>
    <d:href>/remote.php/dav/principals/users/leon/</d:href>
   </cal:calendar-user-address-set>
  </d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>
 </d:response>
</d:multistatus>"""


class FakeResp:
    status_code = 207
    content = NC_XML
    text = NC_XML.decode()


client = nk.CalDavClient("https://cloud.example.de/remote.php/dav/", "leon", "x")
client.session.request = lambda *a, **k: FakeResp()
home, addrs = client._principal("https://cloud.example.de/remote.php/dav/principals/users/leon/")
check("Nextcloud: Kalender-Home", home, "https://cloud.example.de/remote.php/dav/calendars/leon/")
check("Nextcloud: eigene Adressen", addrs, {"mailto:leon@example.org",
                                            "https://cloud.example.de/remote.php/dav/principals/users/leon"})
NC_XML_404 = NC_XML.replace(b"<cal:calendar-user-address-set>", b"").replace(b"</cal:calendar-user-address-set>", b"")
NC_XML_404 = NC_XML_404.replace(b"<d:href>mailto:Leon@Example.org</d:href>", b"").replace(
    b"\n    <d:href>/remote.php/dav/principals/users/leon/</d:href>\n", b"")
FakeResp.content = NC_XML_404
home, addrs = client._principal("https://cloud.example.de/remote.php/dav/principals/users/leon/")
check("ohne Adressliste: Home trotzdem", home, "https://cloud.example.de/remote.php/dav/calendars/leon/")
check("ohne Adressliste: keine Adressen", addrs, set())

# --- Echter Weg gegen den Testserver ----------------------------------------
try:
    import caldav_server
except ImportError:
    caldav_server = None
if caldav_server is None:
    print("übersprungen: Testserver (pip install -r dev/requirements.txt)")
else:
    base = date(2026, 11, 10)
    url, user, password = caldav_server.start(base)
    client = nk.CalDavClient(nk.dav_root(url), user, password)
    cals = client.calendars()
    check("Testserver: mailto erkannt", caldav_server.MAILTO in client.own_addresses, True)
    helper = nk.NextcloudKalender({"id": "nextcloud_kalender"})
    s = datetime.combine(base, datetime.min.time(), TZ)
    e = s + timedelta(days=3)
    titles = []
    for cal in cals:
        for ics in client.events(cal["url"], s, e):
            titles += [ev["title"] for ev in helper.parse_events(ics, cal, TZ, s, e, client.own_addresses)]
    check("Testserver: keine abgelehnten Termine", [t for t in titles if t.startswith("Abgelehnt")], [])
    check("Testserver: zwei ausgeblendet", helper.declined_hidden, 2)
    check("Testserver: übrige Termine da", "Ausschusssitzung" in titles and "Jour fixe Team" in titles, True)

print("Alles in Ordnung." if not fails else f"{fails} Fehler.")
sys.exit(1 if fails else 0)
