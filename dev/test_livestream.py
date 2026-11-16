"""Tests für livestream.py (Termin erkennen, Adresse, QR-Code, Fenstergrenzen) ohne Rendern.

Der QR-Code wird zurückgelesen: aus dem SVG ein Pixelbild bauen und mit OpenCV dekodieren
(falls OpenCV fehlt, wird nur die Form geprüft)."""
import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "tagesdashboard")
import livestream  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def ev(title, start, end, all_day=False):
    """Eintrag wie events_on_day() im Kalender: Titel, ganztägig, Rohdaten unter source."""
    return {"title": title, "all_day": all_day, "source": {"start": start, "end": end}}


day = datetime(2026, 11, 12, tzinfo=TZ)
rat = ev("Ratssitzung", day.replace(hour=17), day.replace(hour=22))
bv = ev("Bezirksvertretung Beuel", day.replace(hour=18), day.replace(hour=21))
lauf = ev("Lauftreff Rheinaue", day.replace(hour=18, minute=30), day.replace(hour=20))
W = livestream.DEFAULT_WORDS

# ---------------------------------------------------------------- Stichwörter
check("Ratssitzung passt", livestream.matches("Ratssitzung", W))
check("Groß/klein egal, Teil des Titels genügt", livestream.matches("RATSSITZUNG (Haushalt 2027)", W))
check("Anderer Termin passt nicht", not livestream.matches("Ausschusssitzung", W))
check("Mehrere Stichwörter mit Komma", livestream.matches("Bezirksvertretung Beuel", "Ratssitzung, Bezirksvertretung"))
check("Leere Stichwörter passen nie", not livestream.matches("Ratssitzung", " , "))
check("Leerer Titel passt nie", not livestream.matches(None, W))

# ---------------------------------------------------------------- Läuft gerade?
check("Vor Beginn: nichts", livestream.running([rat], W, day.replace(hour=16, minute=59)) is None)
check("Genau zu Beginn: läuft", livestream.running([rat], W, day.replace(hour=17)) is rat)
check("Mittendrin: läuft", livestream.running([rat, lauf], W, day.replace(hour=19)) is rat)
check("Genau zum Ende: vorbei", livestream.running([rat], W, day.replace(hour=22)) is None)
allday = ev("Ratssitzung", day, day + timedelta(days=1), all_day=True)
check("Ganztägiger Termin zählt nicht", livestream.running([allday], W, day.replace(hour=12)) is None)
two = livestream.running([bv, rat], "Ratssitzung, Bezirksvertretung", day.replace(hour=19))
check("Zwei zugleich: der früher begonnene", two is rat)
check("Keine Termine: nichts", livestream.running(None, W, day) is None)

# ---------------------------------------------------------------- Adresse
check("Leer: Standardadresse", livestream.normalize_url("  ") == livestream.DEFAULT_URL)
check("Ohne Schema: https:// davor", livestream.normalize_url("bonn.de/livestream") == "https://bonn.de/livestream")
check("Mit Schema bleibt", livestream.normalize_url("http://example.org/x") == "http://example.org/x")
check("Kurzform ohne https://www.", livestream.short_url("https://www.bonn.de/livestream") == "bonn.de/livestream")
check("Kurzform ohne Schrägstrich am Ende", livestream.short_url("https://youtube.com/@bundesstadtbonn/") == "youtube.com/@bundesstadtbonn")

# ---------------------------------------------------------------- Karte
c = livestream.card([lauf, rat], W, "", day.replace(hour=18, minute=10))
check("Karte: Titel des Termins", c and c["title"] == "Ratssitzung")
check("Karte: bis 22:00", c and c["until"] == "bis 22:00")
check("Karte: Standardadresse kurz", c and c["url"] == "bonn.de/livestream" and c["href"] == livestream.DEFAULT_URL)
late = ev("Ratssitzung", day.replace(hour=17), day.replace(hour=0) + timedelta(days=1, hours=0, minutes=30))
c2 = livestream.card([late], W, "", day.replace(hour=23))
check("Über Mitternacht: Datum dabei", c2 and c2["until"] == "bis 13.11. 0:30")
check("Ohne Sitzung: keine Karte", livestream.card([lauf], W, "", day.replace(hour=19)) is None)

# ---------------------------------------------------------------- QR-Code
svg, n = livestream.qr_svg(livestream.DEFAULT_URL)
check("29 Module (Version 3) + 2 × Ruhezone", n == 29 + 2 * livestream.QUIET)
check("viewBox und data-n passen zusammen", f'data-n="{n}"' in svg and f'viewBox="0 0 {n} {n}"' in svg)
check("Weißer Grund (auch bei dunklem Hintergrund)", '<rect width="%d" height="%d" fill="#fff"/>' % (n, n) in svg)
check("Scharfe Kanten", 'shape-rendering="crispEdges"' in svg)
svg_evil, _ = livestream.qr_svg('https://x.de/?a="<b>&c')
check("Adresse im aria-label maskiert", '"<b>' not in svg_evil and "&lt;b&gt;" in svg_evil)


def to_image(svg_text, size, scale=4):
    """Pfad aus Läufen „M x y h len v1 h-len z“ in ein Pixelbild zurückübersetzen."""
    import numpy as np
    img = np.full((size * scale, size * scale), 255, np.uint8)
    for x, y, w in re.findall(r"M(\d+) (\d+)h(\d+)v1h-\d+z", svg_text):
        x, y, w = int(x), int(y), int(w)
        img[y * scale:(y + 1) * scale, x * scale:(x + w) * scale] = 0
    return np.pad(img, 4 * scale, constant_values=255)


try:
    import cv2
except ImportError:
    cv2 = None
    print("(OpenCV fehlt: QR-Codes werden nicht zurückgelesen)")
for url in (livestream.DEFAULT_URL, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://bonn.de/rat?ä=ü"):
    s, size = livestream.qr_svg(url)
    if cv2 is not None:
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(to_image(s, size))
        check(f"QR liest sich zurück: {url}", text == url)

# ---------------------------------------------------------------- Fenstergrenzen (Bild-Cache)
b = livestream.boundaries([rat, lauf, allday], W, day.replace(hour=15))
check("Grenzen: Beginn und Ende, sonst nichts", b == [day.replace(hour=17), day.replace(hour=22)])
check("Grenzen: Vergangenes fällt weg", livestream.boundaries([rat], W, day.replace(hour=18)) == [day.replace(hour=22)])

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER: {', '.join(FAILED)}")
    sys.exit(1)
print("ALLE TESTS OK")
