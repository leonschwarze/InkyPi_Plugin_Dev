"""Sonntagscomic (tagesdashboard/xkcd.py, seit 1.40) ohne Rendern.

  python dev/test_xkcd.py

Prüft gegen dev/mock_xkcd.py: neuester Comic passt → er kommt zuerst; zu breit → der vorherige; keiner passt
→ keine Kandidaten; Ausfall → keine Kandidaten und Statusmeldung; ohne doppelt große Bilder geht es auch;
Zwischenspeicher (zweiter Aufruf fragt nichts mehr); Bild hart schwarz-weiß bzw. farbig; min_w;
dazu free_today, next_event, boundaries und mit dem echten generate_image: Comic nur sonntags, ohne
Termine, außerhalb des Nachrichtenfensters und mit Schalter.
"""
import base64
import io
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEV = ROOT / "dev"
INKYPI = Path(os.environ.get("INKYPI_DIR", ROOT.parent / "InkyPi")) / "src"
sys.path.insert(0, str(DEV))
sys.path.insert(0, str(ROOT / "tagesdashboard"))

import mock_xkcd  # noqa: E402
import status  # noqa: E402
import xkcd  # noqa: E402
from PIL import Image  # noqa: E402

FAILED = []
TZ = ZoneInfo("Europe/Berlin")
LAND, PORT = (800, 480), (480, 800)


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


def fresh(kind):
    import requests
    if not hasattr(fresh, "orig"):
        fresh.orig = requests.Session.get
    requests.Session.get = fresh.orig
    for cache in (xkcd._latest, xkcd._meta, xkcd._sizes, xkcd._picture):
        cache.clear()
    mock_xkcd.calls.clear()
    mock_xkcd.install(None, kind)
    status.begin()


def pixels(c):
    return Image.open(io.BytesIO(base64.b64decode(c["src"].split(",", 1)[1]))).convert("RGB")


# ---------------------------------------------------------------- Auswahl
fresh("normal")
got = xkcd.load(LAND)
check("normal: drei Kandidaten, neuester zuerst", [c["num"] for c in got] == [3327, 3326, 3325])
check("normal: Titel und Mouseover-Text", got[0]["title"] == "Empty Calendar" and got[0]["alt"].startswith("The trick"))
w, h = xkcd.plan_box(LAND)
check("normal: Bild passt in den geplanten Kasten", got[0]["w"] <= w + 1 and got[0]["h"] <= h + 1)
check("normal: mindestens 70 % der normalen Größe", got[0]["w"] >= 440 * xkcd.MIN_SCALE - 1)
check("min_w = 70 % der normalen Breite", got[0]["min_w"] == round(440 * xkcd.MIN_SCALE))
img = pixels(got[0])
check("Bild hat die angegebene Größe", img.size == (got[0]["w"], got[0]["h"]))
check("schwarz-weißer Comic: nur Schwarz und Weiß", set(zip(*[iter(img.tobytes())] * 3)) <= {(0, 0, 0), (255, 255, 255)})
check("doppelt großes Bild genutzt", any(u.endswith("_2x.png") for u in mock_xkcd.calls))
n = len(mock_xkcd.calls)
again = xkcd.load(LAND)
check("zweiter Aufruf: keine Anfrage mehr (Zwischenspeicher)", len(mock_xkcd.calls) == n and again == got)
check("Status: xkcd ok", not status.report(datetime.now(TZ)))

fresh("breit")
got = xkcd.load(LAND)
check("breit: 3327 (740 × 230) übersprungen, 3326 zuerst", got and got[0]["num"] == 3326)

fresh("hoch")
got = xkcd.load(LAND)
check("hoch quer: 3327 (360 × 900) übersprungen", got and got[0]["num"] == 3326)

fresh("keiner")
check("keiner passt: leere Liste", xkcd.load(LAND) == [])
check("keiner passt: höchstens LOOKBACK Comics gefragt",
      sum(1 for u in mock_xkcd.calls if u.endswith("/info.0.json") and "/33" in u) <= xkcd.LOOKBACK)

fresh("farbig")
got = xkcd.load(LAND)
cols = set(zip(*[iter(pixels(got[0]).tobytes())] * 3))
check("farbiger Comic behält seine Farben", any(r > 150 and g < 80 for r, g, b in cols))

fresh("nur1x")
got = xkcd.load(LAND)
check("ohne _2x: Comic trotzdem da, höchstens 1:1", got and got[0]["num"] == 3327 and got[0]["w"] <= 440)

fresh("down")
now = datetime(2026, 11, 15, 14, 20, tzinfo=TZ)
check("Ausfall: leere Liste", xkcd.load(LAND) == [])
status.commit(now)
check("Ausfall: Statusanzeige „xkcd“", [s["name"] for s in status.report(now)] == ["xkcd"])
n = len(mock_xkcd.calls)
xkcd.load(LAND)
check("Ausfall: 30 min nicht noch einmal gefragt", len(mock_xkcd.calls) == n)

check("Adresse der doppelten Größe", xkcd.double_url("https://imgs.xkcd.com/comics/a_b.png")
      == "https://imgs.xkcd.com/comics/a_b_2x.png")
check("interaktive Comics werden übersprungen", xkcd.clean_meta({"num": 1, "img": "x.png", "extra_parts": {"pre": ""}}) is None)
check("animierte GIFs werden übersprungen", xkcd.clean_meta({"num": 1, "img": "x.gif"}) is None)

