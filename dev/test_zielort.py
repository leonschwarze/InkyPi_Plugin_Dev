"""Tests für zielort.py (Wetter am Zielort, seit 1.30) ohne Rendern.

  python dev/test_zielort.py

Geprüft: Ortsnamen aus dem Ortsfeld, welche Treffer der Geokodierung zählen, Entfernung (30 km),
Zwischenspeicher, Stundenfenster des Termins, Texte („Regen ab 14 Uhr“, „Regen 80 %“, Nachtsymbol),
welche Termine eine Zeile bekommen und die Statusanzeige (Zielort vs. Reiseziel).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEV = REPO / "dev"
inkypi_src = Path(os.environ.get("INKYPI_DIR", REPO.parent / "InkyPi")).resolve() / "src"
sys.path.insert(0, str(DEV))
from render import link_plugins  # noqa: E402

link_plugins(inkypi_src)
sys.path.insert(0, str(inkypi_src))

from plugins.tagesdashboard import status, urlaub, zielort  # noqa: E402
from plugins.tagesdashboard.lib import dwd_icons as icons  # noqa: E402
from plugins.tagesdashboard.lib import dwd_wetter as dwd  # noqa: E402

FAILED = []


def check(name, condition):
    print(f"[{'ok' if condition else 'FEHLER'}] {name}")
    if not condition:
        FAILED.append(name)


TZ = timezone(timedelta(hours=1))
BONN = (50.7374, 7.0982)
W = dwd.DwdWetter({"id": "dwd_wetter"})


class Resp:
    def __init__(self, data, status_code=200):
        self._data, self.status_code = data, status_code

    def json(self):
        return self._data


class Session:
    """Ersetzt requests.Session: `answer(url, params)` liefert die Antwort, Aufrufe werden gezählt."""
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def get(self, url, params=None, timeout=None, **kw):
        self.calls.append((url, params))
        return self.answer(url, params or {})


def place(name, lat, lon, cc="DE", code="PPL", pop=10_000):
    return {"name": name, "latitude": lat, "longitude": lon, "country_code": cc, "feature_code": code,
            "population": pop}


PLACES = {"düsseldorf": [place("Düsseldorf", 51.2217, 6.7762, code="PPLA", pop=620_000)],
          "köln": [place("Köln", 50.9333, 6.95, code="PPLA2", pop=1_080_000)],
          "bad godesberg": [place("Bad Godesberg", 50.6842, 7.1556, code="PPLX", pop=0)],
          "eschweiler": [place("Eschweiler", 50.8169, 6.2652, code="PPLA4", pop=56_000)],
          "post tower": [],
          "post": [place("Post", 33.19, -101.38, cc="US", code="PPLA2", pop=5_000)],
          "paris": [place("Paris", 48.857, 2.352, cc="FR", code="PPLC", pop=2_100_000)],
          "rathaus": [place("Rathaus", 48.1, 11.5, code="BLDG", pop=0)],
          # erster Treffer ein Gebäude, zweiter der Ort: der Ort zählt
          "aachen": [place("Aachen", 50.77, 6.08, code="BLDG"), place("Aachen", 50.7766, 6.0834, code="PPLA3",
                                                                       pop=250_000)]}


def geo_answer(url, p):
    hits = PLACES.get(p.get("name", "").lower())
    return Resp({"results": hits} if hits else {"generationtime_ms": 0.2})


def reset():
    zielort._geo.clear()
    urlaub._wx.clear()
    status.reset()


# ---------------------------------------------------------------- Ortsnamen aus dem Ortsfeld
C = zielort.candidates
check("PLZ + Ort zuerst", C("Landtag NRW, Platz des Landtags 1, 40221 Düsseldorf")[0] == "Düsseldorf")
check("Straße und Hausnummer fallen weg", "Platz des Landtags 1" not in C("Landtag NRW, Platz des Landtags 1, 40221 Düsseldorf"))
check("„Köln Hbf“ → Köln", C("Köln Hbf") == ["Köln"])
check("„Düsseldorf Flughafen“ → Düsseldorf", C("Düsseldorf Flughafen") == ["Düsseldorf"])
check("„Köln-Mülheim“ → auch Köln", C("Köln-Mülheim") == ["Köln-Mülheim", "Köln"])
check("„Rathaus, Eschweiler“: von hinten", C("Rathaus, Eschweiler") == ["Eschweiler", "Rathaus"])
check("nur Straße → nichts", C("Poppelsdorfer Allee 12") == [])
check("Link → nichts", C("https://zoom.us/j/123456") == [] and C("www.bonn.de/live") == [])
check("„Post Tower“ wird nicht zu „Post“ zerlegt", C("Post Tower") == ["Post Tower"])
check("leer → nichts", C("") == [] and C(None) == [])
check("zu kurz → nichts", C("A, B") == [])

# ---------------------------------------------------------------- welche Treffer zählen
A = zielort.acceptable
check("Ort in Deutschland", A(place("Eschweiler", 0, 0, code="PPLA4")))
check("Stadtteil (PPLX) zählt", A(place("Bad Godesberg", 0, 0, code="PPLX", pop=0)))
check("Gebäude zählt nicht", not A(place("Rathaus", 0, 0, code="BLDG")))
check("kleiner Namensvetter im Ausland zählt nicht (Post/Texas)", not A(place("Post", 0, 0, cc="US", pop=5_000)))
check("Großstadt im Ausland zählt (Paris)", A(place("Paris", 0, 0, cc="FR", code="PPLC", pop=2_100_000)))
check("ohne Angaben zählt nicht", not A({"latitude": 1, "longitude": 2}))

# ---------------------------------------------------------------- Geokodierung und Speicher
reset()
s = Session(geo_answer)
hit = zielort.geocode("Aachen", s)
check("erster Ort unter mehreren Treffern", hit and hit["pos"] == (50.7766, 6.0834))
check("fragt nach 5 Treffern", s.calls[0][1]["count"] == 5 and s.calls[0][1]["language"] == "de")
zielort.geocode("aachen", s)
check("Treffer bleibt im Speicher (Schreibweise egal)", len(s.calls) == 1)
check("Gebäude → None", zielort.geocode("Rathaus", s) is None)
n = len(s.calls)
zielort.geocode("Rathaus", s)
check("kein Ort: nicht sofort wieder fragen", len(s.calls) == n)
t, found, wait = zielort._geo["rathaus"]
zielort._geo["rathaus"] = (t - 2 * 3600, found, wait)
zielort.geocode("Rathaus", s)
check("kein Ort: auch nach 2 h noch nicht", len(s.calls) == n)
zielort._geo["rathaus"] = (t - 25 * 3600, found, wait)
zielort.geocode("Rathaus", s)
check("kein Ort: nach 24 h wieder", len(s.calls) == n + 1)

reset()
status.begin()
bad = Session(lambda url, p: Resp({}, 503))
check("HTTP-Fehler → None, kein Absturz", zielort.geocode("Düsseldorf", bad) is None)
check("Statusanzeige: Ausfall unter „Zielort“", ("Zielort", "fail") in [(q, a) for q, a, _ in status._events])
t, found, wait = zielort._geo["düsseldorf"]
check("Dienst gestört: nach einer Stunde wieder", wait == zielort.GEO_RETRY_MIN * 60)

# ---------------------------------------------------------------- Entfernung
reset()
s = Session(geo_answer)
d = zielort.place_of("Landtag NRW, Platz des Landtags 1, 40221 Düsseldorf", BONN, session=s)
check("Düsseldorf ist auswärts (~60 km)", d and d[0]["name"] == "Düsseldorf" and 55 < d[1] < 65)
check("Köln Hbf ist bei 30 km noch zu Hause (~25 km)", zielort.place_of("Köln Hbf", BONN, session=s) is None)
check("… bei 15 km auswärts", zielort.place_of("Köln Hbf", BONN, 15, session=s) is not None)
check("„Paris, Bad Godesberg“: von hinten, Bad Godesberg ist zu Hause, Paris wird nicht mehr versucht",
      zielort.place_of("Paris, Bad Godesberg", BONN, session=s) is None)
check("„Post Tower“ ist kein Ort", zielort.place_of("Post Tower", BONN, session=s) is None)
check("„Café Müller“ ist kein Ort", zielort.place_of("Café Müller", BONN, session=s) is None)
check("MIN_KM = 30 (Leons Wahl)", zielort.MIN_KM == 30)

# ---------------------------------------------------------------- eigene Orte der Anfahrt
from plugins.tagesdashboard import anfahrt  # noqa: E402
own = anfahrt.parse_places("Landtag = 51.2259, 6.7730\nStadthaus = Berliner Platz 2, 53111 Bonn\n"
                           "Büro D = Platz des Landtags 1, 40221 Düsseldorf")
n = len(s.calls)
d = zielort.place_of("landtag", BONN, session=s, places=own)
check("eigener Ort mit Koordinate: ohne Abfrage, Name wie im Termin", d and d[0]["name"] == "landtag"
      and d[0]["pos"] == (51.2259, 6.773) and len(s.calls) == n)
d = zielort.place_of("Sitzung im Landtag, Raum E3", BONN, session=s, places=own)
check("eigener Name genügt als Teil des Ortsfelds", d and d[0]["name"] == "Landtag")
check("eigener Ort in Bonn: zu Hause", zielort.place_of("Stadthaus", BONN, session=s, places=own) is None)
d = zielort.place_of("Büro D", BONN, session=s, places=own)
check("eigener Ort mit Adresse: Ort aus der Adresse", d and d[0]["name"] == "Düsseldorf")
check("ohne eigene Orte wie bisher", zielort.place_of("Landtag", BONN, session=s) is None)


# ---------------------------------------------------------------- Wetter während des Termins
def recs(day, hours, temp=8.0, wet=(), prob=80, icon_dry="cloudy", snow=False, cloud=90):
    """Stundenwerte mit Zeitstempel = Ende der Stunde (wie Bright Sky)."""
    out = []
    for h in hours:
        dt = datetime(day.year, day.month, day.day, tzinfo=TZ) + timedelta(hours=h)
        is_wet = h in wet
        out.append({"dt": dt, "temperature": temp + (h % 3) * 0.3, "cloud_cover": cloud,
                    "precipitation": 0.9 if is_wet else 0.0,
                    "precipitation_probability": prob if is_wet else 10,
                    "icon": ("snow" if snow else "rain") if is_wet else icon_dry})
    return out


day = datetime(2026, 11, 10, tzinfo=TZ)
start, end = day + timedelta(hours=13), day + timedelta(hours=16, minutes=30)
allrecs = recs(day, range(0, 24), wet=(15, 16, 17))
win = zielort.window(allrecs, start, end)
check("Fenster 13–16:30: Stunden 14, 15, 16, 17 (Zeitstempel = Ende der Stunde)",
      [r["dt"].hour for r in win] == [14, 15, 16, 17])
check("Fenster mindestens eine Stunde", [r["dt"].hour for r in zielort.window(allrecs, start, start)] == [14])

sm = zielort.summary(win, start, W, dwd, icons)
check("Regen beginnt während des Termins: „Regen ab 14 Uhr“", sm["rain"] == "Regen ab 14 Uhr")
check("Regensymbol", sm["icon_name"] in ("rain", "showers-day") and "<svg" in sm["icon"])
check("kleine Spanne: nur Höchstwert", sm["temp"] == "9°")

later = day + timedelta(hours=15, minutes=7)
sm = zielort.summary(zielort.window(allrecs, later, end), later, W, dwd, icons)
check("Termin läuft schon im Regen: „Regen 80 %“", sm["rain"] == "Regen 80 %")

sm = zielort.summary(zielort.window(recs(day, range(24), wet=(14,), prob=40), start, end), start, W, dwd, icons)
check("eine nasse Stunde reicht (≥ 0,1 mm), ohne Prozent unter 50 %", sm["rain"] == "Regen")
check("… und gibt ein Schauersymbol statt Wolke", sm["icon_name"] == "showers-day")

sm = zielort.summary(zielort.window(recs(day, range(24), wet=(15,), snow=True), start, end), start, W, dwd, icons)
check("Schnee", sm["rain"] == "Schnee ab 14 Uhr")

sm = zielort.summary(zielort.window(recs(day, range(24)), start, end), start, W, dwd, icons)
check("trocken und bedeckt: kein Regen, „Stark bewölkt“", sm["rain"] is None and sm["text"] == "Stark bewölkt")
dry = recs(day, range(24), icon_dry="partly-cloudy-day", cloud=30)
sm = zielort.summary(zielort.window(dry, start, end), start, W, dwd, icons)
check("trocken und heiter: Sonne mit Wolke", sm["rain"] is None and sm["icon_name"] == "partly-cloudy-day")

eve_s, eve_e = day + timedelta(hours=19, minutes=30), day + timedelta(hours=22)
sm = zielort.summary(zielort.window(dry, eve_s, eve_e), eve_s, W, dwd, icons)
check("abends Mond statt Sonne", sm["icon_name"].endswith("-night"))

wide = [dict(r, temperature=4 + i) for i, r in enumerate(zielort.window(dry, start, end))]
check("große Spanne: „4–7°“", zielort.summary(wide, start, W, dwd, icons)["temp"] == "4–7°")
check("keine Daten → None", zielort.summary([], start, W, dwd, icons) is None)


# ---------------------------------------------------------------- welche Termine, Anzeige
def item(title, location, s_, e_, all_day=False):
    return {"title": title, "location": location, "all_day": all_day, "rain": "85 % Regen",
            "source": {"start": s_, "end": e_}}


def bright_sky(url, p):
    if "geocoding" in url:
        return geo_answer(url, p)
    rows = []
    nxt = recs(day + timedelta(days=1), range(24), icon_dry="partly-cloudy-day", cloud=30)
    for r in allrecs + nxt + recs(day + timedelta(days=2), range(24)):
        rows.append({"timestamp": r["dt"].isoformat(), "temperature": r["temperature"] - 2,
                     "precipitation": r["precipitation"], "precipitation_probability": r["precipitation_probability"],
                     "cloud_cover": r["cloud_cover"], "icon": r["icon"]})
    return Resp({"weather": rows})


reset()
status.begin()
now = day + timedelta(hours=10, minutes=20)
cal = [{"events": [
    item("Ausschuss", "Landtag NRW, Platz des Landtags 1, 40221 Düsseldorf", start, end),
    item("Zahnarzt", "Poppelsdorfer Allee 12", day + timedelta(hours=16, minutes=30), day + timedelta(hours=17)),
    item("Vorbei in Düsseldorf", "Düsseldorf", day + timedelta(hours=8), day + timedelta(hours=9)),
    item("Messe", "Düsseldorf", day, day + timedelta(days=1), all_day=True),
    item("Ohne Ort", "", start, end)]},
    {"events": [item("Sprechstunde", "Rathaus, Eschweiler", day + timedelta(days=1, hours=19),
                     day + timedelta(days=1, hours=21))]},
    {"events": [item("Übermorgen", "Düsseldorf", day + timedelta(days=2, hours=10), day + timedelta(days=2, hours=11))]}]
s = Session(bright_sky)
found = zielort.find(cal, BONN, TZ, now, (day + timedelta(days=1)).date(), W, dwd, icons, dwd.parse_ts, session=s)
check("heute und morgen: Ausschuss und Sprechstunde", [it["title"] for it in found] == ["Ausschuss", "Sprechstunde"])
check("Ganztägige, beendete, ohne Ort, übermorgen: nichts",
      all("away" not in it for d_ in cal for it in d_["events"] if it["title"] not in ("Ausschuss", "Sprechstunde")))
check("Bright Sky am Zielort gefragt", any("brightsky" in u and p.get("lat") == 51.2217 for u, p in s.calls))
check("Statusanzeige: Wetter unter „Zielort“", ("Zielort", "ok") in [(q, a) for q, a, _ in status._events]
      and not any(q == "Reiseziel" for q, _, _ in status._events))
a = zielort.annotate(found[0])
check("Zeile: „Düsseldorf 7° · Regen ab 14 Uhr“", a["away_line"] == "Düsseldorf 7° · Regen ab 14 Uhr")
check("Ort gekürzt auf den ersten Teil", a["location"] == "Landtag NRW")
check("Regenhinweis von Bonn entfällt", a["rain"] is None)
b = zielort.annotate(found[1])
check("Eschweiler abends: Mondsymbol, kein Regen", b["away"]["icon_name"].endswith("-night") and b["away"]["rain"] is None)
check("Ort „Rathaus“ bleibt stehen", b["location"] == "Rathaus")
c = zielort.annotate(dict(found[0], location="Düsseldorf"))
check("Ort = Zielort: fällt weg (sonst zweimal Düsseldorf)", c["location"] == "")

reset()
found = zielort.find(cal, (None, None), TZ, now, day.date(), W, dwd, icons, dwd.parse_ts, session=Session(bright_sky))
check("ohne Wetter-Ort: nichts", found == [])

# ---------------------------------------------------------------- Urlaubsbild unverändert
reset()
status.begin()
urlaub.fetch_records((45.76, 4.84), TZ, now, dwd.parse_ts, Session(bright_sky))
check("Urlaubsbild meldet weiter „Reiseziel“", [q for q, _, _ in status._events] == ["Reiseziel", "Reiseziel"])

print()
if FAILED:
    print(f"{len(FAILED)} FEHLER:", *FAILED, sep="\n  ")
    sys.exit(1)
print("Alle Tests bestanden.")