# ---------------------------------------------------------------- Termine
now = datetime(2026, 11, 15, 14, 20, tzinfo=TZ)


def ev(h0, h1, title="T", all_day=False, short=None):
    s = now.replace(hour=h0, minute=0)
    e = now.replace(hour=h1, minute=0) if h1 < 24 else s.replace(hour=0) + timedelta(days=1)
    return {"title": title, "all_day": all_day, "short": short or f"{h0}:00", "source": {"start": s, "end": e}}


check("frei: keine Termine", xkcd.free_today({"is_today": True, "events": []}, now))
check("frei: Termin schon vorbei (mit showPast)", xkcd.free_today({"is_today": True, "events": [ev(10, 12)]}, now))
check("nicht frei: Termin läuft noch", not xkcd.free_today({"is_today": True, "events": [ev(14, 15)]}, now))
check("nicht frei: ganztägiger Termin", not xkcd.free_today({"is_today": True, "events": [ev(0, 24, all_day=True)]}, now))
cal = [{"is_today": True, "label": "Heute", "events": []},
       {"is_today": False, "label": "Morgen", "events": [ev(0, 24, "Müll", True), ev(10, 11, "Jour fixe")]}]
check("nächster Termin mit Uhrzeit bevorzugt", xkcd.next_event(cal) == "Morgen 10:00 Jour fixe")
check("nur ganztägig: ohne Uhrzeit", xkcd.next_event([cal[0], {"is_today": False, "label": "Di",
                                                                 "events": [ev(0, 24, "Müll", True)]}]) == "Di Müll")
check("kein nächster Termin: None", xkcd.next_event(cal[:1]) is None)
check("Grenze sonntags = Ende des letzten Termins", xkcd.boundaries(now, [ev(14, 17)]) == [now.replace(hour=17, minute=0)])
check("Grenze werktags: keine", xkcd.boundaries(now - timedelta(days=1), [ev(14, 17)]) == [])

# ---------------------------------------------------------------- mit dem echten generate_image
os.chdir(INKYPI)
sys.path.insert(0, str(INKYPI))
os.environ["DEV_PROTO"] = "frei"
import caldav_server  # noqa: E402
import mock_brightsky  # noqa: E402
import mock_news  # noqa: E402
import mock_radar  # noqa: E402
import mock_luft  # noqa: E402
import mock_pollen  # noqa: E402
import mock_nina  # noqa: E402

link = INKYPI / "plugins" / "tagesdashboard"
if not link.exists():
    link.symlink_to(ROOT / "tagesdashboard")
from plugins.tagesdashboard import tagesdashboard as td  # noqa: E402

seen = {}


class Cfg:
    def get_resolution(self):
        return (800, 480)

    def get_config(self, key, default=None):
        return {"timezone": "Europe/Berlin", "orientation": "horizontal"}.get(key, default)

    def load_env_key(self, key):
        return seen.get("pw") if key == "NEXTCLOUD_APP_PASSWORD" else None


def params_at(t, **extra):
    """Parameter, die ans Template gingen (render_image abgefangen)."""
    fresh("normal")
    mock_brightsky.install(t, "herbst")  # reicht fremde Adressen ans echte Netz weiter, deshalb zuerst
    mock_news.install(t, "normal")
    mock_radar.install(t, "trocken")
    for mod in (mock_luft, mock_pollen, mock_nina):
        mod.install(t)
    mock_xkcd.install(t, "normal")
    import mock_ziel  # Zielort-Geokodierung nie ins Netz (merkt sich den vorigen get, deshalb zuletzt)
    mock_ziel.install(t)
    url, user, pw = caldav_server.start(t.date())
    seen["pw"] = pw
    td._IMAGE_CACHE.clear()
    td._NIGHT_CACHE.clear()
    p = td.Tagesdashboard({"id": "tagesdashboard"})
    p.current_time = lambda tz: t.astimezone(tz)
    got = {}
    p.render_image = lambda dims, html, css, params: got.update(params) or Image.new("RGB", dims, "white")
    settings = {"nextcloudUrl": url, "username": user, "latitude": "50.73", "longitude": "7.10", "einkSnap": "false",
                "verifySSL": "false", **extra}
    p.generate_image(settings, Cfg())
    return got


sunday = datetime(2026, 11, 15, 14, 20, tzinfo=TZ)
pp = params_at(sunday)
check("Sonntag 14:20, Frühstück vorbei: Comic", pp.get("comics") and pp["comics"][0]["num"] == 3327)
check("Zeile „frei · …“ nennt den nächsten Termin", (pp.get("comic_next") or "").startswith("Morgen"))
check("Sonntag 11:00, Frühstück läuft: kein Comic", not params_at(sunday.replace(hour=11, minute=0)).get("comics"))
check("Sonntag 9:00 im Nachrichtenfenster: kein Comic", not params_at(sunday.replace(hour=9, minute=0)).get("comics"))
check("Samstag ohne Termine: kein Comic", not params_at(sunday - timedelta(days=1)).get("comics"))
check("Schalter aus: kein Comic", not params_at(sunday, cfgVersion="26").get("comics"))
check("Wochenvorschau (18:30): kein Comic", not params_at(sunday.replace(hour=18, minute=30)).get("comics"))

print()
print("Alles in Ordnung." if not FAILED else f"{len(FAILED)} Fehler: {', '.join(FAILED)}")
sys.exit(1 if FAILED else 0)
